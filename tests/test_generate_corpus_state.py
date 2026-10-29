from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = PROJECT_ROOT / "scripts" / "generate_corpus_state.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("sticks_generate_corpus_state", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_missing_release_evidence_directory_returns_no_summary(tmp_path: Path) -> None:
    module = _load_module()
    module.EVIDENCE_DIR = tmp_path / "release" / "evidence"

    assert module.EVIDENCE_DIR.exists() is False
    assert module.evidence_dirs_for_campaign("0.shadowray") == []
    assert module.latest_summary("0.shadowray") is None


def _isolated_report_module(tmp_path: Path):
    module = _load_module()
    module.CAMPAIGNS_DIR = tmp_path / "campaigns"
    module.CAMPAIGNS_DIR.mkdir()
    (module.CAMPAIGNS_DIR / "example.json").write_text("{}")
    module.SUT_DIR = tmp_path / "sut"
    module.EVIDENCE_DIR = tmp_path / "evidence"
    module.PARITY_REPORT = tmp_path / "parity.json"
    module.MITRE_AUDIT = tmp_path / "mitre.json"
    module.HOST_LEAKAGE = tmp_path / "audit.json"
    return module


def _write_summary(module, total: int = 1):
    directory = module.EVIDENCE_DIR / "example_20261010_030000"
    directory.mkdir(parents=True)
    summary_path = directory / "summary.json"
    summary_path.write_text(json.dumps({"total_techniques": total, "successful": total, "failed": 0}))
    return summary_path


def test_missing_audit_is_unknown_and_empty_execution_is_not_success(tmp_path: Path) -> None:
    module = _isolated_report_module(tmp_path)
    _write_summary(module, total=0)
    report = module.build_report()
    assert report["campaigns_without_host_leakage"] == 0
    assert report["campaigns_with_zero_failed_in_latest_evidence"] == 0
    assert report["campaigns"][0]["host_leakage_detected"] is None
    output_path = tmp_path / "state.md"
    module.write_markdown(report, output_path)
    assert "not assessed" in output_path.read_text()


def test_current_digest_is_required_for_clean_audit(tmp_path: Path) -> None:
    module = _isolated_report_module(tmp_path)
    summary_path = _write_summary(module)
    audit = {"campaign_id": "example", "latest_summary": str(summary_path),
             "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
             "host_leakage_detected": False}
    module.HOST_LEAKAGE.write_text(json.dumps({"campaigns": [audit]}))
    report = module.build_report()
    assert report["campaigns_without_host_leakage"] == 1
    assert report["campaigns_with_bound_host_leakage_audit"] == 1
    assert report["campaigns"][0]["latest_execution"]["evidence_scope"] == "runner_report_only"
    summary_path.write_text(json.dumps({"total_techniques": 2, "successful": 2, "failed": 0}))
    stale_report = module.build_report()
    assert stale_report["campaigns_without_host_leakage"] == 0
    assert stale_report["campaigns"][0]["host_leakage_audit_status"] == "unverified_summary_digest"


def test_explicit_audit_input_and_runtime_output(tmp_path: Path, monkeypatch) -> None:
    module = _isolated_report_module(tmp_path)
    summary_path = _write_summary(module)
    audit_path = tmp_path / "runtime-audit.json"
    audit_path.write_text(json.dumps({"campaigns": [{"campaign_id": "example",
        "latest_summary": str(summary_path),
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "host_leakage_detected": True}]}))
    output_dir = tmp_path / "runtime-output"
    monkeypatch.setattr(sys, "argv", [str(MODULE_PATH), "--output-dir", str(output_dir),
                                      "--host-leakage-audit", str(audit_path)])
    module.main()
    report = json.loads((output_dir / "corpus_state.json").read_text())
    assert report["campaigns"][0]["host_leakage_detected"] is True
    assert "not assessed" not in (output_dir / "CORPUS_STATE.md").read_text()
    assert module.OUTPUT_DIR == PROJECT_ROOT / "runs" / "corpus-state"
