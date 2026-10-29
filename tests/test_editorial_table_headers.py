from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


ARTIFACT_ROOT = Path(__file__).resolve().parents[1]


def load_renderer(name: str):
    script = ARTIFACT_ROOT / "scripts" / f"{name}.py"
    specification = importlib.util.spec_from_file_location(name, script)
    assert specification is not None and specification.loader is not None
    renderer = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(renderer)
    return renderer


def table_header(rendered: str) -> str:
    return rendered.split(r"\toprule", 1)[1].split(r"\midrule", 1)[0].strip()


@pytest.mark.parametrize(
    ("renderer_name", "function_name", "columns"),
    [
        ("render_enrichment_baseline_table", "render_latex", 5),
        ("render_execution_commitments_table", "render_latex", 6),
        ("build_fidelity_rationale", "latex_table", 4),
    ],
)
def test_empty_table_headers_have_bold_column_labels(
    renderer_name: str, function_name: str, columns: int
) -> None:
    renderer = load_renderer(renderer_name)
    rendered = getattr(renderer, function_name)([])
    assert table_header(rendered).count(r"\textbf{") == columns


def test_provenance_header_preserves_nested_mechanism_label() -> None:
    renderer = load_renderer("render_provenance_table")
    record = {
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
    rendered = renderer.render_latex([record])
    assert table_header(rendered).count(r"\textbf{") == 7
    assert r"\textbf{\shortstack{Prop.-chosen\\mechanism}}" in rendered
    assert r"SYNTHETIC & 2 & 4 & 25\% & 50\% & 25\% & 50\%" in rendered


def test_admission_header_formats_groups_and_columns_without_changing_rates() -> None:
    renderer = load_renderer("render_admission_comparison_table")
    analysis = {
        "overall": [
            {"arm": arm, "validity_rate": 0.75, "abstention_rate": 0.25}
            for arm in renderer.ARM_ORDER
        ]
    }
    rendered = renderer.render_table(analysis, analysis)
    assert table_header(rendered).count(r"\textbf{") == 8
    assert rendered.count("75.0 & 75.0 & 25.0 & 25.0") == 3


def test_claim_renderer_formats_header_without_writing_frozen_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renderer = load_renderer("render_claim_ledger_table")
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"claims": []}), encoding="utf-8")
    output = tmp_path / "claim_table.tex"
    monkeypatch.setattr(renderer, "LEDGER", ledger)
    monkeypatch.setattr(renderer, "OUTPUT", output)
    monkeypatch.setattr(
        renderer, "verify_ledger", lambda *_arguments: SimpleNamespace(verifications=[])
    )
    assert renderer.main() == 0
    rendered = output.read_text(encoding="utf-8")
    assert table_header(rendered).count(r"\textbf{") == 3
    assert r"\begin{tabularx}{\columnwidth}{@{}llL@{}}" in rendered


@pytest.mark.parametrize(
    ("unit", "population", "expected"),
    [
        ("plan step", "plan step; 25 steps", "plan step; 25 steps"),
        (
            "laboratory shape",
            "laboratory shape; 45 grid points",
            "laboratory shape; 45 grid points",
        ),
        ("plan step", "25 steps", "plan step; 25 steps"),
        ("plan step", "plan steps; 25 steps", "plan step; plan steps; 25 steps"),
        ("plan step", "plan step", "plan step"),
        ("not applicable", "not applicable", "not applicable"),
        ("ATT&CK technique", "697 techniques", "ATT&CK technique; 697 techniques"),
    ],
)
def test_claim_population_description_removes_only_exact_repeated_unit(
    unit: str, population: str, expected: str
) -> None:
    renderer = load_renderer("render_claim_ledger_table")
    assert renderer.population_description(unit, population) == expected


def test_claim_renderer_preserves_population_and_escapes_single_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    renderer = load_renderer("render_claim_ledger_table")
    claim = {
        "claim_id": "STICKS-SYNTHETIC",
        "support_type": "corpus_measurement",
        "unit_of_analysis": "ATT&CK technique",
        "table_population": "ATT&CK technique; 697 techniques",
    }
    ledger = tmp_path / "ledger.json"
    ledger.write_text(json.dumps({"claims": [claim]}), encoding="utf-8")
    output = tmp_path / "claim_table.tex"
    monkeypatch.setattr(renderer, "LEDGER", ledger)
    monkeypatch.setattr(renderer, "OUTPUT", output)
    monkeypatch.setattr(
        renderer,
        "Claim",
        SimpleNamespace(
            model_validate=lambda payload: SimpleNamespace(
                claim_id=payload["claim_id"], model_dump=lambda **_arguments: payload
            )
        ),
    )
    monkeypatch.setattr(
        renderer,
        "verify_ledger",
        lambda *_arguments: SimpleNamespace(
            verifications=[
                SimpleNamespace(claim_id=claim["claim_id"], paper_ready=True)
            ]
        ),
    )
    assert renderer.main() == 0
    rendered = output.read_text(encoding="utf-8")
    assert (
        r"SYNTHETIC & corpus measurement & ATT\&CK technique; 697 techniques"
        in rendered
    )
    assert rendered.count(r"ATT\&CK technique") == 1
