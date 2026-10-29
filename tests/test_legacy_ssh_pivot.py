from pathlib import Path

import pytest
import yaml

from lab.vagrant import apply_sut_profile


PROFILE_PATH = Path(__file__).resolve().parents[1] / "lab/sut_profiles/0.lateral_test.yml"
PUBLIC_KEY = "ssh-ed25519 QUFBQUFBQUFBQUFB source@target-1"


def test_lateral_profile_declares_pivot_without_embedded_key() -> None:
    profile_bytes = PROFILE_PATH.read_bytes()
    profile = yaml.safe_load(profile_bytes)
    source = profile["sut_configuration"]["target-1"]
    target = profile["sut_configuration"]["target-2"]

    assert b"-----BEGIN" not in profile_bytes
    assert source["ssh_pivot"] == {
        "source_user": "pivotuser",
        "target_vm": "target-2",
        "target_user": "target2user",
    }
    assert all("authorized_keys" not in file["path"] for file in target["files"])


def test_pivot_provisioning_generates_key_inside_source_vm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, str]] = []
    responses = ["", PUBLIC_KEY + "\n", "", PUBLIC_KEY + "\n"]

    def fake_ssh(vm_name: str, command: str, timeout: int = 30) -> tuple[bool, str, str]:
        calls.append((vm_name, command))
        return True, responses.pop(0), ""

    monkeypatch.setattr(apply_sut_profile, "run_vagrant_ssh", fake_ssh)
    spec = apply_sut_profile.SshPivotSpec.from_profile(
        "target-1",
        {"source_user": "pivotuser", "target_vm": "target-2", "target_user": "target2user"},
        ["target-1", "target-2"],
    )

    apply_sut_profile.provision_ssh_pivot(spec)

    assert [name for name, _ in calls] == ["target-1", "target-1", "target-2", "target-2"]
    assert "test ! -e" in calls[0][1]
    assert "ssh-keygen" in calls[0][1]
    assert "PRIVATE KEY" not in " ".join(command for _, command in calls)
    assert "authorized_keys" in calls[2][1]
    assert not responses


def test_pivot_provisioning_fails_if_key_generation_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        apply_sut_profile,
        "run_vagrant_ssh",
        lambda vm_name, command, timeout=30: (False, "", "generation refused"),
    )
    spec = apply_sut_profile.SshPivotSpec("target-1", "pivotuser", "target-2", "target2user")

    with pytest.raises(RuntimeError, match="generation refused"):
        apply_sut_profile.provision_ssh_pivot(spec)


def test_pivot_provisioning_fails_on_trust_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = ["", PUBLIC_KEY + "\n", "", "different-key\n"]
    monkeypatch.setattr(
        apply_sut_profile,
        "run_vagrant_ssh",
        lambda vm_name, command, timeout=30: (True, responses.pop(0), ""),
    )
    spec = apply_sut_profile.SshPivotSpec("target-1", "pivotuser", "target-2", "target2user")

    with pytest.raises(ValueError, match="trust differs"):
        apply_sut_profile.provision_ssh_pivot(spec)


def test_pivot_spec_rejects_missing_or_unsafe_host() -> None:
    configuration = {
        "source_user": "pivotuser",
        "target_vm": "target-2",
        "target_user": "target2user",
    }
    with pytest.raises(ValueError, match="required VMs"):
        apply_sut_profile.SshPivotSpec.from_profile("target-1", configuration, ["target-1"])
    with pytest.raises(ValueError, match="safe identifiers"):
        apply_sut_profile.SshPivotSpec.from_profile(
            "target-1", {**configuration, "target_user": "user; exit 1"}, ["target-1", "target-2"]
        )


def test_profile_applies_pivot_after_both_targets_are_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []
    for operation in (
        "apply_user_config",
        "apply_service_config",
        "apply_network_config",
        "apply_files_config",
        "apply_weaknesses",
    ):
        monkeypatch.setattr(
            apply_sut_profile,
            operation,
            lambda vm_name, configuration: events.append(f"configure:{vm_name}"),
        )
    monkeypatch.setattr(
        apply_sut_profile,
        "validate_sut",
        lambda vm_name, profile: events.append(f"validate:{vm_name}"),
    )
    monkeypatch.setattr(
        apply_sut_profile,
        "provision_ssh_pivot",
        lambda spec: events.append(f"pivot:{spec.source_vm}->{spec.target_vm}"),
    )

    assert apply_sut_profile.apply_profile(PROFILE_PATH)
    assert events[-1] == "pivot:target-1->target-2"
    assert "validate:target-1" in events[:-1]
    assert "validate:target-2" in events[:-1]
