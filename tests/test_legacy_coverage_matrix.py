from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "build_coverage_matrix.py"
LEGACY_CAMPAIGN_IDS = {
    "0.apt41_dust",
    "0.c0010",
    "0.c0026",
    "0.costaricto",
    "0.operation_midnighteclipse",
    "0.outer_space",
    "0.salesforce_data_exfiltration",
    "0.shadowray",
}


def _load_module():
    spec = importlib.util.spec_from_file_location("legacy_coverage_matrix", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_coverage_matrix_resolves_every_campaign_and_executor() -> None:
    module = _load_module()

    rows = module.build_matrix()

    assert {row.sticks_campaign_id for row in rows} == LEGACY_CAMPAIGN_IDS
    assert all(row.campaign_file for row in rows)
    assert all(row.sut_profile for row in rows)
    assert all(row.sticks_techniques > 0 for row in rows)
    assert all(row.executor_coverage == 1.0 for row in rows)


def test_legacy_counts_are_bound_to_retained_technique_occurrences():
    rows = _load_module().build_matrix()

    assert all(row.technique_occurrences_preserved for row in rows)
    assert all(row.docker_techniques == row.sticks_techniques for row in rows)
    assert all(len(row.historical_inventory_sha256) == 64 for row in rows)
    apt41 = next(row for row in rows if row.sticks_campaign_id == "0.apt41_dust")
    assert apt41.docker_techniques == 23
    assert apt41.historical_reported_nodes == 24


def test_executor_registration_is_not_reported_as_effect_evidence():
    module = _load_module()
    rows = module.build_matrix()
    shadowray = next(row for row in rows if row.sticks_campaign_id == "0.shadowray")

    assert any(step.declared_execution_mode == "naive_simulated" for step in shadowray.techniques)
    assert all(step.declared_fidelity for step in shadowray.techniques)
    assert "do not demonstrate" in " ".join(shadowray.divergences)
    assert module.DEFAULT_OUTPUT_DIR == PROJECT_ROOT / "runs/legacy-coverage"


@pytest.mark.parametrize("total,successful", [(10, 1), (1, 1), (0, 1)])
def test_partial_or_inconsistent_receipt_is_not_complete(total, successful):
    module = _load_module()
    row = {
        "campaign_file": True,
        "sut_profile": True,
        "sticks_techniques": 10,
        "latest_execution": {"total": total, "successful": successful, "failed": 0},
    }
    assert module.determine_status(row) == "PARTIAL"


def _complete_runner_row():
    return {
        "campaign_file": True,
        "sut_profile": True,
        "sticks_campaign_id": "0.synthetic",
        "sticks_techniques": 2,
        "expected_techniques": ["T1083", "T1105"],
        "latest_execution": {
            "total": 2, "successful": 2, "failed": 0,
            "campaign_id": "0.synthetic", "sut_profile_id": "0.synthetic",
            "technique_ids": ["T1083", "T1105"],
            "step_statuses": ["success", "success"],
        },
    }


def test_full_receipt_is_complete_only_at_the_runner_boundary():
    assert _load_module().determine_status(_complete_runner_row()) == "COMPLETE"


@pytest.mark.parametrize("field,value", [
    ("total", 2.0), ("successful", 2.0), ("failed", False),
])
def test_noninteger_counts_cannot_qualify_a_complete_receipt(field, value):
    row = _complete_runner_row()
    row["latest_execution"][field] = value
    assert _load_module().determine_status(row) == "PARTIAL"


@pytest.mark.parametrize("value", [True, 2.0, "2", -1])
def test_receipt_parser_rejects_invalid_count_types(tmp_path, value):
    module = _load_module()
    path = tmp_path / "0.synthetic_run" / "summary.json"
    path.parent.mkdir()
    path.write_text(json.dumps({
        "total_techniques": value, "successful": 0, "failed": 0,
    }))

    with pytest.raises(ValueError):
        module.latest_evidence("0.synthetic", evidence_dir=tmp_path)


@pytest.mark.parametrize("field,value", [
    ("campaign_id", "0.other"),
    ("sut_profile_id", "0.other"),
    ("technique_ids", ["T1083", "T1083"]),
    ("technique_ids", ["T1083", "T1057"]),
    ("step_statuses", ["success", "failed"]),
])
def test_equal_counts_cannot_hide_receipt_mismatch(field, value):
    row = _complete_runner_row()
    row["latest_execution"][field] = value
    assert _load_module().determine_status(row) == "PARTIAL"


def test_latest_evidence_preserves_step_and_profile_fields(tmp_path, monkeypatch):
    module = _load_module()
    receipt = tmp_path / "0.synthetic_run" / "summary.json"
    receipt.parent.mkdir()
    receipt.write_text(json.dumps({
        "campaign_id": "0.synthetic", "sut_profile_id": "0.synthetic",
        "total_techniques": 2, "successful": 2, "failed": 0,
        "technique_results": [
            {"technique_id": "T1083", "status": "success"},
            {"technique_id": "T1105", "status": "success"},
        ],
    }))
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path)
    result = module.latest_evidence("0.synthetic")
    assert result.campaign_id == result.sut_profile_id == "0.synthetic"
    assert result.technique_ids == ["T1083", "T1105"]
    assert result.step_statuses == ["success", "success"]


def test_typed_outcome_receipt_is_execution_evidence_but_not_complete(tmp_path, monkeypatch):
    module = _load_module()
    typed_outcomes = tmp_path / "typed_campaign_outcomes"
    typed_outcomes.mkdir()
    (typed_outcomes / "C0010.final_run_receipt.json").write_text(json.dumps({
        "campaign_id": "0.c0010",
        "cycle_passed": True,
        "scope": "one observed guest effect and bounded controller effects",
        "source_tree_sha256": "a" * 64,
        "guest_effects_observed": 1,
        "controller_effects_observed": 4,
        "simulated": 4,
    }))
    monkeypatch.setattr(module, "TYPED_OUTCOMES_DIR", typed_outcomes)
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path / "absent-evidence")

    execution = module.latest_evidence("0.c0010")

    assert execution is not None
    assert execution.evidence_kind == "typed_outcome"
    assert execution.successful == 5
    assert execution.total == 9
    assert execution.failed == 0
    assert module.determine_status({
        "campaign_file": True,
        "sut_profile": True,
        "sticks_campaign_id": "0.c0010",
        "sticks_techniques": 9,
        "expected_techniques": ["T0"] * 9,
        "latest_execution": execution.__dict__,
    }) == "PARTIAL"


def test_markdown_labels_and_bounds_typed_outcomes(tmp_path, monkeypatch):
    module = _load_module()
    typed_outcomes = tmp_path / "typed_campaign_outcomes"
    typed_outcomes.mkdir()
    (typed_outcomes / "C0010.final_run_receipt.json").write_text(json.dumps({
        "campaign_id": "0.c0010",
        "cycle_passed": True,
        "scope": "bounded calibration only",
        "source_tree_sha256": "a" * 64,
        "guest_effects_observed": 1,
        "controller_effects_observed": 4,
        "simulated": 4,
    }))
    monkeypatch.setattr(module, "TYPED_OUTCOMES_DIR", typed_outcomes)
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path / "absent-evidence")
    output_path = tmp_path / "COVERAGE_MATRIX.md"

    module.write_markdown(module.build_matrix(), "2026-10-25T00:00:00", output_path)

    report = output_path.read_text()
    assert "`typed_outcome`" in report
    assert "Bounded Typed-Outcome Scope" in report
    assert "bounded calibration only" in report


def test_legacy_coverage_matrix_writes_to_requested_directory(
    monkeypatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    monkeypatch.setattr(
        sys,
        "argv",
        ["build_coverage_matrix.py", "--output-dir", str(tmp_path)],
    )

    module.main()

    assert (tmp_path / "coverage_matrix.json").exists()
    assert (tmp_path / "COVERAGE_MATRIX.md").exists()


def test_explicit_evidence_directory_does_not_use_default_receipts(tmp_path, monkeypatch):
    module = _load_module()
    default = tmp_path / "default"
    selected = tmp_path / "selected"
    for root, successful in ((default, 0), (selected, 1)):
        receipt = root / "0.c0010_20261012" / "summary.json"
        receipt.parent.mkdir(parents=True)
        receipt.write_text(json.dumps({
            "campaign_id": "0.c0010", "sut_profile_id": "0.c0010",
            "total_techniques": 1, "successful": successful, "failed": 1 - successful,
            "technique_results": [],
        }))
    monkeypatch.setattr(module, "EVIDENCE_DIR", default)
    result = module.latest_evidence("0.c0010", evidence_dir=selected)
    assert result.successful == 1
    assert result.summary_sha256 == hashlib.sha256(
        (selected / "0.c0010_20261012/summary.json").read_bytes()
    ).hexdigest()
    assert module.latest_evidence("0.c0010").successful == 0


def test_evidence_directory_must_exist(tmp_path):
    with pytest.raises(FileNotFoundError):
        _load_module().latest_evidence("0.c0010", evidence_dir=tmp_path / "missing")


def test_absent_default_evidence_remains_an_empty_population(tmp_path, monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "EVIDENCE_DIR", tmp_path / "not-shipped")
    monkeypatch.setattr(module, "TYPED_OUTCOMES_DIR", tmp_path / "not-shipped-typed")
    assert module.latest_evidence("0.c0010") is None
    assert all(row.latest_execution is None for row in module.build_matrix())


def test_evidence_summary_cannot_escape_selected_directory(tmp_path):
    outside = tmp_path / "outside.json"
    outside.write_text("{}")
    root = tmp_path / "selected"
    receipt = root / "0.c0010_20261012/summary.json"
    receipt.parent.mkdir(parents=True)
    receipt.symlink_to(outside)
    with pytest.raises(ValueError, match="escape|symlink"):
        _load_module().latest_evidence("0.c0010", evidence_dir=root)


def test_cli_records_explicit_evidence_population(tmp_path, monkeypatch):
    selected = tmp_path / "selected"
    selected.mkdir()
    output = tmp_path / "report"
    monkeypatch.setattr(sys, "argv", [
        "build_coverage_matrix.py", "--evidence-dir", str(selected),
        "--output-dir", str(output),
    ])
    _load_module().main()
    report = json.loads((output / "coverage_matrix.json").read_text())
    assert report["evidence_directory"] == str(selected)
    assert report["missing"] == 8
    assert all(row["latest_execution"] is None for row in report["campaigns"])


def test_retained_historical_corpus_contains_all_eight_campaigns() -> None:
    script_path = PROJECT_ROOT / "scripts" / "audit_legacy_parity.py"
    spec = importlib.util.spec_from_file_location("legacy_parity_audit", script_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    dag_files = sorted(module.DOCKER_DAG_DIR.glob("*_dag.json"))

    assert module.DOCKER_DAG_DIR.name == "dag"
    assert len(dag_files) == 8


def test_retained_corpus_is_self_contained_and_fails_if_missing(tmp_path: Path) -> None:
    from concretization.legacy_dag_corpus import resolve_legacy_dag_dir

    import pytest

    assert resolve_legacy_dag_dir(PROJECT_ROOT) == PROJECT_ROOT / "data/legacy/dag"
    with pytest.raises(FileNotFoundError, match="historical STICKS DAG corpus not found"):
        resolve_legacy_dag_dir(tmp_path / "isolated-artifact")


def test_parity_audit_writes_only_to_requested_output_directory(monkeypatch, tmp_path):
    script_path = PROJECT_ROOT / "scripts/audit_legacy_parity.py"
    spec = importlib.util.spec_from_file_location("legacy_parity_cli", script_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    monkeypatch.setattr(sys, "argv", [str(script_path), "--output-dir", str(tmp_path)])

    module.main()

    assert (tmp_path / "legacy_parity_report.json").is_file()
    assert (tmp_path / "LEGACY_PARITY_REPORT.md").is_file()
    assert module.DEFAULT_OUTPUT_DIR == PROJECT_ROOT / "runs/legacy-parity"
