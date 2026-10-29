from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.behavioral_structure import (  # noqa: E402
    campaign_technique_sets,
    curveball,
    families,
    measure,
    summarize,
)


def _technique(stix_id: str, attack_id: str) -> dict:
    return {
        "type": "attack-pattern",
        "id": stix_id,
        "external_references": [{"source_name": "mitre-attack", "external_id": attack_id}],
    }


def _uses(source: str, target: str, **extra: object) -> dict:
    return {"type": "relationship", "relationship_type": "uses", "source_ref": source, "target_ref": target, **extra}


def test_sets_keep_only_active_campaigns_and_active_links() -> None:
    bundle = {"objects": [
        _technique("ap--1", "T1005"), _technique("ap--2", "T1083"),
        {"type": "campaign", "id": "campaign--a"},
        {"type": "campaign", "id": "campaign--b", "revoked": True},
        {"type": "campaign", "id": "campaign--c"},
        _uses("campaign--a", "ap--1"), _uses("campaign--a", "ap--2", revoked=True),
        _uses("campaign--b", "ap--2"),
    ]}
    assert campaign_technique_sets(bundle) == [frozenset({"T1005"})]


def test_curveball_preserves_set_sizes_and_item_frequencies() -> None:
    sets = [frozenset("abc"), frozenset("cd"), frozenset("ade"), frozenset("b")]
    shuffled = curveball(sets, swaps=200, rng=random.Random(1))
    assert [len(row) for row in shuffled] == [len(row) for row in sets]
    assert Counter(item for row in shuffled for item in row) == Counter(item for row in sets for item in row)


def test_identical_campaigns_form_one_family() -> None:
    sets = [frozenset("ab"), frozenset("ab"), frozenset("xy")]
    assert families(sets) == 1
    assert summarize(sets).family_share == pytest.approx(2 / 3)


def test_the_measurement_is_seeded() -> None:
    sets = [frozenset("abc"), frozenset("bcd"), frozenset("cde"), frozenset("ae")]
    assert measure(sets, null_draws=20, swaps=50) == measure(sets, null_draws=20, swaps=50)


def test_a_single_campaign_is_refused() -> None:
    with pytest.raises(ValueError, match="at least two"):
        summarize([frozenset("a")])
