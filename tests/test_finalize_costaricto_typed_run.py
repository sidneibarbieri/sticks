"""A typed CostaRicto seal admits the declared observer files and nothing else."""

import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import finalize_isolated_lab_run as finalizer
from scripts import typed_runtime_seal
from scripts.run_isolated_lab_campaign import sha256_file, tree_manifest, write_json
from tests.test_finalize_costaricto_run import make_run

RUN_ID = "0123456789abcdef0123456789abcdef"


def make_typed_run(tmp_path: Path, monkeypatch) -> Path:
    run_root = make_run(tmp_path)
    evidence = run_root / "evidence"
    observer = {name: (evidence / name).read_bytes() for name in finalizer.OBSERVATION_FILES["0.costaricto"]}
    for name in observer:
        (evidence / name).unlink()
    shutil.rmtree(evidence / "0.costaricto_fixture")
    summary = evidence / "runtime-v2" / RUN_ID / "summary.json"
    summary.parent.mkdir(parents=True)
    write_json(summary, {"schema_version": "runtime-campaign/v2", "campaign_id": "0.costaricto",
                         "run_id": RUN_ID})
    (run_root / "execution.log").write_text("runner output\n")
    initial = tree_manifest(evidence)
    write_json(run_root / "evidence_manifest.json", initial)
    context = json.loads((run_root / "run_context.json").read_text())
    context.update(evidence_tree_sha256=initial["tree_sha256"], execution_log_path="execution.log",
                   execution_log_sha256=sha256_file(run_root / "execution.log"))
    write_json(run_root / "run_context.json", context)
    for name, content in observer.items():  # the observer writes after the runner manifest
        (evidence / name).write_bytes(content)

    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    monkeypatch.setattr(finalizer, "_verify_typed_source_manifest",
                        lambda root, _: json.loads((root / "source_manifest.json").read_text()))
    monkeypatch.setattr(typed_runtime_seal, "validate_costaricto_typed_completion",
                        lambda *_: SimpleNamespace(campaign_id="0.costaricto", run_id=RUN_ID,
                                                   effects_observed=3, simulated=7))
    return run_root


def test_typed_seal_binds_the_independent_observation(tmp_path, monkeypatch):
    run_root = make_typed_run(tmp_path, monkeypatch)
    receipt = finalizer.build_receipt(run_root)
    assert receipt["schema"] == "isolated-costaricto-typed-receipt/v1"
    assert receipt["cycle_passed"] is True
    assert receipt["observer_checks"] and all(receipt["observer_checks"].values())
    assert receipt["observer_transport_path"] == "evidence/costaricto-target-observation.transport.json"
    assert receipt["final_evidence_tree_sha256"] != receipt["evidence_tree_sha256"]


def test_typed_seal_rejects_changed_runner_evidence(tmp_path, monkeypatch):
    run_root = make_typed_run(tmp_path, monkeypatch)
    summary = run_root / "evidence/runtime-v2" / RUN_ID / "summary.json"
    summary.write_text(summary.read_text() + " ")
    with pytest.raises(ValueError, match="changed after its manifest"):
        finalizer.build_receipt(run_root)


def test_typed_seal_rejects_an_undeclared_evidence_file(tmp_path, monkeypatch):
    run_root = make_typed_run(tmp_path, monkeypatch)
    (run_root / "evidence/extra.json").write_text("{}")
    with pytest.raises(ValueError, match="Unexpected independent observation files"):
        finalizer.build_receipt(run_root)


def test_typed_seal_rejects_an_unbound_observation(tmp_path, monkeypatch):
    run_root = make_typed_run(tmp_path, monkeypatch)
    transport = run_root / "evidence/costaricto-target-observation.transport.json"
    data = json.loads(transport.read_text())
    data["exit_code"] = 1
    write_json(transport, data)
    with pytest.raises(ValueError, match="not bound"):
        finalizer.build_receipt(run_root)
