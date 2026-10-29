"""Lifecycle bootstrap binds actual guest boot identity before granting authority."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from runners.capability_store import CapabilityStore
from runners.lab_runtime_bootstrap import (
    bootstrap_lab_authority,
    qualify_declared_lab_topology,
)


def install_probe(
    monkeypatch, *, second_boot="boot-a", principal="ubuntu", failed=False
):
    nonces = iter(["nonce-a", "nonce-b"])
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.uuid4", lambda: SimpleNamespace(hex=next(nonces))
    )
    calls = []

    def probe(profile_id, script, **kwargs):
        assert profile_id == "0.c0026"
        assert kwargs["execution_user"] == "ubuntu"
        calls.append(script)
        nonce = "nonce-a" if len(calls) == 1 else "nonce-b"
        assert nonce in script
        payload = json.dumps(
            dict(
                hostname="target-linux-1",
                principal=principal,
                boot_id="boot-a" if len(calls) == 1 else second_boot,
                nonce=nonce,
            )
        )
        return subprocess.CompletedProcess(
            ["guest-probe"], 17 if failed else 0, payload, "original stderr"
        )

    monkeypatch.setattr("runners.lab_runtime_bootstrap.run_bash_on_target_vm", probe)
    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", probe)
    return calls


def bootstrap(tmp_path, store):
    return bootstrap_lab_authority(
        sut_profile_id="0.c0026",
        expected_host_id="target-linux-1",
        principal="ubuntu",
        run_id="run-a",
        environment_id="lab-a",
        run_root=tmp_path,
        store=store,
    )


def test_actual_boot_identity_is_bound_before_registered_shell_authority(
    monkeypatch, tmp_path
):
    calls = install_probe(monkeypatch)
    store = CapabilityStore()
    acquired = bootstrap(tmp_path, store)
    assert acquired.scope.epoch == "boot-a"
    assert acquired.scope.run_id == "run-a"
    assert len(calls) == 2
    assert [fact.name for fact in store.snapshot()] == ["lab:shell"]
    assert acquired.reference.authority_id == "lab-shell"


def test_reboot_between_discovery_and_acquisition_grants_no_authority(
    monkeypatch, tmp_path
):
    install_probe(monkeypatch, second_boot="boot-b")
    store = CapabilityStore()
    with pytest.raises(ValueError):
        bootstrap(tmp_path, store)
    assert store.snapshot() == ()
    assert (tmp_path / "observations").is_dir()


def test_wrong_discovery_principal_is_rejected_before_retention(monkeypatch, tmp_path):
    install_probe(monkeypatch, principal="vagrant")
    store = CapabilityStore()
    with pytest.raises(ValueError):
        bootstrap(tmp_path, store)
    assert store.snapshot() == ()
    assert list(tmp_path.iterdir()) == []


def test_discovery_command_failure_preserves_original_exit(monkeypatch, tmp_path):
    install_probe(monkeypatch, failed=True)
    store = CapabilityStore()
    with pytest.raises(subprocess.CalledProcessError) as caught:
        bootstrap(tmp_path, store)
    assert caught.value.returncode == 17
    assert caught.value.stderr == "original stderr"
    assert store.snapshot() == ()


def test_topology_requires_every_declared_vm_and_retains_boot_identity(monkeypatch):
    profile = SimpleNamespace(required_vms=["caldera", "attacker", "target-base"])
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.load_sut_profile", lambda _: profile
    )
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.normalize_vm_name",
        lambda value: {"target-base": "target-linux-1"}.get(value, value),
    )
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.detect_vagrant_provider", lambda: "qemu"
    )
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.uuid4",
        lambda: SimpleNamespace(hex="topology-nonce"),
    )
    calls = []

    def probe(vm_name, nonce, **kwargs):
        calls.append((vm_name, nonce, kwargs["provider"]))
        return subprocess.CompletedProcess(
            [], 0, f"{nonce}\t{vm_name}\tboot-{vm_name}\n", ""
        )

    monkeypatch.setattr("runners.lab_runtime_bootstrap.probe_vm_identity", probe)

    witness = qualify_declared_lab_topology("0.c0010")

    assert calls == [
        ("caldera", "topology-nonce", "qemu"),
        ("attacker", "topology-nonce", "qemu"),
        ("target-linux-1", "topology-nonce", "qemu"),
    ]
    assert [member.vm_name for member in witness.members] == [
        "caldera",
        "attacker",
        "target-linux-1",
    ]


def test_topology_rejects_a_partial_or_malformed_vm_response(monkeypatch):
    profile = SimpleNamespace(required_vms=["caldera", "attacker"])
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.load_sut_profile", lambda _: profile
    )
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.normalize_vm_name", lambda value: value
    )
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.detect_vagrant_provider", lambda: "qemu"
    )
    monkeypatch.setattr(
        "runners.lab_runtime_bootstrap.uuid4",
        lambda: SimpleNamespace(hex="topology-nonce"),
    )

    def probe(vm_name, nonce, **kwargs):
        output = (
            f"{nonce}\t{vm_name}\tboot-{vm_name}\n" if vm_name == "caldera" else "bad"
        )
        return subprocess.CompletedProcess([], 0, output, "")

    monkeypatch.setattr("runners.lab_runtime_bootstrap.probe_vm_identity", probe)

    with pytest.raises(ValueError, match="malformed"):
        qualify_declared_lab_topology("0.c0010")
