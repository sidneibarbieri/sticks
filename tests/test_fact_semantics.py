from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.fact_semantics import (  # noqa: E402
    EvidenceRequirement,
    FactAssertion,
    FactSemanticDescriptor,
    FactSemanticsRegistry,
    FactUse,
    audit_fact_semantics,
    build_fact_semantics_coverage_report,
)
from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402

REGISTRY_PATH = PROJECT_ROOT / "data" / "concretization" / "fact_semantics.json"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
PLANS_DIR = PROJECT_ROOT / "release" / "plans"


def _registry() -> FactSemanticsRegistry:
    return FactSemanticsRegistry.model_validate_json(REGISTRY_PATH.read_text(encoding="utf-8"))


def _templates() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


def _catalog(name: str) -> BindingCatalog:
    return BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{name}.binding-catalog.json").read_text(encoding="utf-8")
    )


def test_versioned_registry_covers_every_fact_in_the_evaluated_deep_slice() -> None:
    registry = _registry()
    report = build_fact_semantics_coverage_report(
        registry,
        [_catalog("C0010"), _catalog("C0026"), _catalog("C0045")],
        _templates(),
    )

    assert registry.validate_hash()
    assert len(registry.facts) == 54
    assert report.conformant
    assert report.audited_sut_count == 3
    assert report.conformant_sut_count == 3
    assert report.validate_hash()
    assert all(audit.conformant for audit in report.audits)
    assert all(audit.claim_boundary.startswith("does_not_establish") for audit in report.audits)


def test_registry_rejects_two_identifiers_with_the_same_semantic_identity() -> None:
    descriptor = {
        "subject": "target",
        "predicate": "shell_access",
        "assertion": FactAssertion.access,
        "allowed_uses": [FactUse.template_effect],
        "evidence_requirement": EvidenceRequirement.independent_effect_observation,
    }

    with pytest.raises(ValidationError, match="duplicate semantic identities"):
        FactSemanticsRegistry(
            facts=[
                FactSemanticDescriptor(fact_id="access.shell.one", **descriptor),
                FactSemanticDescriptor(fact_id="access.shell.two", **descriptor),
            ]
        )


def test_audit_reports_an_unregistered_fact_without_converting_it_to_a_valid_state() -> None:
    registry = _registry()
    catalog = BindingCatalog(
        sut_id="fixture",
        source_sha256="fixture",
        initial_facts=["unregistered.fact"],
    )
    catalog.finalize_hash()

    audit = audit_fact_semantics(registry, catalog, [])

    assert not audit.conformant
    assert audit.unregistered_fact_ids == ["unregistered.fact"]
    assert audit.use_violations == []
    assert audit.validate_hash()


def test_audit_reports_a_known_fact_when_its_origin_is_not_permitted() -> None:
    registry = FactSemanticsRegistry(
        facts=[
            FactSemanticDescriptor(
                fact_id="fixture.fact",
                subject="fixture",
                predicate="declared_state",
                assertion=FactAssertion.availability,
                allowed_uses=[FactUse.catalog_initial],
                evidence_requirement=EvidenceRequirement.declared_contract,
            )
        ]
    )
    registry.finalize_hash()
    catalog = BindingCatalog(
        sut_id="fixture",
        source_sha256="fixture",
        goal_facts=["fixture.fact"],
    )
    catalog.finalize_hash()

    audit = audit_fact_semantics(registry, catalog, [])

    assert not audit.conformant
    assert audit.unregistered_fact_ids == []
    assert len(audit.use_violations) == 1
    assert audit.use_violations[0].use is FactUse.catalog_goal
