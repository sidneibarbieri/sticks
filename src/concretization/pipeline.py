"""Concretize a STICKS plan through bounded search and deterministic verification."""

from __future__ import annotations

import hashlib
import json

from contracts.procedural_ir import ProceduralPlan

from .models import (
    ActionTemplate,
    BindingCatalog,
    CandidateAssessment,
    ConcretizedPlan,
    ConcretizedStep,
    ProcedureProposal,
)
from .planning import certify_plan
from .retrieval import retrieve_templates
from .solver import enumerate_candidates
from .verifier import assess_candidate, choose_candidate


def action_catalog_hash(templates: list[ActionTemplate]) -> str:
    payload = [template.model_dump(mode="json") for template in templates]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def concretize_plan(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    *,
    llm_proposals: list[ProcedureProposal] | None = None,
) -> ConcretizedPlan:
    if not plan.validate_hash():
        raise ValueError("source procedural plan hash mismatch")
    if not catalog.validate_hash():
        raise ValueError("binding catalog hash mismatch")

    template_index = {template.template_id: template for template in templates}
    proposals_by_technique: dict[str, list[ProcedureProposal]] = {}
    for proposal in llm_proposals or []:
        proposals_by_technique.setdefault(proposal.technique_id, []).append(proposal)

    known_facts = set(catalog.initial_facts)
    concrete_steps: list[ConcretizedStep] = []
    rejected: list[CandidateAssessment] = []
    unresolved: list[str] = []
    retrieval_traces = []
    retrieved_by_technique = {}
    for step in plan.steps:
        retrieved_templates, retrieval_trace = retrieve_templates(
            step, templates
        )
        retrieval_traces.append(retrieval_trace)
        retrieved_by_technique[step.technique_id] = retrieved_templates

    pending = list(plan.steps)
    while pending:
        selected_transition = None
        round_rejections: list[CandidateAssessment] = []
        for source_position, step in enumerate(pending):
            candidates = (
                proposals_by_technique.get(step.technique_id, [])
                + enumerate_candidates(
                    step,
                    retrieved_by_technique[step.technique_id],
                    catalog,
                )
            )
            assessments = [
                assess_candidate(
                    proposal,
                    technique_id=step.technique_id,
                    execution_domain=step.execution_domain,
                    templates=template_index,
                    catalog=catalog,
                    known_facts=known_facts,
                )
                for proposal in candidates
            ]
            selected = choose_candidate(assessments)
            round_rejections.extend(
                assessment
                for assessment in assessments
                if not assessment.accepted
            )
            if selected is not None:
                selected_transition = (source_position, step, selected)
                break
        rejected.extend(round_rejections)
        if selected_transition is None:
            unresolved.extend(step.technique_id for step in pending)
            break
        source_position, step, selected = selected_transition
        pending.pop(source_position)
        template = template_index[selected.proposal.template_id]
        concrete_steps.append(
            ConcretizedStep(
                sequence=len(concrete_steps) + 1,
                technique_id=step.technique_id,
                template_id=template.template_id,
                bindings=selected.proposal.bindings,
                requires=template.requires,
                produces=template.produces,
                evidence_predicates=template.evidence_predicates,
                fidelity_ceiling=template.fidelity_ceiling,
                proposal_source=selected.proposal.source,
                assumption_count=selected.assumption_count,
            )
        )
        known_facts.update(template.produces)

    result = ConcretizedPlan(
        campaign_id=plan.campaign_id,
        source_plan_sha256=plan.content_sha256,
        binding_catalog_sha256=catalog.content_sha256,
        action_catalog_sha256=action_catalog_hash(templates),
        steps=concrete_steps,
        unresolved_technique_ids=unresolved,
        rejected_candidates=rejected,
        retrieval_traces=retrieval_traces,
        planning_certificate=certify_plan(
            concrete_steps,
            initial_facts=catalog.initial_facts,
            goal_facts=catalog.goal_facts,
        ),
    )
    result.finalize_hash()
    return result
