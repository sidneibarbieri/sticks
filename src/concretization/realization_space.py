"""Enumerate a bounded family of causally admissible procedure realizations."""

from __future__ import annotations

import hashlib
import itertools
import json
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from pydantic import Field

from contracts.procedural_ir import ProceduralPlan, ProcedureStep

from .models import (
    ActionTemplate,
    BindingCatalog,
    CandidateAssessment,
    CausalLink,
    ConcretizedPlan,
    ConcretizedStep,
    ProcedureProposal,
    RetrievalTrace,
    StrictModel,
)
from .pipeline import action_catalog_hash
from .planning import certify_plan
from .retrieval import retrieve_templates
from .solver import enumerate_candidates
from .verifier import assess_candidate


class EnumerationStatus(str, Enum):
    exhaustive = "exhaustive"
    bounded = "bounded"
    no_admissible_realization = "no_admissible_realization"
    budget_exhausted_without_realization = "budget_exhausted_without_realization"


class StepCandidateInventory(StrictModel):
    source_step_index: int = Field(ge=0)
    technique_id: str
    retrieved_template_ids: list[str] = Field(default_factory=list)
    finite_domain_candidate_count: int = Field(ge=0)
    supplied_proposal_count: int = Field(ge=0)
    unique_candidate_count: int = Field(ge=0)


class BlockerCount(StrictModel):
    code: str
    count: int = Field(ge=1)


class StepRealizationCoverage(StrictModel):
    source_step_index: int = Field(ge=0)
    technique_id: str
    candidate_count: int = Field(ge=0)
    realized_procedure_assignment_count: int = Field(ge=0)
    realized_behavior_contract_count: int = Field(ge=0)
    realized_binding_variant_count: int = Field(ge=0)
    realized_template_ids: list[str] = Field(default_factory=list)
    realized_sequence_positions: list[int] = Field(default_factory=list)


class CausalGraphNode(StrictModel):
    sequence: int = Field(ge=1)
    source_step_index: int = Field(ge=0)
    technique_id: str
    template_id: str


class CausalRealizationGraph(StrictModel):
    graph_kind: Literal["causal_procedure_realization"] = "causal_procedure_realization"
    initial_facts: list[str] = Field(default_factory=list)
    goal_facts: list[str] = Field(default_factory=list)
    source_step_order: list[int] = Field(default_factory=list)
    nodes: list[CausalGraphNode] = Field(default_factory=list)
    edges: list[CausalLink] = Field(default_factory=list)
    causal_structure_sha256: str = ""
    content_sha256: str = ""

    def _computed_causal_structure_hash(self) -> str:
        source_step_by_sequence = {node.sequence: node.source_step_index for node in self.nodes}

        def source_reference(sequence: int) -> str:
            if sequence == 0:
                return "initial"
            return f"source-step:{source_step_by_sequence[sequence]}"

        payload = {
            "initial_facts": sorted(self.initial_facts),
            "goal_facts": sorted(self.goal_facts),
            "nodes": sorted(
                (
                    {
                        "source_step_index": node.source_step_index,
                        "technique_id": node.technique_id,
                    }
                    for node in self.nodes
                ),
                key=lambda node: (node["source_step_index"], node["technique_id"]),
            ),
            "edges": sorted(
                (
                    {
                        "fact_id": edge.fact_id,
                        "producer": source_reference(edge.producer_sequence),
                        "consumer": source_reference(edge.consumer_sequence),
                    }
                    for edge in self.edges
                ),
                key=lambda edge: (
                    edge["fact_id"],
                    edge["producer"],
                    edge["consumer"],
                ),
            ),
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def finalize_hash(self) -> None:
        self.causal_structure_sha256 = self._computed_causal_structure_hash()
        self.content_sha256 = _content_hash(self, excluded_fields={"content_sha256"})

    def validate_hash(self) -> bool:
        return (
            bool(self.content_sha256)
            and self.causal_structure_sha256 == self._computed_causal_structure_hash()
            and self.content_sha256 == _content_hash(self, excluded_fields={"content_sha256"})
        )


class RealizationCandidate(StrictModel):
    rank: int = Field(ge=1)
    source_step_order: list[int] = Field(default_factory=list)
    total_assumption_count: int = Field(ge=0)
    minimum_fidelity_ceiling: str
    proposal_sources: list[str] = Field(default_factory=list)
    plan: ConcretizedPlan
    graph: CausalRealizationGraph
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        self.content_sha256 = _content_hash(self, excluded_fields={"content_sha256"})

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == _content_hash(
            self,
            excluded_fields={"content_sha256"},
        )


class RealizationSpace(StrictModel):
    schema_version: str = "1"
    campaign_id: str
    source_plan_sha256: str
    binding_catalog_sha256: str
    action_catalog_sha256: str
    source_ordering_policy: str
    source_limitations: list[str] = Field(default_factory=list)
    generation_policy: str = "bounded_search_over_versioned_admitted_candidates"
    candidate_universe: str = "finite_catalog_plus_supplied_proposals"
    template_overlay_sha256: str | None = None
    operational_status: Literal["not_run"] = "not_run"
    source_step_count: int = Field(ge=1)
    maximum_realizations: int = Field(ge=1)
    maximum_search_states: int = Field(ge=1)
    search_states_explored: int = Field(ge=0)
    procedure_assignments_explored: int = Field(ge=0)
    ordering_search_states_explored: int = Field(ge=0)
    seeded_realization_count: int = Field(ge=0)
    search_exhausted: bool
    truncation_reason: str | None = None
    enumeration_status: EnumerationStatus
    dead_end_count: int = Field(ge=0)
    maximal_realized_steps: int = Field(ge=0)
    dead_end_technique_ids: list[str] = Field(default_factory=list)
    candidate_inventory: list[StepCandidateInventory] = Field(default_factory=list)
    retrieval_traces: list[RetrievalTrace] = Field(default_factory=list)
    step_realization_coverage: list[StepRealizationCoverage] = Field(default_factory=list)
    blocker_counts: list[BlockerCount] = Field(default_factory=list)
    realization_count: int = Field(ge=0)
    ordering_variant_count: int = Field(ge=0)
    procedure_assignment_variant_count: int = Field(ge=0)
    behavior_contract_variant_count: int = Field(ge=0)
    causal_structure_variant_count: int = Field(ge=0)
    graph_variant_count: int = Field(ge=0)
    realizations: list[RealizationCandidate] = Field(default_factory=list)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        self.content_sha256 = _content_hash(self, excluded_fields={"content_sha256"})

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == _content_hash(
            self,
            excluded_fields={"content_sha256"},
        )


@dataclass(frozen=True)
class _ChosenTransition:
    source_step_index: int
    concrete_step: ConcretizedStep


@dataclass(frozen=True)
class _SearchState:
    pending_step_indices: tuple[int, ...]
    known_facts: frozenset[str]
    chosen: tuple[_ChosenTransition, ...]


def _content_hash(model: StrictModel, *, excluded_fields: set[str]) -> str:
    payload = model.model_dump(mode="json", exclude=excluded_fields)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _proposal_key(proposal: ProcedureProposal) -> tuple[object, ...]:
    return (
        proposal.technique_id,
        proposal.template_id,
        tuple(sorted(proposal.bindings.items())),
    )


def _proposal_sort_key(proposal: ProcedureProposal) -> tuple[object, ...]:
    source_priority = 0 if proposal.source == "finite_domain_solver" else 1
    return (
        source_priority,
        proposal.template_id,
        tuple(sorted(proposal.bindings.items())),
        proposal.source,
    )


def _deduplicate_proposals(
    proposals: list[ProcedureProposal],
) -> list[ProcedureProposal]:
    unique: dict[tuple[object, ...], ProcedureProposal] = {}
    for proposal in sorted(proposals, key=_proposal_sort_key):
        unique.setdefault(_proposal_key(proposal), proposal)
    return sorted(unique.values(), key=_proposal_sort_key)


def _assessment_sort_key(assessment: CandidateAssessment) -> tuple[object, ...]:
    proposal = assessment.proposal
    source_priority = 0 if proposal.source == "finite_domain_solver" else 1
    return (
        assessment.assumption_count,
        source_priority,
        proposal.template_id,
        tuple(sorted(proposal.bindings.items())),
        proposal.source,
    )


def _minimum_fidelity(steps: list[ConcretizedStep]) -> str:
    fidelity_order = {"faithful": 0, "adapted": 1, "inspired": 2}
    return max(
        (step.fidelity_ceiling for step in steps),
        key=lambda value: (fidelity_order.get(value, 3), value),
    )


def _fidelity_penalty(value: str) -> int:
    return {"faithful": 0, "adapted": 1, "inspired": 2}.get(value, 3)


def _candidate_rank_key(candidate: RealizationCandidate) -> tuple[object, ...]:
    non_solver_steps = sum(
        step.proposal_source != "finite_domain_solver" for step in candidate.plan.steps
    )
    return (
        candidate.total_assumption_count,
        _fidelity_penalty(candidate.minimum_fidelity_ceiling),
        non_solver_steps,
        tuple(candidate.source_step_order),
        candidate.plan.execution_semantic_sha256,
    )


def _procedure_assignment_signature(candidate: RealizationCandidate) -> str:
    by_source_step = sorted(
        zip(candidate.source_step_order, candidate.plan.steps),
        key=lambda item: item[0],
    )
    payload = [
        {
            "source_step_index": source_step_index,
            "technique_id": step.technique_id,
            "template_id": step.template_id,
            "bindings": step.bindings,
        }
        for source_step_index, step in by_source_step
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _behavior_contract_signature(candidate: RealizationCandidate) -> str:
    by_source_step = sorted(
        zip(candidate.source_step_order, candidate.plan.steps),
        key=lambda item: item[0],
    )
    payload = [
        {
            "source_step_index": source_step_index,
            "technique_id": step.technique_id,
            "bindings": step.bindings,
            "requires": step.requires,
            "produces": step.produces,
            "evidence_predicates": step.evidence_predicates,
            "fidelity_ceiling": step.fidelity_ceiling,
        }
        for source_step_index, step in by_source_step
    ]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _step_realization_coverage(
    plan: ProceduralPlan,
    inventories: list[StepCandidateInventory],
    candidates: list[RealizationCandidate],
) -> list[StepRealizationCoverage]:
    coverage: list[StepRealizationCoverage] = []
    for source_step_index, source_step in enumerate(plan.steps):
        realized_procedures: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        realized_behavior_contracts: set[tuple[object, ...]] = set()
        realized_bindings: set[tuple[tuple[str, str], ...]] = set()
        realized_templates: set[str] = set()
        realized_positions: set[int] = set()
        for candidate in candidates:
            if source_step_index not in candidate.source_step_order:
                continue
            realized_index = candidate.source_step_order.index(source_step_index)
            realized_step = candidate.plan.steps[realized_index]
            binding_signature = tuple(sorted(realized_step.bindings.items()))
            realized_procedures.add((realized_step.template_id, binding_signature))
            realized_behavior_contracts.add(
                (
                    binding_signature,
                    tuple(realized_step.requires),
                    tuple(realized_step.produces),
                    tuple(realized_step.evidence_predicates),
                    realized_step.fidelity_ceiling,
                )
            )
            realized_bindings.add(binding_signature)
            realized_templates.add(realized_step.template_id)
            realized_positions.add(realized_step.sequence)
        coverage.append(
            StepRealizationCoverage(
                source_step_index=source_step_index,
                technique_id=source_step.technique_id,
                candidate_count=inventories[source_step_index].unique_candidate_count,
                realized_procedure_assignment_count=len(realized_procedures),
                realized_behavior_contract_count=len(realized_behavior_contracts),
                realized_binding_variant_count=len(realized_bindings),
                realized_template_ids=sorted(realized_templates),
                realized_sequence_positions=sorted(realized_positions),
            )
        )
    return coverage


def _build_graph(
    plan: ConcretizedPlan,
    source_step_order: list[int],
) -> CausalRealizationGraph:
    certificate = plan.planning_certificate
    if certificate is None:
        raise ValueError("realization plan has no planning certificate")
    graph = CausalRealizationGraph(
        initial_facts=certificate.initial_facts,
        goal_facts=certificate.goal_facts,
        source_step_order=source_step_order,
        nodes=[
            CausalGraphNode(
                sequence=step.sequence,
                source_step_index=source_step_index,
                technique_id=step.technique_id,
                template_id=step.template_id,
            )
            for source_step_index, step in zip(source_step_order, plan.steps)
        ],
        edges=certificate.causal_links,
    )
    graph.finalize_hash()
    return graph


def _build_candidate(
    *,
    source_plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    chosen: tuple[_ChosenTransition, ...],
) -> RealizationCandidate | None:
    steps = [transition.concrete_step for transition in chosen]
    certificate = certify_plan(
        steps,
        initial_facts=catalog.initial_facts,
        goal_facts=catalog.goal_facts,
    )
    if not certificate.valid:
        return None
    concrete_plan = ConcretizedPlan(
        ordering_policy="causal_topological_realization",
        campaign_id=source_plan.campaign_id,
        source_plan_sha256=source_plan.content_sha256,
        binding_catalog_sha256=catalog.content_sha256,
        action_catalog_sha256=action_catalog_hash(templates),
        steps=steps,
        planning_certificate=certificate,
    )
    concrete_plan.finalize_hash()
    source_step_order = [transition.source_step_index for transition in chosen]
    candidate = RealizationCandidate(
        rank=1,
        source_step_order=source_step_order,
        total_assumption_count=sum(step.assumption_count for step in steps),
        minimum_fidelity_ceiling=_minimum_fidelity(steps),
        proposal_sources=sorted({step.proposal_source for step in steps}),
        plan=concrete_plan,
        graph=_build_graph(concrete_plan, source_step_order),
    )
    return candidate


def _canonical_candidate_for_assignment(
    *,
    source_plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    template_index: dict[str, ActionTemplate],
    assignment: tuple[ProcedureProposal, ...],
) -> RealizationCandidate | None:
    pending = list(range(len(source_plan.steps)))
    known_facts = frozenset(catalog.initial_facts)
    chosen: tuple[_ChosenTransition, ...] = ()
    while pending:
        selected: tuple[int, CandidateAssessment] | None = None
        for source_step_index in pending:
            assessment = _assess_step_candidates(
                source_plan.steps[source_step_index],
                [assignment[source_step_index]],
                template_index=template_index,
                catalog=catalog,
                known_facts=known_facts,
            )[0]
            if assessment.accepted:
                selected = source_step_index, assessment
                break
        if selected is None:
            return None
        source_step_index, assessment = selected
        transition = _transition_from_assessment(
            source_step_index,
            assessment,
            sequence=len(chosen) + 1,
            template_index=template_index,
        )
        pending.remove(source_step_index)
        known_facts |= frozenset(transition.concrete_step.produces)
        chosen = (*chosen, transition)
    return _build_candidate(
        source_plan=source_plan,
        catalog=catalog,
        templates=templates,
        chosen=chosen,
    )


def _validate_inputs(plan: ProceduralPlan, catalog: BindingCatalog) -> None:
    if not plan.validate_hash():
        raise ValueError("source procedural plan hash mismatch")
    if not catalog.validate_hash():
        raise ValueError("binding catalog hash mismatch")


def _proposals_by_technique(
    plan: ProceduralPlan,
    supplied_proposals: list[ProcedureProposal],
) -> dict[str, list[ProcedureProposal]]:
    plan_techniques = {step.technique_id for step in plan.steps}
    unknown = sorted(
        {
            proposal.technique_id
            for proposal in supplied_proposals
            if proposal.technique_id not in plan_techniques
        }
    )
    if unknown:
        raise ValueError("supplied proposals do not map to plan techniques: " + ", ".join(unknown))
    grouped: dict[str, list[ProcedureProposal]] = {}
    for proposal in supplied_proposals:
        grouped.setdefault(proposal.technique_id, []).append(proposal)
    return grouped


def _build_candidate_universe(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    supplied_proposals: list[ProcedureProposal],
    *,
    maximum_candidates_per_step: int,
) -> tuple[
    dict[int, list[ProcedureProposal]],
    list[RetrievalTrace],
    list[StepCandidateInventory],
]:
    grouped_proposals = _proposals_by_technique(plan, supplied_proposals)
    proposals_by_step: dict[int, list[ProcedureProposal]] = {}
    retrieval_traces: list[RetrievalTrace] = []
    inventories: list[StepCandidateInventory] = []
    retrieval_limit = max(1, len(templates))
    for source_step_index, step in enumerate(plan.steps):
        retrieved, trace = retrieve_templates(step, templates, top_k=retrieval_limit)
        finite_candidates = enumerate_candidates(
            step,
            retrieved,
            catalog,
            maximum_candidates=maximum_candidates_per_step,
        )
        supplied = grouped_proposals.get(step.technique_id, [])
        unique = _deduplicate_proposals([*finite_candidates, *supplied])
        proposals_by_step[source_step_index] = unique
        retrieval_traces.append(trace)
        inventories.append(
            StepCandidateInventory(
                source_step_index=source_step_index,
                technique_id=step.technique_id,
                retrieved_template_ids=[template.template_id for template in retrieved],
                finite_domain_candidate_count=len(finite_candidates),
                supplied_proposal_count=len(supplied),
                unique_candidate_count=len(unique),
            )
        )
    return proposals_by_step, retrieval_traces, inventories


def _assess_step_candidates(
    step: ProcedureStep,
    proposals: list[ProcedureProposal],
    *,
    template_index: dict[str, ActionTemplate],
    catalog: BindingCatalog,
    known_facts: frozenset[str],
) -> list[CandidateAssessment]:
    return [
        assess_candidate(
            proposal,
            technique_id=step.technique_id,
            execution_domain=step.execution_domain,
            templates=template_index,
            catalog=catalog,
            known_facts=set(known_facts),
        )
        for proposal in proposals
    ]


def _transition_from_assessment(
    source_step_index: int,
    assessment: CandidateAssessment,
    *,
    sequence: int,
    template_index: dict[str, ActionTemplate],
) -> _ChosenTransition:
    proposal = assessment.proposal
    template = template_index[proposal.template_id]
    return _ChosenTransition(
        source_step_index=source_step_index,
        concrete_step=ConcretizedStep(
            sequence=sequence,
            technique_id=proposal.technique_id,
            template_id=template.template_id,
            bindings=dict(proposal.bindings),
            requires=list(template.requires),
            produces=list(template.produces),
            evidence_predicates=list(template.evidence_predicates),
            fidelity_ceiling=template.fidelity_ceiling,
            proposal_source=proposal.source,
            assumption_count=assessment.assumption_count,
        ),
    )


def enumerate_realization_space(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    *,
    supplied_proposals: list[ProcedureProposal] | None = None,
    maximum_realizations: int = 64,
    maximum_search_states: int = 10000,
    maximum_candidates_per_step: int = 512,
    template_overlay_sha256: str | None = None,
) -> RealizationSpace:
    """Enumerate admitted realizations without claiming operational execution."""

    if maximum_realizations < 1:
        raise ValueError("maximum_realizations must be positive")
    if maximum_search_states < 1:
        raise ValueError("maximum_search_states must be positive")
    if maximum_candidates_per_step < 1:
        raise ValueError("maximum_candidates_per_step must be positive")
    _validate_inputs(plan, catalog)
    template_index = {template.template_id: template for template in templates}
    if len(template_index) != len(templates):
        raise ValueError("action template identifiers must be unique")
    templates = sorted(templates, key=lambda template: template.template_id)
    template_index = {template.template_id: template for template in templates}
    proposals_by_step, retrieval_traces, inventories = _build_candidate_universe(
        plan,
        catalog,
        templates,
        supplied_proposals or [],
        maximum_candidates_per_step=maximum_candidates_per_step,
    )

    frontier = [
        _SearchState(
            pending_step_indices=tuple(range(len(plan.steps))),
            known_facts=frozenset(catalog.initial_facts),
            chosen=(),
        )
    ]
    candidates: list[RealizationCandidate] = []
    seen_semantic_hashes: set[str] = set()
    blocker_counts: Counter[str] = Counter()
    dead_end_techniques: set[str] = set()
    dead_end_count = 0
    maximal_realized_steps = 0
    states_explored = 0
    procedure_assignments_explored = 0
    ordering_search_states_explored = 0
    truncation_reason: str | None = None

    assignment_domains = [proposals_by_step[index] for index in range(len(plan.steps))]
    for assignment in itertools.product(*assignment_domains):
        if states_explored >= maximum_search_states or len(candidates) >= maximum_realizations:
            break
        procedure_assignments_explored += 1
        states_explored += 1
        candidate = _canonical_candidate_for_assignment(
            source_plan=plan,
            catalog=catalog,
            templates=templates,
            template_index=template_index,
            assignment=assignment,
        )
        if candidate is None:
            continue
        semantic_hash = candidate.plan.execution_semantic_sha256
        if semantic_hash not in seen_semantic_hashes:
            seen_semantic_hashes.add(semantic_hash)
            candidates.append(candidate)
    seeded_realization_count = len(candidates)
    if seeded_realization_count:
        maximal_realized_steps = len(plan.steps)

    while frontier:
        if states_explored >= maximum_search_states:
            truncation_reason = "maximum_search_states"
            break
        if len(candidates) >= maximum_realizations:
            truncation_reason = "maximum_realizations"
            break
        state = frontier.pop()
        states_explored += 1
        ordering_search_states_explored += 1
        maximal_realized_steps = max(maximal_realized_steps, len(state.chosen))
        if not state.pending_step_indices:
            candidate = _build_candidate(
                source_plan=plan,
                catalog=catalog,
                templates=templates,
                chosen=state.chosen,
            )
            if candidate is None:
                dead_end_count += 1
                blocker_counts["UNRESOLVED_GOAL"] += 1
                continue
            semantic_hash = candidate.plan.execution_semantic_sha256
            if semantic_hash not in seen_semantic_hashes:
                seen_semantic_hashes.add(semantic_hash)
                candidates.append(candidate)
            continue

        branches: list[_SearchState] = []
        state_blockers: Counter[str] = Counter()
        for source_step_index in state.pending_step_indices:
            step = plan.steps[source_step_index]
            proposals = proposals_by_step[source_step_index]
            assessments = _assess_step_candidates(
                step,
                proposals,
                template_index=template_index,
                catalog=catalog,
                known_facts=state.known_facts,
            )
            accepted = sorted(
                (assessment for assessment in assessments if assessment.accepted),
                key=_assessment_sort_key,
            )
            for assessment in accepted:
                transition = _transition_from_assessment(
                    source_step_index,
                    assessment,
                    sequence=len(state.chosen) + 1,
                    template_index=template_index,
                )
                remaining = tuple(
                    index for index in state.pending_step_indices if index != source_step_index
                )
                branches.append(
                    _SearchState(
                        pending_step_indices=remaining,
                        known_facts=state.known_facts
                        | frozenset(transition.concrete_step.produces),
                        chosen=(*state.chosen, transition),
                    )
                )
            if not proposals:
                state_blockers["NO_CANDIDATE"] += 1
            for assessment in assessments:
                if assessment.accepted:
                    continue
                for issue in assessment.issues:
                    state_blockers[issue.code] += 1

        if branches:
            frontier.extend(reversed(branches))
            continue
        dead_end_count += 1
        blocker_counts.update(state_blockers)
        dead_end_techniques.update(
            plan.steps[index].technique_id for index in state.pending_step_indices
        )

    candidates.sort(key=_candidate_rank_key)
    ranked_candidates: list[RealizationCandidate] = []
    for rank, candidate in enumerate(candidates, start=1):
        ranked = candidate.model_copy(update={"rank": rank, "content_sha256": ""})
        ranked.finalize_hash()
        ranked_candidates.append(ranked)

    search_exhausted = not frontier
    if search_exhausted and ranked_candidates:
        status = EnumerationStatus.exhaustive
    elif search_exhausted:
        status = EnumerationStatus.no_admissible_realization
    elif ranked_candidates:
        status = EnumerationStatus.bounded
    else:
        status = EnumerationStatus.budget_exhausted_without_realization

    ordering_variants = {tuple(item.source_step_order) for item in ranked_candidates}
    procedure_assignment_variants = {
        _procedure_assignment_signature(item) for item in ranked_candidates
    }
    behavior_contract_variants = {_behavior_contract_signature(item) for item in ranked_candidates}
    causal_structure_variants = {item.graph.causal_structure_sha256 for item in ranked_candidates}
    graph_variants = {item.graph.content_sha256 for item in ranked_candidates}
    result = RealizationSpace(
        campaign_id=plan.campaign_id,
        source_plan_sha256=plan.content_sha256,
        binding_catalog_sha256=catalog.content_sha256,
        action_catalog_sha256=action_catalog_hash(templates),
        template_overlay_sha256=template_overlay_sha256,
        source_ordering_policy=plan.ordering_policy,
        source_limitations=list(plan.limitations),
        source_step_count=len(plan.steps),
        maximum_realizations=maximum_realizations,
        maximum_search_states=maximum_search_states,
        search_states_explored=states_explored,
        procedure_assignments_explored=procedure_assignments_explored,
        ordering_search_states_explored=ordering_search_states_explored,
        seeded_realization_count=seeded_realization_count,
        search_exhausted=search_exhausted,
        truncation_reason=truncation_reason,
        enumeration_status=status,
        dead_end_count=dead_end_count,
        maximal_realized_steps=maximal_realized_steps,
        dead_end_technique_ids=sorted(dead_end_techniques),
        candidate_inventory=inventories,
        retrieval_traces=retrieval_traces,
        step_realization_coverage=_step_realization_coverage(
            plan,
            inventories,
            ranked_candidates,
        ),
        blocker_counts=[
            BlockerCount(code=code, count=count) for code, count in sorted(blocker_counts.items())
        ],
        realization_count=len(ranked_candidates),
        ordering_variant_count=len(ordering_variants),
        procedure_assignment_variant_count=len(procedure_assignment_variants),
        behavior_contract_variant_count=len(behavior_contract_variants),
        causal_structure_variant_count=len(causal_structure_variants),
        graph_variant_count=len(graph_variants),
        realizations=ranked_candidates,
    )
    result.finalize_hash()
    return result
