"""The contract-strength guard rejects over-admitting template contracts.

The guard complements the evidence-policy role check: it reads the ``requires`` and
``produces`` shape of each template, not its evidence predicates. The current catalog
must be clean, and each weakness category must fire on a planted template so the guard
is demonstrably not vacuous.
"""

from __future__ import annotations

import json
from pathlib import Path

from concretization.contract_strength import (
    ContractWeakness,
    audit_catalog_contracts,
    audit_template_contract,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def _catalog_templates() -> list[dict]:
    return json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]


def test_current_catalog_has_no_weak_contract() -> None:
    report = audit_catalog_contracts(_catalog_templates())
    assert report.template_count == len(_catalog_templates())
    assert report.unconditioned_effect_templates == []
    assert report.self_satisfying_templates == []
    assert report.clean


def test_every_current_template_declares_a_precondition() -> None:
    # The guard enforces that a produced state is always conditioned on something.
    for template in _catalog_templates():
        audit = audit_template_contract(template)
        assert audit.requires, f"{audit.template_id} produces state with no precondition"
        assert audit.sound


def test_unconditioned_effect_is_detected() -> None:
    planted = {
        "template_id": "planted-unconditioned",
        "requires": [],
        "produces": ["system:domain_admin"],
        "evidence_predicates": ["bounded_effect_observed"],
    }
    audit = audit_template_contract(planted)
    assert ContractWeakness.unconditioned_effect in audit.weaknesses
    assert not audit.sound
    report = audit_catalog_contracts([planted])
    assert report.unconditioned_effect_templates == ["planted-unconditioned"]
    assert not report.clean


def test_self_satisfying_requirement_is_detected() -> None:
    planted = {
        "template_id": "planted-circular",
        "requires": ["host.beachhead", "actor.ready"],
        "produces": ["host.beachhead", "actor.ready", "system:lateral"],
        "evidence_predicates": ["bounded_effect_observed"],
    }
    audit = audit_template_contract(planted)
    assert ContractWeakness.self_satisfying_requirement in audit.weaknesses
    assert not audit.sound
    report = audit_catalog_contracts([planted])
    assert report.self_satisfying_templates == ["planted-circular"]


def test_sound_contract_passes() -> None:
    sound = {
        "template_id": "planted-sound",
        "requires": ["actor.ready"],
        "produces": ["actor.toolkit.ready", "system:toolkit"],
        "evidence_predicates": ["artifact_hash_recorded"],
    }
    audit = audit_template_contract(sound)
    assert audit.weaknesses == []
    assert audit.sound
