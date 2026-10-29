from __future__ import annotations

import hashlib
import json
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
from concretization.fact_semantics import (  # noqa: E402
    EvidenceRequirement,
    FactAssertion,
    FactSemanticDescriptor,
    FactSemanticsRegistry,
    FactUse,
)
from concretization.provider import (  # noqa: E402
    BudgetConfig,
    ProviderConfig,
    ProviderKind,
)
from concretization.stage2_curation import (  # noqa: E402
    BoundaryStatus,
    CurationOutcome,
    Stage2CurationLedger,
    Stage2CurationLimits,
    run_stage2_curation,
)
from concretization.template_overlay import TemplateImplementationWitness  # noqa: E402
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


def _base_template() -> ActionTemplate:
    return ActionTemplate(
        template_id="base-fixture",
        technique_ids=["T1001"],
        execution_domain="target",
        parameter_kinds={"target": "target_host"},
        requires=["sut.ready"],
        produces=["goal.ready", "access.observed"],
        evidence_predicates=["fixture.observed"],
        fidelity_ceiling="adapted",
        description="Exercise a bounded fixture.",
    )


def _fact_semantics() -> FactSemanticsRegistry:
    registry = FactSemanticsRegistry(
        facts=[
            FactSemanticDescriptor(
                fact_id="sut.ready",
                subject="sut",
                predicate="ready",
                assertion=FactAssertion.availability,
                allowed_uses=[FactUse.catalog_initial, FactUse.template_requirement],
                evidence_requirement=EvidenceRequirement.declared_contract,
            ),
            FactSemanticDescriptor(
                fact_id="goal.ready",
                subject="target",
                predicate="goal_ready",
                assertion=FactAssertion.observation,
                allowed_uses=[FactUse.catalog_goal, FactUse.template_effect],
                evidence_requirement=EvidenceRequirement.independent_effect_observation,
            ),
            FactSemanticDescriptor(
                fact_id="access.observed",
                subject="target",
                predicate="access_observed",
                assertion=FactAssertion.access,
                allowed_uses=[FactUse.template_effect],
                evidence_requirement=EvidenceRequirement.independent_effect_observation,
            ),
        ]
    )
    registry.finalize_hash()
    return registry


def _write_replay(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "template_id": "generated-fixture",
                "technique_ids": ["T1001"],
                "execution_domain": "target",
                "parameter_kinds": {"target": "target_host"},
                "requires": ["sut.ready"],
                "produces": ["goal.ready", "access.observed"],
                "evidence_predicates": ["fixture.observed"],
                "fidelity_ceiling": "adapted",
                "description": "Exercise an alternate bounded fixture.",
            }
        ),
        encoding="utf-8",
    )


def _provider_config(replay_path: Path) -> ProviderConfig:
    return ProviderConfig(
        provider=ProviderKind.replay,
        model="replay-fixture",
        api_key_env="UNUSED_REPLAY_KEY",
        replay_path=str(replay_path),
        budget=BudgetConfig(max_requests=2),
    )


def _witness(artifact_root: Path) -> TemplateImplementationWitness:
    implementation = artifact_root / "executor.py"
    implementation.write_text("def execute():\n    return 'observed'\n", encoding="utf-8")
    return TemplateImplementationWitness(
        template_id="generated-fixture",
        executor_id="fixture.execute",
        implementation_path="executor.py",
        implementation_sha256=hashlib.sha256(implementation.read_bytes()).hexdigest(),
        supported_parameter_kinds=["target_host"],
        evidence_predicates=["fixture.observed"],
    )


def _run(
    tmp_path: Path,
    *,
    witnesses: list[TemplateImplementationWitness],
    desired_procedure_assignments_per_step: int = 2,
    desired_behavior_contracts_per_step: int = 2,
    output_name: str = "stage2",
):
    replay_path = tmp_path / "response.json"
    _write_replay(replay_path)
    return run_stage2_curation(
        _plan(),
        _catalog(),
        _fact_semantics(),
        [_base_template()],
        _provider_config(replay_path),
        implementation_witnesses=witnesses,
        artifact_root=tmp_path / "artifact",
        output_dir=tmp_path / output_name,
        limits=Stage2CurationLimits(
            desired_procedure_assignments_per_step=(desired_procedure_assignments_per_step),
            desired_behavior_contracts_per_step=desired_behavior_contracts_per_step,
            maximum_generation_targets=2,
            maximum_realizations=8,
            maximum_search_states=100,
            maximum_candidates_per_step=16,
            maximum_attempts_per_target=1,
        ),
    )


def test_stage2_requires_a_witness_before_a_generated_candidate_changes_search(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()

    result = _run(tmp_path, witnesses=[])

    assert result.ledger.runtime_manual_decision_count == 0
    assert result.baseline_fact_semantic_audit.conformant
    assert result.ledger.provider_request_count == 1
    assert result.ledger.planning_only_candidate_count == 1
    assert result.ledger.implementation_bound_candidate_count == 0
    assert CurationOutcome.planning_only_candidate in result.ledger.outcomes
    assert (
        result.ledger.base_action_catalog_sha256 == result.ledger.post_overlay_action_catalog_sha256
    )
    assert (
        result.post_overlay_realization_space.procedure_assignment_variant_count
        == result.baseline_realization_space.procedure_assignment_variant_count
    )
    witness_boundary = next(
        boundary
        for boundary in result.ledger.boundaries
        if boundary.boundary_id == "implementation_witness"
    )
    assert witness_boundary.status is BoundaryStatus.absent
    assert (tmp_path / "stage2" / "stage2-curation-ledger.json").is_file()
    assert (tmp_path / "stage2" / "baseline-fact-semantics-audit.json").is_file()
    assert (tmp_path / "stage2" / "provider-evidence" / "target-000").is_dir()


def test_stage2_uses_a_valid_witness_without_a_runtime_manual_decision(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()

    result = _run(tmp_path, witnesses=[_witness(artifact_root)])

    assert result.ledger.runtime_manual_decision_count == 0
    assert result.ledger.implementation_bound_candidate_count == 1
    assert CurationOutcome.implementation_bound_candidate in result.ledger.outcomes
    assert (
        result.ledger.base_action_catalog_sha256 != result.ledger.post_overlay_action_catalog_sha256
    )
    assert (
        result.post_overlay_realization_space.procedure_assignment_variant_count
        == result.baseline_realization_space.procedure_assignment_variant_count + 1
    )
    assert (
        result.post_overlay_realization_space.behavior_contract_variant_count
        == result.baseline_realization_space.behavior_contract_variant_count
    )
    stored_ledger = Stage2CurationLedger.model_validate_json(
        (tmp_path / "stage2" / "stage2-curation-ledger.json").read_text(encoding="utf-8")
    )
    assert stored_ledger.validate_hash()


def test_stage2_skips_the_provider_when_the_catalog_meets_the_declared_target(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()

    result = _run(
        tmp_path,
        witnesses=[],
        desired_procedure_assignments_per_step=1,
        desired_behavior_contracts_per_step=1,
    )

    assert result.ledger.proposal_target_count == 0
    assert result.ledger.provider_request_count == 0
    assert result.template_generation_batch.rows == []
    assert result.ledger.outcomes == [CurationOutcome.catalog_sufficient]
    assert (tmp_path / "stage2" / "provider-evidence").is_dir()


def test_stage2_never_overwrites_an_existing_evidence_directory(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifact"
    artifact_root.mkdir()
    _run(tmp_path, witnesses=[])

    with pytest.raises(FileExistsError, match="already exists"):
        _run(tmp_path, witnesses=[])
