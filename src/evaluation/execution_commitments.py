"""Explicit execution commitments per campaign: how much procedural information the
contract makes concrete.

Executing a CTI procedure requires, per step, a mechanism (which action template) and a
binding for each of the template's parameters. This module counts those commitments in the
concretized plan: one mechanism commitment per step plus one binding commitment per bound
parameter, together with the candidates the verifier pruned.

Scope. This is a structural characterization of the contract -- the amount of procedural
information STICKS makes explicit and determines deterministically. It is not a measure of
analyst time, effort, or cost; establishing those would require a user study. The count
does not assert that a human would make exactly these decisions by hand.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from concretization.models import ActionTemplate, BindingCatalog
from concretization.pipeline import concretize_plan
from contracts.procedural_ir import ProceduralPlan


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CampaignCommitments(StrictModel):
    campaign_id: str
    steps: int
    # One template choice per step.
    mechanism_commitments: int
    # One binding per bound parameter across all steps.
    binding_commitments: int
    # The execution commitments the contract makes concrete.
    total_execution_commitments: int
    # Inadmissible candidates the verifier rejected while committing the plan.
    candidates_pruned_by_verifier: int
    # True when every step was resolved without leaving an open decision.
    fully_determined: bool


def measure_commitments(
    campaign_id: str,
    plan: ProceduralPlan,
    declared: BindingCatalog,
    templates: list[ActionTemplate],
) -> CampaignCommitments:
    result = concretize_plan(plan, declared, templates, llm_proposals=[])
    mechanism_commitments = len(result.steps)
    binding_commitments = sum(len(step.bindings) for step in result.steps)
    return CampaignCommitments(
        campaign_id=campaign_id,
        steps=len(plan.steps),
        mechanism_commitments=mechanism_commitments,
        binding_commitments=binding_commitments,
        total_execution_commitments=mechanism_commitments + binding_commitments,
        candidates_pruned_by_verifier=len(result.rejected_candidates),
        fully_determined=not result.unresolved_technique_ids,
    )
