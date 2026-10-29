from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from executors import lab_transport  # noqa: E402


def test_detect_vagrant_provider_prefers_explicit_sticks_env(monkeypatch) -> None:
    monkeypatch.setenv("STICKS_VAGRANT_PROVIDER", "qemu")
    monkeypatch.delenv("VAGRANT_DEFAULT_PROVIDER", raising=False)

    assert lab_transport.detect_vagrant_provider() == "qemu"


def test_lab_detection_reports_unreachable_transport_without_hiding_bad_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        lab_transport,
        "resolve_target_vm_name",
        lambda _profile: (_ for _ in ()).throw(FileNotFoundError("missing VM")),
    )

    assert lab_transport.detect_lab_infrastructure("0.shadowray") == ""

    monkeypatch.setattr(
        lab_transport,
        "resolve_target_vm_name",
        lambda _profile: (_ for _ in ()).throw(ValueError("bad profile")),
    )
    with pytest.raises(ValueError, match="bad profile"):
        lab_transport.detect_lab_infrastructure("0.shadowray")


def test_run_command_in_vm_sets_vagrant_default_provider(
    monkeypatch, tmp_path: Path
) -> None:
    vm_dir = tmp_path / "lab" / "vagrant" / "target-linux-1"
    vm_dir.mkdir(parents=True)
    monkeypatch.setattr(lab_transport, "LAB_VAGRANT_DIR", tmp_path / "lab" / "vagrant")

    captured: dict[str, object] = {}

    def fake_run(
        command, cwd=None, capture_output=None, text=None, timeout=None, env=None
    ):
        captured["command"] = command
        captured["cwd"] = cwd
        captured["env"] = env
        return subprocess.CompletedProcess(command, 0, "ok", "")

    monkeypatch.setattr(lab_transport.subprocess, "run", fake_run)
    monkeypatch.setenv("STICKS_VAGRANT_PROVIDER", "qemu")

    result = lab_transport.run_command_in_vm("target-linux-1", "echo ok")

    assert result.returncode == 0
    assert captured["command"] == ["vagrant", "ssh", "-c", "echo ok"]
    assert captured["cwd"] == vm_dir
    assert captured["env"]["VAGRANT_DEFAULT_PROVIDER"] == "qemu"


def test_run_bash_on_target_vm_passes_provider_to_vagrant_transport(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        lab_transport, "resolve_target_vm_name", lambda _: "target-linux-1"
    )
    captured: dict[str, object] = {}

    def fake_run_command_in_vm(
        vm_name: str, remote_cmd: str, timeout: int, provider: str | None = None
    ):
        captured["vm_name"] = vm_name
        captured["remote_cmd"] = remote_cmd
        captured["timeout"] = timeout
        captured["provider"] = provider
        return subprocess.CompletedProcess(["vagrant"], 0, "ok", "")

    monkeypatch.setattr(lab_transport, "run_command_in_vm", fake_run_command_in_vm)

    result = lab_transport.run_bash_on_target_vm(
        sut_profile_id="0.shadowray",
        bash_script="echo hello",
        timeout=12,
        provider="qemu",
    )

    assert result.returncode == 0
    assert captured["vm_name"] == "target-linux-1"
    assert captured["timeout"] == 12
    assert captured["provider"] == "qemu"
    assert "bash -lc" in captured["remote_cmd"]


def test_topology_probe_binds_one_nonce_without_granting_shell_authority(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def run(vm_name, remote_cmd, **kwargs):
        captured["vm_name"] = vm_name
        captured["remote_cmd"] = remote_cmd
        captured.update(kwargs)
        return subprocess.CompletedProcess([], 0, "nonce-a\tattacker\tboot-a\n", "")

    monkeypatch.setattr(lab_transport, "run_command_in_vm", run)

    result = lab_transport.probe_vm_identity("attacker", "nonce-a", provider="qemu")

    assert result.stdout.startswith("nonce-a\t")
    assert captured["vm_name"] == "attacker"
    assert captured["provider"] == "qemu"
    assert "nonce-a" in captured["remote_cmd"]


@pytest.mark.parametrize("nonce", ["", "two tokens"])
def test_topology_probe_rejects_ambiguous_nonce(nonce: str) -> None:
    with pytest.raises(ValueError, match="nonce"):
        lab_transport.probe_vm_identity("attacker", nonce)


def test_target_script_runs_as_explicit_user_without_root_fallback(monkeypatch):
    monkeypatch.setattr(
        lab_transport, "resolve_target_vm_name", lambda _: "target-linux-1"
    )
    commands = []

    def run(vm_name, remote_cmd, **kwargs):
        commands.append(remote_cmd)
        return subprocess.CompletedProcess([], 1, "", "unknown user")

    monkeypatch.setattr(lab_transport, "run_command_in_vm", run)
    result = lab_transport.run_bash_on_target_vm(
        "fixture", "id -un", execution_user="clouduser"
    )
    assert result.returncode == 1
    assert len(commands) == 1
    assert "sudo -n -H -u clouduser -- bash -lc" in commands[0]


@pytest.mark.parametrize(
    "owner,declared,valid",
    [
        ("clouduser", "clouduser", True),
        ("other", "clouduser", False),
        ("root", "root", False),
    ],
)
def test_browser_binding_requires_declared_non_root_owner(
    monkeypatch, owner, declared, valid
):
    target = SimpleNamespace(
        users=[SimpleNamespace(username=declared)],
        files=[
            SimpleNamespace(path=f"/home/{owner}/.mozilla/profiles.ini", owner=owner)
        ],
    )
    profile = SimpleNamespace(hosts={"target-base": target})
    monkeypatch.setattr(lab_transport, "load_sut_profile", lambda _: profile)
    monkeypatch.setattr(
        lab_transport, "resolve_target_vm_name", lambda _: "target-linux-1"
    )
    monkeypatch.setattr(lab_transport, "normalize_vm_name", lambda _: "target-linux-1")
    if valid:
        assert lab_transport.browser_discovery_binding("fixture") == (
            owner,
            (f"/home/{owner}/.mozilla/profiles.ini",),
        )
    else:
        with pytest.raises(ValueError, match="one declared non-root"):
            lab_transport.browser_discovery_binding("fixture")
