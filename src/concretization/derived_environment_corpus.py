"""Measure admission when the laboratory environment is derived, not authored.

The deep evaluation authors one binding catalog per campaign, which is what limited it to
three campaigns. This corpus asks how far admission reaches when the environment is derived
from the catalog instead: for every campaign the environment is the minimal declared
laboratory its plan can bind against, and admission is decided by the same verifier.

Aggregation is deterministic and offline; no proposer is consulted.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from contracts.procedural_ir import ProceduralPlan

from .lab_environment import derive_lab_environment
from .models import ActionTemplate
from .pipeline import concretize_plan

QUESTION = (
    "Can the declared environment be derived from the action catalog instead of authored "
    "per campaign?"
)
METHOD = (
    "For each plan, the environment is derived from the templates that plan can retrieve: "
    "one laboratory binding per consumed parameter kind, and initial facts are exactly the "
    "required facts those templates never produce. Every derived binding is a system "
    "choice, so provenance still reports it as introduced by the reconstruction."
)
NOTE = (
    "Authored environments remain the deep-evaluation baseline. Derivation removes the "
    "per-campaign authoring step, which is what limited execution to three campaigns; it "
    "does not reproduce a historical victim network."
)


class DerivedEnvironmentCampaign(BaseModel):
    """Admission for one campaign under its derived laboratory environment."""

    model_config = ConfigDict(extra="forbid")

    campaign_id: str
    total_steps: int
    admitted_steps: int
    environment_bindings: int
    environment_sha256: str


class DerivedEnvironmentCorpus(BaseModel):
    """Corpus-wide admission under derived environments."""

    model_config = ConfigDict(extra="forbid")

    question: str = QUESTION
    method: str = METHOD
    campaigns: int
    total_steps: int
    admitted_steps: int
    admitted_rate: float
    campaigns_fully_admitted: int
    campaigns_partially_admitted: int
    campaigns_with_no_admitted_step: int
    note: str = NOTE
    per_campaign: list[DerivedEnvironmentCampaign] = Field(default_factory=list)


def measure_campaign(
    plan: ProceduralPlan, templates: list[ActionTemplate]
) -> DerivedEnvironmentCampaign:
    """Derive the environment this plan needs and record how many steps it admits."""
    environment = derive_lab_environment(f"lab.{plan.campaign_id.lower()}", templates, plan)
    committed = concretize_plan(plan, environment, templates, llm_proposals=[])
    return DerivedEnvironmentCampaign(
        campaign_id=plan.campaign_id,
        total_steps=len(plan.steps),
        admitted_steps=len(committed.steps),
        environment_bindings=len(environment.bindings),
        environment_sha256=environment.content_sha256,
    )


def aggregate(
    per_campaign: list[DerivedEnvironmentCampaign],
) -> DerivedEnvironmentCorpus:
    """Fold per-campaign admission into corpus totals."""
    total_steps = sum(item.total_steps for item in per_campaign)
    admitted_steps = sum(item.admitted_steps for item in per_campaign)
    fully = sum(
        1 for item in per_campaign if item.total_steps and item.admitted_steps == item.total_steps
    )
    partial = sum(
        1 for item in per_campaign if 0 < item.admitted_steps < item.total_steps
    )
    none = sum(1 for item in per_campaign if item.admitted_steps == 0)
    return DerivedEnvironmentCorpus(
        campaigns=len(per_campaign),
        total_steps=total_steps,
        admitted_steps=admitted_steps,
        admitted_rate=admitted_steps / total_steps if total_steps else 0.0,
        campaigns_fully_admitted=fully,
        campaigns_partially_admitted=partial,
        campaigns_with_no_admitted_step=none,
        per_campaign=per_campaign,
    )
