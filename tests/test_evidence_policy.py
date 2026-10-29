from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.evidence_policy import (
    PredicateRole,
    audit_catalog,
    audit_template,
    load_roles,
)

ROLES = {
    "artifact_hash_recorded": PredicateRole.effect,
    "no_external_transfer": PredicateRole.safety,
    "process_exit_recorded": PredicateRole.liveness,
}


def _template(template_id: str, predicates: list[str]) -> dict:
    return {"template_id": template_id, "evidence_predicates": predicates}


def test_a_policy_observing_a_produced_state_certifies_the_effect():
    audit = audit_template("stage-payload", ["artifact_hash_recorded"], ROLES)
    assert audit.certifies_declared_effect


def test_safety_assertions_alone_do_not_certify_an_effect():
    audit = audit_template("stage-payload", ["no_external_transfer"], ROLES)
    assert not audit.certifies_declared_effect
    assert audit.safety_predicates == ["no_external_transfer"]


def test_process_exit_alone_does_not_certify_an_effect():
    audit = audit_template("stage-payload", ["process_exit_recorded"], ROLES)
    assert not audit.certifies_declared_effect
    assert audit.liveness_predicates == ["process_exit_recorded"]


def test_an_unregistered_predicate_blocks_certification():
    audit = audit_template("stage-payload", ["artifact_hash_recorded", "mystery"], ROLES)
    assert audit.unregistered_predicates == ["mystery"]
    assert not audit.certifies_declared_effect


def test_safety_predicates_are_kept_alongside_the_effect():
    audit = audit_template(
        "stage-payload", ["artifact_hash_recorded", "no_external_transfer"], ROLES
    )
    assert audit.certifies_declared_effect
    assert audit.safety_predicates == ["no_external_transfer"]


def test_catalog_report_names_the_templates_that_fail():
    report = audit_catalog(
        [
            _template("good", ["artifact_hash_recorded"]),
            _template("safety-only", ["no_external_transfer"]),
            _template("exit-only", ["process_exit_recorded"]),
        ],
        ROLES,
    )
    assert report.template_count == 3
    assert report.effect_certified_count == 1
    assert report.safety_only_templates == ["safety-only"]
    assert report.liveness_only_templates == ["exit-only"]
    assert not report.clean


def test_every_released_template_certifies_a_produced_state():
    roles = load_roles(PROJECT_ROOT / "data/concretization/evidence_predicate_roles.json")
    catalog = json.loads(
        (PROJECT_ROOT / "data/concretization/action_templates.json").read_text(encoding="utf-8")
    )
    report = audit_catalog(catalog["templates"], roles)
    assert report.clean
    assert report.effect_certified_count == report.template_count


def test_every_catalog_predicate_has_exactly_one_declared_role():
    roles = load_roles(PROJECT_ROOT / "data/concretization/evidence_predicate_roles.json")
    catalog = json.loads(
        (PROJECT_ROOT / "data/concretization/action_templates.json").read_text(encoding="utf-8")
    )
    used = {
        predicate
        for template in catalog["templates"]
        for predicate in template["evidence_predicates"]
    }
    assert used <= set(roles)
    assert set(roles) - used == set()


def test_an_unknown_role_value_is_rejected():
    with pytest.raises(ValueError):
        PredicateRole("decorative")
