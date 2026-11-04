"""The CostaRicto prior-work comparison record is recomputable from the frozen private receipt.

The committed public record must be exactly what the campaign builder regenerates from the frozen
paired collection, show no truncated generation, and show that both arms realized the two
real-controlled effects. When the private evidence is absent (a public clone), regeneration is
skipped; the record's internal consistency is still checked.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RECORD = PROJECT_ROOT / "release" / "experiments" / "prior_work_comparison" / "costaricto_paired.json"
BUILDER = PROJECT_ROOT / "scripts" / "build_prior_work_campaign_evidence.py"
PRIVATE_ROOT = (
    PROJECT_ROOT.parents[2] / "_private" / "experiments" / "STICKS_P17_COSTARICTO_PAIRED_20261104"
)


def _builder_module():
    spec = importlib.util.spec_from_file_location("build_prior_work_campaign_evidence", BUILDER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="utf-8"))


def test_record_regenerates_byte_for_byte() -> None:
    if not (PRIVATE_ROOT / "receipt.json").is_file():
        pytest.skip("frozen private receipt is absent (public clone)")
    payload = _builder_module().build_payload(PRIVATE_ROOT)
    regenerated = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    assert regenerated == RECORD.read_text(encoding="utf-8")


def test_no_generation_was_truncated() -> None:
    record = _record()
    assert record["prior_work_generations_truncated"] == 0
    assert record["prior_work_generation_stop_reasons"].get("stop") == (
        record["prior_work_generations_total"]
    )


def test_both_arms_realize_both_real_controlled_effects() -> None:
    record = _record()
    assert record["campaign_id"] == "0.costaricto"
    assert record["real_controlled_steps"] == 2
    assert record["admitted_observed_steps"] == 2
    assert record["prior_work_observed_steps"] == 2
    assert record["prior_work_fully_failed_techniques"] == []


def test_cell_counts_are_consistent() -> None:
    record = _record()
    assert record["cells_total"] == record["cells_per_arm"] * 2
    for arm in ("admitted", "prior_work_style"):
        for step_id in ("s1", "s9"):
            summary = record["arms"][arm][step_id]
            assert summary["target_observed"] + summary["failed"] == record["cells_per_arm"]
