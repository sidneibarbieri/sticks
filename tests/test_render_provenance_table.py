from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts/render_provenance_table.py"
SPEC = importlib.util.spec_from_file_location("render_provenance_table", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


def provenance_record() -> dict:
    return {
        "taxonomy_version": 1,
        "campaign_id": "SYNTHETIC",
        "total_steps": 2,
        "total_binding_occurrences": 4,
        "binding_occurrence_counts": {
            "cti_evidenced": 1,
            "environment_determined": 2,
            "system_introduced": 1,
        },
        "mechanism_counts": {"proposer_chosen": 1},
    }


def test_provenance_and_mechanism_rates_use_distinct_denominators() -> None:
    assert RENDERER._row_cells(provenance_record()) == [
        "SYNTHETIC", "2", "4", "25\\%", "50\\%", "25\\%", "50\\%",
    ]


def test_rendered_tables_disclose_both_denominators() -> None:
    for rendered in (
        RENDERER.render_latex([provenance_record()]),
        RENDERER.render_markdown([provenance_record()]),
    ):
        assert "Binding shares use binding occurrences" in rendered
        assert "mechanism share uses steps" in rendered
    assert "mechanism" in RENDERER.render_latex([provenance_record()])
