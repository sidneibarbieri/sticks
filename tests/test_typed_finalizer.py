"""Typed finalization binds runtime acquisitions to the independent guest chain."""

import shutil
import hashlib
import json

import pytest

from scripts import finalize_isolated_lab_run as finalizer
from scripts.run_isolated_lab_campaign import tree_manifest, write_json
from tests.test_finalize_isolated_lab_run import make_run
from tests.test_typed_runtime_seal import prepared


def make_typed_run(tmp_path, monkeypatch):
    payload, records, sources, _ = prepared(tmp_path / "typed", monkeypatch)
    run_root = make_run(tmp_path)
    workspace = run_root / "workspace"
    shutil.copytree(sources, workspace, dirs_exist_ok=True)
    evidence = run_root / "evidence"
    legacy = evidence / "0.c0026_001"
    (legacy / "summary.json").unlink()
    legacy.rmdir()
    destination = evidence / "runtime-v2" / payload["run_id"]
    shutil.copytree(records, destination)
    observer_path = evidence / "c0026-target-observation.json"
    observer_path.unlink()
    transport_path = evidence / "c0026-target-observation.transport.json"
    transport_path.unlink()
    initial = tree_manifest(evidence)
    source_manifest = tree_manifest(workspace)
    write_json(run_root / "evidence_manifest.json", initial)
    write_json(run_root / "source_manifest.json", source_manifest)
    artifacts = tree_manifest(workspace / "data/artifacts")
    write_json(
        run_root / "run_context.json",
        {
            "campaign_id": "0.c0026",
            "exit_code": 0,
            "keep_lab_requested": True,
            "source_tree_sha256": source_manifest["tree_sha256"],
            "evidence_tree_sha256": initial["tree_sha256"],
            "artifact_tree_sha256": artifacts["tree_sha256"],
        },
    )
    observation = {
        "schema": "c0026-target-chain-observation/v1",
        "hostname": "target-linux-1",
        "boot_id": "boot-a",
        "observer_uid": 0,
        "chunk_count": 2,
        "scope": "Synthetic guest fixture chain",
        "passed": True,
        "collection_sha256": "a" * 64,
        "archive_sha256": "b" * 64,
        "checks": {
            "collection_matches_declared_sources": True,
            "archive_contains_collection": True,
            "chunks_reassemble_archive": True,
            "dynamic_resolution_recorded": True,
            "benign_transfer_retained": True,
        },
    }
    probe_sha256 = hashlib.sha256(
        (workspace / "scripts/probe_c0026_target.py").read_bytes()
    ).hexdigest()
    write_json(transport_path, {
        "exit_code": 0, "stdout": json.dumps(observation), "stderr": "",
        "probe_sha256": probe_sha256,
    })
    write_json(observer_path, {
        "schema": "c0026-target-observer-receipt/v1",
        "campaign_id": "0.c0026",
        "source_tree_sha256": source_manifest["tree_sha256"],
        "probe_sha256": probe_sha256,
        "observation": observation,
    })
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    return run_root, observation


def test_typed_final_receipt_separates_observed_and_simulated(monkeypatch, tmp_path):
    run_root, _ = make_typed_run(tmp_path, monkeypatch)
    receipt = finalizer.build_receipt(run_root)
    assert receipt["schema"] == "isolated-lab-final-receipt/v2"
    assert receipt["runner_effects_observed"] == 5
    assert receipt["runner_simulated"] == 1
    assert receipt["runner_total_techniques"] == 6
    assert "runner_successful" not in receipt
    assert receipt["cycle_passed"] is True


@pytest.mark.parametrize("alteration", ["boot", "digest", "missing_check"])
def test_typed_finalizer_rejects_unbound_guest_observation(
    monkeypatch, tmp_path, alteration
):
    run_root, observation = make_typed_run(tmp_path, monkeypatch)
    if alteration == "boot":
        observation["boot_id"] = "another-boot"
    elif alteration == "digest":
        observation["collection_sha256"] = "f" * 64
    else:
        observation["checks"].pop("chunks_reassemble_archive")
    receipt_path = run_root / "evidence/c0026-target-observation.json"
    receipt = finalizer.read_json(receipt_path)
    receipt["observation"] = observation
    write_json(receipt_path, receipt)
    transport_path = run_root / "evidence/c0026-target-observation.transport.json"
    transport = finalizer.read_json(transport_path)
    transport["stdout"] = json.dumps(observation)
    write_json(transport_path, transport)
    with pytest.raises(ValueError, match="Independent C0026"):
        finalizer.build_receipt(run_root)


def test_typed_layout_cannot_downgrade_to_legacy_summary(monkeypatch, tmp_path):
    run_root, _ = make_typed_run(tmp_path, monkeypatch)
    _, payload = finalizer.runner_summary(run_root / "evidence", "0.c0026")
    payload["schema_version"] = "runtime-campaign/v1"
    payload.update(successful=6, skipped=0)
    summary_path = run_root / "evidence/runtime-v2" / payload["run_id"] / "summary.json"
    write_json(summary_path, payload)
    observer_path = run_root / "evidence/c0026-target-observation.json"
    observer = finalizer.read_json(observer_path)
    transport_path = run_root / "evidence/c0026-target-observation.transport.json"
    transport = finalizer.read_json(transport_path)
    observer_path.unlink()
    transport_path.unlink()
    initial = tree_manifest(run_root / "evidence")
    write_json(run_root / "evidence_manifest.json", initial)
    context = finalizer.read_json(run_root / "run_context.json")
    context["evidence_tree_sha256"] = initial["tree_sha256"]
    write_json(run_root / "run_context.json", context)
    write_json(observer_path, observer)
    write_json(transport_path, transport)
    with pytest.raises(ValueError, match="layout"):
        finalizer.build_receipt(run_root)
