"""Compare the committed execution across proposers over one finite catalog.

An untrusted proposer suggests a realization; a deterministic verifier admits it from a
finite catalog. This module records what each proposer actually commits, so a reader can
check whether the committed execution depends on which proposer supplied the proposal.

Network and configuration stay in the caller: this module takes proposal lists already
obtained from a model and turns them into observations, so it has no provider coupling.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from contracts.procedural_ir import ProceduralPlan

from .models import ActionTemplate, BindingCatalog, ProcedureProposal
from .pipeline import concretize_plan

SOLVER_PROPOSER = "finite_domain_solver"


class ConvergenceObservation(BaseModel):
    """One proposer's committed execution for a campaign.

    usable_proposals and malformed_proposals show what the untrusted proposer emitted;
    committed_from_proposer shows how many committed steps the verifier took from it. A model
    can contribute admissible proposals and still commit exactly what the solver commits.
    """

    model_config = ConfigDict(extra="forbid")

    proposer: str
    temperature: Optional[float] = None
    sample: Optional[int] = None
    usable_proposals: int = 0
    malformed_proposals: int = 0
    committed_from_proposer: int = 0
    committed_steps: int
    execution_semantic_sha256: str
    call_record_path: Optional[str] = None
    call_record_sha256: Optional[str] = None


class ControlledConditions(BaseModel):
    """What the comparison holds constant, so convergence is not a settings artifact."""

    model_config = ConfigDict(extra="forbid")

    action_catalog_sha256: str
    system_prompt_sha256: str
    temperature: float
    max_output_tokens: int
    retry_policy: str
    held_constant: list[str]
    varied_across_runs: list[str]


class ConvergenceRecord(BaseModel):
    """The frozen comparison for one campaign."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    question: str
    controlled_conditions: ControlledConditions
    observations: list[ConvergenceObservation] = Field(default_factory=list)
    distinct_execution_hashes: int = 0
    converged: bool = False
    note: str = ""


def solver_observation(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
) -> ConvergenceObservation:
    """The deterministic reference: what the solver commits with no proposal supplied."""
    committed = concretize_plan(plan, catalog, templates, llm_proposals=[])
    return ConvergenceObservation(
        proposer=SOLVER_PROPOSER,
        committed_steps=len(committed.steps),
        execution_semantic_sha256=committed.execution_semantic_sha256,
    )


def model_observation(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    proposals: list[ProcedureProposal],
    *,
    proposer: str,
    temperature: float,
    sample: int,
    malformed_proposals: int = 0,
    call_record_path: str | None = None,
    call_record_sha256: str | None = None,
) -> ConvergenceObservation:
    """What a model proposer commits once its proposals pass the same verifier."""
    committed = concretize_plan(plan, catalog, templates, llm_proposals=proposals)
    committed_from_proposer = sum(
        1 for step in committed.steps if step.proposal_source != SOLVER_PROPOSER
    )
    return ConvergenceObservation(
        proposer=proposer,
        temperature=temperature,
        sample=sample,
        usable_proposals=len(proposals),
        malformed_proposals=malformed_proposals,
        committed_from_proposer=committed_from_proposer,
        committed_steps=len(committed.steps),
        execution_semantic_sha256=committed.execution_semantic_sha256,
        call_record_path=call_record_path,
        call_record_sha256=call_record_sha256,
    )


def assemble_record(
    campaign_id: str,
    observations: list[ConvergenceObservation],
    conditions: ControlledConditions,
    *,
    question: str,
    note: str,
) -> ConvergenceRecord:
    """Fold observations into a record and decide convergence by distinct committed hashes."""
    distinct = {observation.execution_semantic_sha256 for observation in observations}
    return ConvergenceRecord(
        campaign_id=campaign_id,
        question=question,
        controlled_conditions=conditions,
        observations=observations,
        distinct_execution_hashes=len(distinct),
        converged=len(distinct) == 1,
        note=note,
    )
