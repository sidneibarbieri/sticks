from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import (  # noqa: E402
    ActionTemplate,
    BindingCatalog,
    BindingValue,
    ProcedureProposal,
)
from concretization.realization_space import (  # noqa: E402
    EnumerationStatus,
    enumerate_realization_space,
)
from contracts.procedural_ir import (  # noqa: E402
    ProceduralPlan,
    ProcedureStep,
    SourceSnapshot,
)


def _step(index: int, technique_id: str, *, execution_domain: str = "target") -> ProcedureStep:
    return ProcedureStep(
        technique_id=technique_id,
        technique_stix_id=f"attack-pattern--{index}",
        name=f"Step {index}",
        execution_domain=execution_domain,
        relationship_ids=[f"relationship--{index}"],
    )


def _plan(steps: list[ProcedureStep]) -> ProceduralPlan:
    plan = ProceduralPlan(
        campaign_id="CTEST",
        campaign_name="Fixture",
        source=SourceSnapshot(
            bundle_sha256="bundle",
            object_count=len(steps),
            campaign_stix_id="campaign--fixture",
            campaign_external_id="CTEST",
        ),
        steps=steps,
    )
    plan.finalize_hash()
    return plan


def _catalog(*, initial_facts: list[str], goal_facts: list[str]) -> BindingCatalog:
    catalog = BindingCatalog(
        sut_id="sut-fixture",
        source_sha256="source",
        initial_facts=initial_facts,
        goal_facts=goal_facts,
        bindings=[
            BindingValue(
                binding_id="target.primary",
                kind="target_host",
                value="lab://target-1",
                source="sut",
            )
        ],
    )
    catalog.finalize_hash()
    return catalog


def _template(
    template_id: str,
    technique_id: str,
    *,
    requires: list[str],
    produces: list[str],
    fidelity_ceiling: str = "adapted",
) -> ActionTemplate:
    return ActionTemplate(
        template_id=template_id,
        technique_ids=[technique_id],
        execution_domain="target",
        parameter_kinds={"target": "target_host"},
        requires=requires,
        produces=produces,
        evidence_predicates=[f"{template_id}.observed"],
        fidelity_ceiling=fidelity_ceiling,
        description=f"Benign fixture for {template_id}.",
    )


def test_enumerates_multiple_procedures_for_one_technique() -> None:
    plan = _plan([_step(0, "T1001")])
    catalog = _catalog(initial_facts=["sut.ready"], goal_facts=["goal.ready"])
    templates = [
        _template("procedure-a", "T1001", requires=["sut.ready"], produces=["goal.ready"]),
        _template(
            "procedure-b",
            "T1001",
            requires=["sut.ready"],
            produces=["goal.ready"],
            fidelity_ceiling="inspired",
        ),
    ]

    result = enumerate_realization_space(plan, catalog, templates)

    assert result.enumeration_status == EnumerationStatus.exhaustive
    assert result.realization_count == 2
    assert result.procedure_assignment_variant_count == 2
    assert result.behavior_contract_variant_count == 2
    assert result.causal_structure_variant_count == 1
    assert result.graph_variant_count == 2
    assert result.operational_status == "not_run"
    assert result.step_realization_coverage[0].candidate_count == 2
    assert result.step_realization_coverage[0].realized_procedure_assignment_count == 2
    assert result.step_realization_coverage[0].realized_behavior_contract_count == 2
    assert result.step_realization_coverage[0].realized_template_ids == [
        "procedure-a",
        "procedure-b",
    ]
    assert [item.plan.steps[0].template_id for item in result.realizations] == [
        "procedure-a",
        "procedure-b",
    ]


def test_causal_facts_force_an_order_different_from_source_order() -> None:
    plan = _plan([_step(0, "T2002"), _step(1, "T2001")])
    catalog = _catalog(initial_facts=["sut.ready"], goal_facts=["goal.ready"])
    templates = [
        _template("consume", "T2002", requires=["access.ready"], produces=["goal.ready"]),
        _template("produce", "T2001", requires=["sut.ready"], produces=["access.ready"]),
    ]

    result = enumerate_realization_space(plan, catalog, templates)

    assert result.realization_count == 1
    realization = result.realizations[0]
    assert realization.source_step_order == [1, 0]
    assert [
        (edge.producer_sequence, edge.consumer_sequence) for edge in realization.graph.edges
    ] == [
        (0, 1),
        (1, 2),
    ]


def test_independent_steps_create_distinct_topological_orders() -> None:
    plan = _plan([_step(0, "T3001"), _step(1, "T3002")])
    catalog = _catalog(
        initial_facts=["sut.ready"],
        goal_facts=["first.ready", "second.ready"],
    )
    templates = [
        _template("first", "T3001", requires=["sut.ready"], produces=["first.ready"]),
        _template("second", "T3002", requires=["sut.ready"], produces=["second.ready"]),
    ]

    result = enumerate_realization_space(plan, catalog, templates)

    assert result.realization_count == 2
    assert result.ordering_variant_count == 2
    assert result.causal_structure_variant_count == 1
    assert result.graph_variant_count == 2
    assert {tuple(item.source_step_order) for item in result.realizations} == {(0, 1), (1, 0)}


def test_search_limit_is_reported_instead_of_claiming_completeness() -> None:
    plan = _plan([_step(0, "T4001"), _step(1, "T4002"), _step(2, "T4003")])
    catalog = _catalog(
        initial_facts=["sut.ready"],
        goal_facts=["one.ready", "two.ready", "three.ready"],
    )
    templates = [
        _template("one", "T4001", requires=["sut.ready"], produces=["one.ready"]),
        _template("two", "T4002", requires=["sut.ready"], produces=["two.ready"]),
        _template("three", "T4003", requires=["sut.ready"], produces=["three.ready"]),
    ]

    result = enumerate_realization_space(plan, catalog, templates, maximum_realizations=2)

    assert result.enumeration_status == EnumerationStatus.bounded
    assert result.realization_count == 2
    assert not result.search_exhausted
    assert result.truncation_reason == "maximum_realizations"


def test_depth_first_search_finds_a_deep_witness_before_expanding_all_prefixes() -> None:
    steps = [_step(index, f"T45{index:02d}") for index in range(8)]
    plan = _plan(steps)
    goal_facts = [f"step-{index}.ready" for index in range(8)]
    catalog = _catalog(initial_facts=["sut.ready"], goal_facts=goal_facts)
    templates = [
        _template(
            f"procedure-{index}",
            step.technique_id,
            requires=["sut.ready"],
            produces=[goal_facts[index]],
        )
        for index, step in enumerate(steps)
    ]

    result = enumerate_realization_space(
        plan,
        catalog,
        templates,
        maximum_realizations=1,
        maximum_search_states=9,
    )

    assert result.realization_count == 1
    assert result.maximal_realized_steps == 8
    assert result.enumeration_status == EnumerationStatus.bounded


def test_procedure_diversity_is_seeded_before_ordering_variants() -> None:
    plan = _plan([_step(0, "T4601"), _step(1, "T4602")])
    catalog = _catalog(
        initial_facts=["sut.ready"],
        goal_facts=["first.ready", "second.ready"],
    )
    templates = [
        _template("first-a", "T4601", requires=["sut.ready"], produces=["first.ready"]),
        _template("first-b", "T4601", requires=["sut.ready"], produces=["first.ready"]),
        _template("second", "T4602", requires=["sut.ready"], produces=["second.ready"]),
    ]

    result = enumerate_realization_space(
        plan,
        catalog,
        templates,
        maximum_realizations=2,
    )

    assert result.realization_count == 2
    assert result.procedure_assignment_variant_count == 2
    assert result.behavior_contract_variant_count == 2
    assert result.seeded_realization_count == 2
    assert result.step_realization_coverage[0].realized_procedure_assignment_count == 2
    assert {
        tuple(step.template_id for step in item.plan.steps) for item in result.realizations
    } == {("first-a", "second"), ("first-b", "second")}


def test_missing_candidate_produces_auditable_abstention() -> None:
    plan = _plan([_step(0, "T5001")])
    catalog = _catalog(initial_facts=["sut.ready"], goal_facts=["goal.ready"])

    result = enumerate_realization_space(plan, catalog, [])

    assert result.enumeration_status == EnumerationStatus.no_admissible_realization
    assert result.realization_count == 0
    assert result.dead_end_technique_ids == ["T5001"]
    assert {(item.code, item.count) for item in result.blocker_counts} == {("NO_CANDIDATE", 1)}


def test_output_and_ranking_are_deterministic() -> None:
    plan = _plan([_step(0, "T6001"), _step(1, "T6002")])
    catalog = _catalog(
        initial_facts=["sut.ready"],
        goal_facts=["one.ready", "two.ready"],
    )
    templates = [
        _template("one", "T6001", requires=["sut.ready"], produces=["one.ready"]),
        _template("two", "T6002", requires=["sut.ready"], produces=["two.ready"]),
    ]

    first = enumerate_realization_space(plan, catalog, templates)
    second = enumerate_realization_space(plan, catalog, list(reversed(templates)))

    assert first.content_sha256 == second.content_sha256
    assert [item.content_sha256 for item in first.realizations] == [
        item.content_sha256 for item in second.realizations
    ]


def test_supplied_proposal_for_unknown_technique_is_not_silently_ignored() -> None:
    plan = _plan([_step(0, "T7001")])
    catalog = _catalog(initial_facts=["sut.ready"], goal_facts=["goal.ready"])
    proposal = ProcedureProposal(
        technique_id="T9999",
        template_id="unknown",
        bindings={},
        source="llm",
    )

    with pytest.raises(ValueError, match="do not map"):
        enumerate_realization_space(plan, catalog, [], supplied_proposals=[proposal])


def test_catalog_hash_validation_does_not_repair_tampered_input() -> None:
    catalog = _catalog(initial_facts=["sut.ready"], goal_facts=["goal.ready"])
    expected_hash = catalog.content_sha256
    catalog.sut_id = "tampered"

    assert not catalog.validate_hash()
    assert not catalog.validate_hash()
    assert catalog.content_sha256 == expected_hash
