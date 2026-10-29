"""Authority dispatch is distinct from retaining arbitrary observation data."""

import json
import subprocess

import pytest

from runners.capability_authority import (
    LabShellRequest,
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import FactScope, ObservationReference
from runners.capability_observations import PredicateObservation, retain_observation


@pytest.mark.parametrize("authority_id,relative_path", [
    ("c0026-archive", "scripts/probe_c0026_target.py"),
    ("c0010-payload", "data/observer_specs/c0010_controller.json"),
    ("c0010-transfer", "scripts/probe_c0010_target.py"),
    ("costaricto-collection", "scripts/probe_costaricto_effects.py"),
])
def test_observer_revision_changes_with_deployed_dependency(monkeypatch, authority_id, relative_path):
    from pathlib import Path
    from runners.capability_authority import registered_authority_revision

    root = Path(__file__).resolve().parents[1]
    selected = root / relative_path
    baseline = registered_authority_revision({authority_id})
    read_bytes = Path.read_bytes

    def changed_bytes(path):
        content = read_bytes(path)
        return content + b"\nchanged probe bytes\n" if path == selected else content

    monkeypatch.setattr(Path, "read_bytes", changed_bytes)
    assert registered_authority_revision({authority_id}) != baseline


def test_observer_revision_rejects_missing_deployed_probe(monkeypatch):
    from pathlib import Path
    from runners.capability_authority import registered_authority_revision

    read_bytes = Path.read_bytes

    def missing_probe(path):
        if path.name == "probe_c0026_target.py":
            raise FileNotFoundError("missing deployed probe")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", missing_probe)
    with pytest.raises(FileNotFoundError, match="missing deployed probe"):
        registered_authority_revision({"c0026-archive"})


def request():
    return LabShellRequest(
        sut_profile_id="0.c0026",
        nonce="nonce-a",
        scope=FactScope(
            run_id="run-a",
            environment_id="lab-a",
            epoch="boot-a",
            locus="target",
            host_id="target-linux-1",
            principal="ubuntu",
        ),
    )


def install_guest_reply(monkeypatch, principal="ubuntu"):
    def probe(sut_profile_id, bash_script, **kwargs):
        assert kwargs["execution_user"] == "ubuntu"
        reply = json.dumps(
            dict(
                hostname="target-linux-1",
                principal=principal,
                boot_id="boot-a",
                nonce="nonce-a",
            )
        )
        return subprocess.CompletedProcess(["probe"], 0, reply, "")

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", probe)


def verify(tmp_path, reference):
    return verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=request().scope,
        expected_predicate="shell-nonce",
    )


def test_registered_adapter_issues_consumable_acquisition(monkeypatch, tmp_path):
    install_guest_reply(monkeypatch)
    reference = acquire_registered_observation(
        "lab-shell", request(), run_root=tmp_path
    )
    observed = verify(tmp_path, reference)
    assert observed.passed is True
    assert observed.established_facts == ("lab:shell",)


def test_storage_receipt_alone_does_not_establish_adapter_authority(tmp_path):
    claimed = PredicateObservation(
        scope=request().scope,
        predicate_id="shell-nonce",
        passed=True,
        established_facts=("lab:shell",),
        details={},
    )
    reference = retain_observation(claimed, authority_id="lab-shell", run_root=tmp_path)
    with pytest.raises((ValueError, FileNotFoundError)):
        verify(tmp_path, reference)


def test_unknown_adapter_is_rejected_without_guest_execution(tmp_path):
    with pytest.raises(ValueError):
        acquire_registered_observation(
            "executor-provided", request(), run_root=tmp_path
        )
    assert list(tmp_path.iterdir()) == []


def test_registered_failed_probe_preserves_failure_without_products(
    monkeypatch, tmp_path
):
    install_guest_reply(monkeypatch, principal="vagrant")
    reference = acquire_registered_observation(
        "lab-shell", request(), run_root=tmp_path
    )
    failed = verify(tmp_path, reference)
    assert failed.passed is False
    assert failed.established_facts == ()


def test_modified_dispatch_receipt_is_refused(monkeypatch, tmp_path):
    install_guest_reply(monkeypatch)
    reference = acquire_registered_observation(
        "lab-shell", request(), run_root=tmp_path
    )
    receipt = tmp_path / "authority_receipts" / reference.record_path.split("/")[1]
    forged = ObservationReference(
        **(reference.model_dump() | {"record_sha256": "b" * 64})
    )
    receipt.write_text(forged.model_dump_json(), encoding="utf-8")
    with pytest.raises(ValueError):
        verify(tmp_path, reference)


def test_symlink_dispatch_receipt_is_refused(monkeypatch, tmp_path):
    install_guest_reply(monkeypatch)
    reference = acquire_registered_observation(
        "lab-shell", request(), run_root=tmp_path
    )
    receipt = tmp_path / "authority_receipts" / reference.record_path.split("/")[1]
    replacement = tmp_path / "elsewhere.json"
    receipt.rename(replacement)
    receipt.symlink_to(replacement)
    with pytest.raises(OSError):
        verify(tmp_path, reference)
