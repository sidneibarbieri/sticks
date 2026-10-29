from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import (
    ActionTemplate,
    BindingCatalog,
    BindingValue,
    ProcedureProposal,
)
from concretization.pipeline import concretize_plan
from concretization.prompt import build_prompt
from contracts.procedural_ir import (
    ProcedureStep,
    ProceduralPlan,
    SourceSnapshot,
)


def _plan() -> ProceduralPlan:
    plan = ProceduralPlan(
        campaign_id="C9999",
        campaign_name="Fixture",
        source=SourceSnapshot(
            bundle_sha256="bundle",
            object_count=3,
            campaign_stix_id="campaign--fixture",
            campaign_external_id="C9999",
        ),
        steps=[
            ProcedureStep(
                technique_id="T1190",
                technique_stix_id="attack-pattern--fixture",
                name="Exploit Public-Facing Application",
                execution_domain="boundary",
                tactics=["initial-access"],
                platforms=["Linux"],
                relationship_ids=["relationship--fixture"],
                procedure_descriptions=["The campaign abused an exposed service."],
            )
        ],
    )
    plan.finalize_hash()
    return plan


def _catalog(*, external: bool = False) -> BindingCatalog:
    catalog = BindingCatalog(
        sut_id="sut-fixture",
        source_sha256="source",
        initial_facts=["sut.service.reachable"],
        goal_facts=["access.target.shell"],
        bindings=[
            BindingValue(
                binding_id="actor.primary",
                kind="actor_host",
                value="lab://actor",
                source="sut",
            ),
            BindingValue(
                binding_id="endpoint.primary",
                kind="endpoint",
                value="https://outside.invalid" if external else "lab://target/service",
                source="sut",
                scope="external" if external else "lab",
            ),
            BindingValue(
                binding_id="target.primary",
                kind="target_host",
                value="lab://target",
                source="sut",
            ),
            BindingValue(
                binding_id="credential.fixture",
                kind="credential_source",
                value="secret://sut/fixture",
                source="sut",
                secret_reference=True,
            ),
        ],
    )
    catalog.finalize_hash()
    return catalog


def _template() -> ActionTemplate:
    return ActionTemplate(
        template_id="probe",
        technique_ids=["T1190"],
        execution_domain="boundary",
        parameter_kinds={
            "actor": "actor_host",
            "endpoint": "endpoint",
            "target": "target_host",
        },
        requires=["sut.service.reachable"],
        produces=["access.target.shell"],
        evidence_predicates=["request_logged"],
        fidelity_ceiling="adapted",
        description="Probe the declared service.",
    )


def test_finite_domain_concretization_is_deterministic() -> None:
    first = concretize_plan(_plan(), _catalog(), [_template()])
    second = concretize_plan(_plan(), _catalog(), [_template()])
    assert not first.unresolved_technique_ids
    assert first.content_sha256 == second.content_sha256
    assert first.execution_semantic_sha256 == second.execution_semantic_sha256
    assert first.steps[0].bindings["endpoint"] == "endpoint.primary"
    assert first.planning_certificate is not None
    assert first.planning_certificate.valid
    assert first.planning_certificate.unresolved_goals == []
    assert first.retrieval_traces[0].candidates[0].template_id == "probe"
    assert first.retrieval_traces[0].candidates[0].exact_technique_match


def test_external_llm_binding_is_rejected() -> None:
    proposal = ProcedureProposal(
        technique_id="T1190",
        template_id="probe",
        bindings={
            "actor": "actor.primary",
            "endpoint": "endpoint.primary",
            "target": "target.primary",
        },
        source="llm",
    )
    result = concretize_plan(
        _plan(),
        _catalog(external=True),
        [_template()],
        llm_proposals=[proposal],
    )
    assert result.unresolved_technique_ids == ["T1190"]
    assert any(
        issue.code == "EXTERNAL_BINDING_FORBIDDEN"
        for assessment in result.rejected_candidates
        for issue in assessment.issues
    )


def test_verified_llm_proposal_is_preferred_over_equal_solver_candidate() -> None:
    proposal = ProcedureProposal(
        technique_id="T1190",
        template_id="probe",
        bindings={
            "actor": "actor.primary",
            "endpoint": "endpoint.primary",
            "target": "target.primary",
        },
        source="llm",
    )
    result = concretize_plan(
        _plan(),
        _catalog(),
        [_template()],
        llm_proposals=[proposal],
    )
    assert result.steps[0].proposal_source == "llm"
    deterministic = concretize_plan(_plan(), _catalog(), [_template()])
    assert (
        result.execution_semantic_sha256
        == deterministic.execution_semantic_sha256
    )


def test_prompt_exposes_secret_reference_metadata_not_value() -> None:
    prompt = build_prompt(_plan(), _catalog(), [_template()])
    payload = json.loads(prompt)
    assert "secret://sut/fixture" not in prompt
    secret = next(
        item for item in payload["bindings"] if item["binding_id"] == "credential.fixture"
    )
    assert secret["secret_reference"] is True


def test_causal_planner_reorders_steps_when_source_order_is_not_executable() -> None:
    plan = _plan()
    plan.steps = [
        ProcedureStep(
            technique_id="T1005",
            technique_stix_id="attack-pattern--collect",
            name="Collect",
            execution_domain="target",
            tactics=["collection"],
            platforms=["Linux"],
            relationship_ids=["relationship--collect"],
        ),
        ProcedureStep(
            technique_id="T1190",
            technique_stix_id="attack-pattern--access",
            name="Access",
            execution_domain="boundary",
            tactics=["initial-access"],
            platforms=["Linux"],
            relationship_ids=["relationship--access"],
        ),
    ]
    plan.finalize_hash()
    collect = ActionTemplate(
        template_id="collect",
        technique_ids=["T1005"],
        execution_domain="target",
        parameter_kinds={},
        requires=["access.target.shell"],
        produces=["collection.complete"],
        evidence_predicates=["collection_hash_recorded"],
        fidelity_ceiling="adapted",
        description="Collect a benign fixture.",
    )
    access = _template()
    catalog = _catalog()
    catalog.goal_facts = ["collection.complete"]
    catalog.finalize_hash()
    result = concretize_plan(plan, catalog, [collect, access])
    assert [step.technique_id for step in result.steps] == ["T1190", "T1005"]
    assert result.planning_certificate is not None
    assert result.planning_certificate.valid
