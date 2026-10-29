from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/audit_host_leakage.py"


def load_auditor():
    spec = importlib.util.spec_from_file_location("host_leakage_audit", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_evidence_is_unknown(monkeypatch, tmp_path):
    module = load_auditor()
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path)

    row = module.audit_campaign("campaign")

    assert row["has_evidence"] is False
    assert row["host_leakage_detected"] is None
    assert row["summary_sha256"] is None


def test_declared_local_execution_is_detected_and_bound(monkeypatch, tmp_path):
    module = load_auditor()
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path)
    run_dir = tmp_path / "campaign_20261010_000000"
    run_dir.mkdir()
    summary = {"technique_results": [
        {"technique_id": "T1105", "host": "localhost", "stdout": "", "stderr": ""},
        {"technique_id": "T1005", "host": "target-linux-1", "stdout": "Darwin Kernel Version"},
    ]}
    raw = json.dumps(summary).encode()
    (run_dir / "summary.json").write_bytes(raw)

    row = module.audit_campaign("campaign")

    assert row["host_leakage_detected"] is True
    assert row["summary_sha256"] == hashlib.sha256(raw).hexdigest()
    assert row["leaked_steps"][0]["patterns"] == ["declared_local_host"]
    assert set(row["leaked_steps"][1]["patterns"]) == {"darwin_kernel", "darwin_uname"}


def test_target_without_markers_has_limited_negative_result(monkeypatch, tmp_path):
    module = load_auditor()
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path)
    run_dir = tmp_path / "campaign_20261010_000000"
    run_dir.mkdir()
    (run_dir / "summary.json").write_text(json.dumps({"technique_results": [
        {"host": "target-linux-1", "stdout": "completed"},
    ]}))

    row = module.audit_campaign("campaign")

    assert row["host_leakage_detected"] is False
    assert row["audit_scope"] == "retained_summary_markers_and_declared_hosts"


def test_cli_writes_in_requested_runtime_directory(monkeypatch, tmp_path):
    module = load_auditor()
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path / "no-evidence")
    monkeypatch.setattr(sys, "argv", [str(SCRIPT_PATH), "--output-dir", str(tmp_path)])

    module.main()

    assert (tmp_path / "host_leakage_audit.json").is_file()
    assert (tmp_path / "HOST_LEAKAGE_AUDIT.md").is_file()
    assert module.DEFAULT_OUTPUT_DIR == SCRIPT_PATH.parents[1] / "runs/host-leakage-audit"
