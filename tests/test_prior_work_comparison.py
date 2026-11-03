"""The prior-work comparison record is recomputable from the frozen private receipt.

The committed public record must be exactly what the builder regenerates from the frozen paired
collection, show no truncated generation, and show the measured per-arm step contrast. When the
private evidence is absent (a public clone), regeneration is skipped; the record's internal
consistency is still checked.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECORD = PROJECT_ROOT / "release" / "experiments" / "prior_work_comparison" / "c0026_paired.json"
BUILDER = PROJECT_ROOT / "scripts" / "build_prior_work_comparison_evidence.py"


def _builder_module():
    spec = importlib.util.spec_from_file_location("build_prior_work_comparison_evidence", BUILDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_record_regenerates_byte_for_byte() -> None:
    module = _builder_module()
    if not (module.DEFAULT_PRIVATE_ROOT / "receipt.json").is_file():
        pytest.skip("frozen private receipt is absent (public clone)")
    payload = module.build_payload(module.DEFAULT_PRIVATE_ROOT)
    regenerated = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert regenerated == RECORD.read_text(encoding="utf-8")


def test_no_generation_was_truncated() -> None:
    record = _record()
    assert record["prior_work_generations_truncated"] == 0
    assert record["prior_work_generation_stop_reasons"].get("stop") == (
        record["prior_work_generations_total"]
    )


def test_admitted_realizes_every_step_prior_work_misses_one() -> None:
    record = _record()
    assert record["admitted_observed_steps"] == record["real_controlled_steps"]
    assert record["prior_work_observed_steps"] == record["real_controlled_steps"] - 1
    assert record["prior_work_failed_technique"] == "T1030"
    assert record["prior_work_failed_cells"] == record["cells_per_arm"]


def test_both_arms_have_the_same_cell_count() -> None:
    record = _record()
    assert record["cells_total"] == record["cells_per_arm"] * 2
    for arm in ("admitted", "prior_work_style"):
        for step_id in ("s2", "s3", "s4", "s5", "s6"):
            summary = record["arms"][arm][step_id]
            assert summary["target_observed"] + summary["failed"] == record["cells_per_arm"]
