from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pytest  # noqa: E402

from concretization.models import BindingCatalog  # noqa: E402
from evaluation.provenance import BINDING_SOURCE_CLASSES, classify_binding  # noqa: E402
from evaluation.provenance_conformance import audit_source_coverage  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
CAMPAIGNS = ("C0010", "C0026", "C0045")


def test_every_documented_source_classifies():
    for source, expected in BINDING_SOURCE_CLASSES.items():
        assert classify_binding(source) is expected


def test_unknown_source_fails_closed():
    # Fail-closed: an unrecognized source raises rather than defaulting to a class.
    with pytest.raises(ValueError):
        classify_binding("surprise")


def test_unknown_source_is_flagged_by_the_audit():
    coverage = audit_source_coverage([{"binding_id": "b", "source": "surprise"}])
    assert coverage.unknown_sources == ["surprise"]
    assert coverage.conformant is False
    assert "surprise" not in coverage.observed_sources


def _all_catalog_bindings() -> list[dict]:
    bindings: list[dict] = []
    for campaign_id in CAMPAIGNS:
        catalog = BindingCatalog.model_validate_json(
            (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
        )
        bindings.extend(catalog.model_dump(mode="json")["bindings"])
    return bindings


def test_real_catalogs_are_conformant():
    coverage = audit_source_coverage(_all_catalog_bindings())
    assert coverage.conformant is True
    assert coverage.unknown_sources == []
    # Every source in the real data is a documented one.
    assert set(coverage.observed_sources).issubset(set(BINDING_SOURCE_CLASSES))
