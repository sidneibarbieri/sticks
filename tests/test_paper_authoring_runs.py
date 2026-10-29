"""Manuscript macros must not silently incorporate exploratory authoring runs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_renderer():
    spec = importlib.util.spec_from_file_location(
        "render_paper_macros", PROJECT_ROOT / "scripts" / "render_paper_macros.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_run(root: Path, run_id: str, status: str = "admitted") -> None:
    run_root = root / "stage2_authoring" / "runs" / run_id
    run_root.mkdir(parents=True)
    summary = {
        "run_id": run_id,
        "attempted_techniques": 1,
        "admitted_templates": int(status == "admitted"),
        "combined_reach_steps": 9,
        "total_steps": 10,
    }
    decision = {
        "technique_id": "T1005",
        "status": status,
        "rejection_code": None if status == "admitted" else "malformed_schema",
    }
    (run_root / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    (run_root / "decisions.jsonl").write_text(json.dumps(decision) + "\n", encoding="utf-8")


def test_new_exploratory_run_cannot_change_paper_macros(tmp_path, monkeypatch):
    renderer = _load_renderer()
    monkeypatch.setattr(renderer, "EXPERIMENTS", tmp_path)
    monkeypatch.setattr(renderer, "PAPER_AUTHORING_RUNS", ("first", "second"))
    _write_run(tmp_path, "first")
    _write_run(tmp_path, "second")
    before = renderer._isolated_authoring_runs()

    _write_run(tmp_path, "exploratory", status="rejected")

    assert renderer._isolated_authoring_runs() == before
    assert before["runs"] == "2"


def test_disagreeing_verdicts_fail_even_when_summary_counts_agree(tmp_path, monkeypatch):
    renderer = _load_renderer()
    monkeypatch.setattr(renderer, "EXPERIMENTS", tmp_path)
    monkeypatch.setattr(renderer, "PAPER_AUTHORING_RUNS", ("first", "second"))
    _write_run(tmp_path, "first")
    _write_run(tmp_path, "second")
    decision_path = tmp_path / "stage2_authoring" / "runs" / "second" / "decisions.jsonl"
    decision = json.loads(decision_path.read_text(encoding="utf-8"))
    decision["technique_id"] = "T1006"
    decision_path.write_text(json.dumps(decision) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="disagree on decisions"):
        renderer._isolated_authoring_runs()
