from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.claim_numerals import (
    Accessor,
    ClaimQuantity,
    NumericExemption,
    Reduction,
    Rendering,
    audit_numerals,
    prose_literals,
    renderable_values,
    resolve_quantity,
)


def _write(root: Path, relative: str, payload: dict) -> str:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return relative


def test_prose_literals_ignores_identifier_tokens():
    prose = ["C0045 step T1105 admitted 3 of 25 steps under P16 and STICKS-P08"]
    assert prose_literals(prose) == {"3", "25"}


def test_renderable_values_covers_counts_rates_and_list_lengths():
    document = {"total": 55, "rate": 0.2198952879581152, "rows": [1, 2, 3]}
    written = renderable_values(document)
    assert "55" in written
    assert "22.0" in written
    assert "3" in written


def test_total_sums_a_field_across_documents(tmp_path):
    paths = [
        _write(tmp_path, "a.json", {"commitments": 32}),
        _write(tmp_path, "b.json", {"commitments": 47}),
    ]
    quantity = ClaimQuantity(literal="79", reduction=Reduction.total, evidence_paths=paths,
                             field_paths=["commitments"])
    assert resolve_quantity(quantity, tmp_path) == "79"


def test_total_sums_several_fields_in_one_document(tmp_path):
    path = _write(tmp_path, "corpus.json", {"full": 2, "partial": 44})
    quantity = ClaimQuantity(literal="46", reduction=Reduction.total, evidence_paths=[path],
                             field_paths=["full", "partial"])
    assert resolve_quantity(quantity, tmp_path) == "46"


def test_length_accessor_counts_list_entries(tmp_path):
    paths = [
        _write(tmp_path, "one.json", {"steps": [0] * 9}),
        _write(tmp_path, "two.json", {"steps": [0] * 16}),
    ]
    quantity = ClaimQuantity(literal="25", reduction=Reduction.total, evidence_paths=paths,
                             field_paths=["steps"], accessor=Accessor.length)
    assert resolve_quantity(quantity, tmp_path) == "25"


def test_document_count_reports_the_evaluated_population(tmp_path):
    paths = [_write(tmp_path, f"{name}.json", {}) for name in ("a", "b", "c")]
    quantity = ClaimQuantity(literal="3", reduction=Reduction.document_count, evidence_paths=paths)
    assert resolve_quantity(quantity, tmp_path) == "3"


def test_percent_rendering_uses_the_declared_precision(tmp_path):
    path = _write(tmp_path, "rates.json", {"share": 0.4591104734576757})
    quantity = ClaimQuantity(literal="45.9", reduction=Reduction.total, evidence_paths=[path],
                             field_paths=["share"], rendering=Rendering.percent, decimals=1)
    assert resolve_quantity(quantity, tmp_path) == "45.9"


def test_a_stale_number_is_reported_as_unbound(tmp_path):
    path = _write(tmp_path, "corpus.json", {"campaigns": 55, "steps": 1146})
    audit = audit_numerals(
        claim_id="STICKS-P08",
        prose=["Across 51 campaigns containing 1019 steps"],
        quantities=[],
        exemptions=[],
        evidence_paths=[path],
        project_root=tmp_path,
    )
    assert audit.unbound_literals == ["51", "1019"]
    assert not audit.clean


def test_current_numbers_resolve_against_their_evidence(tmp_path):
    path = _write(tmp_path, "corpus.json", {"campaigns": 55, "steps": 1146})
    audit = audit_numerals(
        claim_id="STICKS-P08",
        prose=["Across 55 campaigns containing 1146 steps"],
        quantities=[],
        exemptions=[],
        evidence_paths=[path],
        project_root=tmp_path,
    )
    assert audit.clean


def test_a_quantity_may_not_read_outside_the_claim_evidence_chain(tmp_path):
    inside = _write(tmp_path, "inside.json", {"value": 1})
    outside = _write(tmp_path, "outside.json", {"value": 7})
    quantity = ClaimQuantity(literal="7", reduction=Reduction.total, evidence_paths=[outside],
                             field_paths=["value"])
    audit = audit_numerals(
        claim_id="STICKS-P99",
        prose=["the reduction reports 7 units"],
        quantities=[quantity],
        exemptions=[],
        evidence_paths=[inside],
        project_root=tmp_path,
    )
    assert audit.quantity_mismatches == [
        "7 reads documents outside the claim's evidence chain: outside.json"
    ]


def test_a_declaration_the_prose_never_uses_is_reported(tmp_path):
    path = _write(tmp_path, "corpus.json", {"value": 7})
    quantity = ClaimQuantity(literal="7", reduction=Reduction.total, evidence_paths=[path],
                             field_paths=["value"])
    audit = audit_numerals(
        claim_id="STICKS-P99",
        prose=["the property states no number at all"],
        quantities=[quantity],
        exemptions=[],
        evidence_paths=[path],
        project_root=tmp_path,
    )
    assert audit.unused_declarations == ["7"]


def test_an_exemption_covers_a_declared_configuration_value(tmp_path):
    path = _write(tmp_path, "corpus.json", {"steps": 25})
    audit = audit_numerals(
        claim_id="STICKS-P15",
        prose=["25 steps sampled at temperature 0.7"],
        quantities=[],
        exemptions=[NumericExemption(literal="0.7", justification="declared sampling temperature")],
        evidence_paths=[path],
        project_root=tmp_path,
    )
    assert audit.clean


def test_total_without_a_field_path_is_rejected():
    with pytest.raises(ValueError, match="requires at least one field path"):
        ClaimQuantity(literal="1", reduction=Reduction.total, evidence_paths=["a.json"])


def test_document_count_with_a_field_path_is_rejected():
    with pytest.raises(ValueError, match="takes no field paths"):
        ClaimQuantity(
            literal="1",
            reduction=Reduction.document_count,
            evidence_paths=["a.json"],
            field_paths=["x"],
        )
