"""The joined campaign table must agree with the three tables it summarizes."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPERIMENTS = PROJECT_ROOT / "release" / "experiments"
SCRIPT = PROJECT_ROOT / "scripts" / "render_campaign_summary_table.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("render_campaign_summary_table", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


summary = _load_module()


def _rows_of(table: Path) -> dict[str, list[str]]:
    body = table.read_text(encoding="utf-8").split(r"\midrule", 1)[1]
    rows = {}
    for line in body.splitlines():
        cells = [cell.strip() for cell in line.rstrip("\\ ").split("&")]
        if len(cells) > 1 and re.fullmatch(r"C\d{4}", cells[0]):
            rows[cells[0]] = cells
    return rows


def _record(kind: str, campaign_id: str, suffix: str) -> dict:
    return json.loads((EXPERIMENTS / kind / f"{campaign_id}.{suffix}.json").read_text())


@pytest.mark.parametrize("campaign_id", summary.DEFAULT_CAMPAIGNS)
def test_every_cell_matches_the_separate_tables(campaign_id: str) -> None:
    row = summary.load_row(EXPERIMENTS, campaign_id)
    baseline = _rows_of(EXPERIMENTS / "enrichment_baseline" / "baseline_table.tex")[campaign_id]
    commitments = _rows_of(EXPERIMENTS / "execution_commitments" / "commitments_table.tex")[campaign_id]
    provenance = _rows_of(EXPERIMENTS / "provenance" / "provenance_table.tex")[campaign_id]

    admitted = [str(row.steps), f"{row.raw_admitted}/{row.steps}", f"{row.enriched_admitted}/{row.steps}"]
    assert admitted == baseline[1:4]
    assert str(row.bindings) == provenance[2]
    assert [str(row.commitments), str(row.pruned_candidates)] == commitments[4:6]


def test_records_from_different_campaigns_are_rejected() -> None:
    with pytest.raises(ValueError, match="different campaigns"):
        summary.CampaignSummaryRow.from_records(
            baseline=_record("enrichment_baseline", "C0010", "baseline"),
            provenance=_record("provenance", "C0026", "provenance"),
            commitments=_record("execution_commitments", "C0010", "commitments"),
        )


def test_provenance_that_does_not_sum_is_rejected() -> None:
    with pytest.raises(ValidationError, match="does not sum"):
        summary.CampaignSummaryRow(
            campaign_id="C9999", steps=1, raw_admitted=0, enriched_admitted=1,
            bindings=3, cti_bindings=0, environment_bindings=1, system_bindings=1,
            mechanism_commitments=1, binding_commitments=3, pruned_candidates=0,
        )
