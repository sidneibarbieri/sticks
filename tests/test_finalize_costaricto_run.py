"""CostaRicto final receipts require bound guest checks and conservative rows."""

import hashlib
import json
from pathlib import Path

import pytest

from scripts import finalize_isolated_lab_run as finalizer
from scripts.run_isolated_lab_campaign import sha256_file, tree_manifest, write_json


ARTIFACT_ROOT = Path(__file__).resolve().parents[1]


def make_run(tmp_path: Path) -> Path:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    profile = workspace / "data/sut_profiles/0.costaricto.yml"
    profile.parent.mkdir(parents=True)
    profile.write_text("requirements:\n  required_vms: [caldera, attacker, target-linux-1]\n")
    for machine in ("caldera", "attacker", "target-linux-1"):
        vm_dir = workspace / "lab/vagrant" / machine
        vm_dir.mkdir(parents=True)
        (vm_dir / "Vagrantfile").write_text("# fixture\n")

    campaign_path = workspace / "campaigns/0.costaricto.json"
    campaign_path.parent.mkdir(parents=True)
    campaign_path.write_bytes((ARTIFACT_ROOT / "campaigns/0.costaricto.json").read_bytes())
    probe_path = workspace / "scripts/probe_costaricto_target.py"
    probe_path.parent.mkdir(parents=True)
    probe_path.write_bytes((ARTIFACT_ROOT / "scripts/probe_costaricto_target.py").read_bytes())
    source_entries = [
        {"path": relative, "sha256": sha256_file(workspace / relative)}
        for relative in ("campaigns/0.costaricto.json", "scripts/probe_costaricto_target.py")
    ]
    write_json(run_root / "source_manifest.json", {
        "tree_sha256": "source-digest", "files": source_entries,
    })

    artifacts = workspace / "data/artifacts"
    artifacts.mkdir(parents=True)
    write_json(run_root / "artifact_manifest.json", tree_manifest(artifacts))
    campaign = json.loads(campaign_path.read_text())
    rows = []
    for step in campaign["techniques"]:
        products = ["simulation:record"] if step["expected_mode"] == "naive_simulated" else []
        if step["technique_id"] == "T1588.002":
            products = ["simulation:guest_tool_staged"]
        if step["technique_id"] == "T1005":
            products = ["collection:local_data"]
        rows.append({
            "technique_id": step["technique_id"], "execution_mode": step["expected_mode"],
            "fidelity": {"declared": step["expected_fidelity"], "verified": None},
            "status": "success",
            "executor_name": "executors.fixture", "capabilities_produced": products,
        })
    evidence = run_root / "evidence"
    summary_path = evidence / "0.costaricto_fixture/summary.json"
    summary_path.parent.mkdir(parents=True)
    write_json(summary_path, {
        "campaign_id": "0.costaricto", "total_techniques": 10,
        "successful": 10, "failed": 0, "skipped": 0,
        "technique_results": rows,
    })
    evidence_manifest = tree_manifest(evidence)
    write_json(run_root / "evidence_manifest.json", evidence_manifest)
    write_json(run_root / "run_context.json", {
        "campaign_id": "0.costaricto", "exit_code": 0,
        "keep_lab_requested": True, "source_tree_sha256": "source-digest",
        "evidence_tree_sha256": evidence_manifest["tree_sha256"],
        "artifact_tree_sha256": tree_manifest(artifacts)["tree_sha256"],
    })

    checks = {name: True for name in finalizer.COSTARICTO_CHECKS}
    observation = {
        "schema": "costaricto-bounded-guest-observation/v1",
        "hostname": "target-linux-1", "observer_uid": 0,
        "boot_id": "synthetic-boot", "checks": checks, "passed": True,
        "file_sha256": {
            "collection_source": "a" * 64, "collection_copy": "a" * 64,
            "tool_source": "b" * 64, "tool_copy": "b" * 64,
            "benign_payload": finalizer.COSTARICTO_PAYLOAD_SHA256,
        },
        "scope": finalizer.COSTARICTO_SCOPE,
    }
    probe_sha256 = sha256_file(probe_path)
    write_json(evidence / "costaricto-target-observation.transport.json", {
        "exit_code": 0, "stdout": json.dumps(observation), "stderr": "",
        "probe_sha256": probe_sha256,
    })
    write_json(evidence / "costaricto-target-observation.json", {
        "schema": "costaricto-target-observer-receipt/v1",
        "campaign_id": "0.costaricto", "source_tree_sha256": "source-digest",
        "probe_sha256": probe_sha256, "observation": observation,
    })
    return run_root


def refresh_initial_evidence(run_root: Path) -> None:
    manifest_path = run_root / "evidence_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    digest = hashlib.sha256()
    for entry in sorted(manifest["files"], key=lambda item: item["path"]):
        path = run_root / "evidence" / entry["path"]
        entry["sha256"] = sha256_file(path)
        entry["size"] = path.stat().st_size
        digest.update(entry["path"].encode() + b"\0" + entry["sha256"].encode() + b"\0")
    manifest["tree_sha256"] = digest.hexdigest()
    write_json(manifest_path, manifest)
    context_path = run_root / "run_context.json"
    context = json.loads(context_path.read_text())
    context["evidence_tree_sha256"] = manifest["tree_sha256"]
    write_json(context_path, context)


def test_costaricto_receipt_binds_runner_guest_and_teardown(tmp_path, monkeypatch):
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")

    receipt = finalizer.build_receipt(run_root)

    assert receipt["campaign_id"] == "0.costaricto"
    assert receipt["runner_successful"] == 10
    assert all(receipt["observer_checks"].values())
    assert set(receipt["vm_states"].values()) == {"not_created"}
    assert receipt["scope"] == finalizer.COSTARICTO_SCOPE


@pytest.mark.parametrize("mutation", ["transport_failure", "wrong_probe", "missing_check", "non_root", "wrong_payload_hash"])
def test_costaricto_rejects_unbound_or_incomplete_guest_observation(tmp_path, monkeypatch, mutation):
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    evidence = run_root / "evidence"
    transport_path = evidence / "costaricto-target-observation.transport.json"
    receipt_path = evidence / "costaricto-target-observation.json"
    transport = json.loads(transport_path.read_text())
    receipt = json.loads(receipt_path.read_text())
    if mutation == "transport_failure":
        transport["exit_code"] = 4
    elif mutation == "wrong_probe":
        receipt["probe_sha256"] = "wrong"
    else:
        if mutation == "missing_check":
            del receipt["observation"]["checks"]["known_benign_payload_present"]
        elif mutation == "wrong_payload_hash":
            receipt["observation"]["file_sha256"]["benign_payload"] = "c" * 64
        else:
            receipt["observation"]["observer_uid"] = 1000
        transport["stdout"] = json.dumps(receipt["observation"])
    write_json(transport_path, transport)
    write_json(receipt_path, receipt)

    with pytest.raises(ValueError, match="CostaRicto"):
        finalizer.build_receipt(run_root)


@pytest.mark.parametrize("mutation", ["tool_promoted", "fake_discovery", "wrong_mode", "wrong_fidelity", "wrong_order"])
def test_costaricto_rejects_runner_contract_mismatch(tmp_path, monkeypatch, mutation):
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    summary_path = run_root / "evidence/0.costaricto_fixture/summary.json"
    summary = json.loads(summary_path.read_text())
    rows = summary["technique_results"]
    if mutation == "tool_promoted":
        next(row for row in rows if row["technique_id"] == "T1588.002")["capabilities_produced"] = ["resources:tool_acquired"]
    elif mutation == "fake_discovery":
        next(row for row in rows if row["technique_id"] == "T1005")["capabilities_produced"].append("discovery:file_listing")
    elif mutation == "wrong_mode":
        next(row for row in rows if row["technique_id"] == "T1588.002")["execution_mode"] = "real_controlled"
    elif mutation == "wrong_fidelity":
        next(row for row in rows if row["technique_id"] == "T1588.002")["fidelity"]["declared"] = "adapted"
    else:
        rows[0], rows[1] = rows[1], rows[0]
    write_json(summary_path, summary)
    refresh_initial_evidence(run_root)

    with pytest.raises(ValueError, match="CostaRicto"):
        finalizer.build_receipt(run_root)


def test_costaricto_requires_all_declared_vms_destroyed(tmp_path, monkeypatch):
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "running")

    with pytest.raises(ValueError, match="not all been destroyed"):
        finalizer.build_receipt(run_root)
