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
)
from concretization.target_queue import build_template_generation_queue  # noqa: E402
from concretization.realization_space import enumerate_realization_space  # noqa: E402
from contracts.procedural_ir import (  # noqa: E402
    ProceduralPlan,
    ProcedureStep,
    SourceSnapshot,
)


def _plan() -> ProceduralPlan:
    plan = ProceduralPlan(
        campaign_id="CTEST",
        campaign_name="Fixture",
        source=SourceSnapshot(
            bundle_sha256="bundle",
            object_count=1,
            campaign_stix_id="campaign--fixture",
            campaign_external_id="CTEST",
        ),
        steps=[
            ProcedureStep(
                technique_id="T1001",
                technique_stix_id="attack-pattern--fixture",
                name="Fixture technique",
                execution_domain="target",
                platforms=["Linux"],
                relationship_ids=["relationship--fixture"],
                procedure_descriptions=["Exercise the declared fixture."],
            )
        ],
    )
    plan.finalize_hash()
    return plan


def _catalog() -> BindingCatalog:
    catalog = BindingCatalog(
        sut_id="sut-fixture",
        source_sha256="source",
        initial_facts=["sut.ready"],
        goal_facts=["goal.ready"],
        bindings=[
            BindingValue(
                binding_id="target.primary",
                kind="target_host",
                value="lab://target-1",
                source="fixture",
            )
        ],
    )
    catalog.finalize_hash()
    return catalog


def _template() -> ActionTemplate:
    return ActionTemplate(
        template_id="existing-fixture",
        technique_ids=["T1001"],
        execution_domain="target",
        parameter_kinds={"target": "target_host"},
        requires=["sut.ready"],
        produces=["goal.ready"],
        evidence_predicates=["fixture.observed"],
        fidelity_ceiling="adapted",
        description="Exercise the bounded fixture.",
    )


def test_queue_derives_hash_bound_campaign_and_sut_context() -> None:
    result = build_template_generation_queue(
        _plan(),
        _catalog(),
        [_template()],
        desired_behavior_contracts_per_step=2,
        maximum_targets=4,
    )

    assert result.total_procedure_assignment_deficit == 1
    assert result.total_behavior_contract_deficit == 1
    assert result.selected_target_count == 1
    assert result.unselected_procedure_assignment_deficit == 0
    assert result.operational_status == "not_run"
    target = result.targets[0]
    assert target.target_id == "CTEST:0:T1001:v1"
    assert target.context is not None
    assert target.context.validate_hash()
    assert target.context.admissible_required_facts == ["sut.ready"]
    assert target.context.admissible_produced_facts == ["goal.ready"]
    assert target.context.available_binding_kinds == ["target_host"]
    assert target.context.existing_template_ids == ["existing-fixture"]
    assert len(target.context.admissible_behavior_contracts) == 1


def test_queue_reports_unselected_deficit_under_target_budget() -> None:
    result = build_template_generation_queue(
        _plan(),
        _catalog(),
        [_template()],
        desired_procedure_assignments_per_step=4,
        desired_behavior_contracts_per_step=4,
        maximum_targets=1,
    )

    assert result.total_procedure_assignment_deficit == 3
    assert result.total_behavior_contract_deficit == 3
    assert result.selected_target_count == 1
    assert result.unselected_procedure_assignment_deficit == 2
    assert result.needs[0].requested_additional_procedure_assignment_count == 3
    assert result.needs[0].unmet_behavior_contract_count == 3
    assert result.needs[0].selected_target_count == 1


def test_queue_is_deterministic() -> None:
    first = build_template_generation_queue(_plan(), _catalog(), [_template()])
    second = build_template_generation_queue(_plan(), _catalog(), [_template()])

    assert first.content_sha256 == second.content_sha256


def test_queue_rejects_tampered_realization_space() -> None:
    plan = _plan()
    catalog = _catalog()
    templates = [_template()]
    space = enumerate_realization_space(plan, catalog, templates)
    space.realization_count = 99

    with pytest.raises(ValueError, match="realization space hash mismatch"):
        build_template_generation_queue(
            plan,
            catalog,
            templates,
            realization_space=space,
        )
