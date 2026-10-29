"""Prior-work-style step planner for the controlled comparison.

This arm reproduces the *generation* algorithm of the closest end-to-end prior work: given an
abstract attack goal and a declared environment, a language model emits one concrete realization
of the step. It does not apply the deterministic admissibility that STICKS contributes.

Scope and deviation, stated for the record: the prior work also runs a Caldera execution-feedback
recovery loop that classifies failures and revises commands over repeated executions. That loop
needs live execution, so at the generation boundary measured here it is not modelled; the arm is
named ``prior_work_style`` and is never presented as a conformant re-implementation of that system.
Each seed produces one independent generation, so divergence across seeds is the measured quantity.
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable

from pydantic import Field, ValidationError

from concretization.models import ActionTemplate, BindingCatalog, StrictModel
from evaluation.controlled_comparison import ArmId, NeutralProposalRecord
from evaluation.proposal_errors import MalformedProposalError
from evaluation.proposal_view import binding_view, raw_template_view

# A completion callable maps (system_prompt, user_prompt) to the model's raw text response.
CompletionFn = Callable[[str, str], str]

SYSTEM_PROMPT = """You convert one abstract attack goal into one concrete laboratory step.
You receive the goal, its technique, the declared environment facts, and the action catalog. Each
catalog template declares the parameter kinds it takes; each declared binding has a kind. Return
one JSON object naming the template that realizes the step and binding every parameter the
template declares, matching each parameter to a binding of the same kind:
{
  "template_id": string,          // one catalog template id
  "bindings": {string: string}    // every declared parameter name -> a declared binding id
}
Choose the realization you judge most likely to execute. Do not add commentary.
"""


class PriorWorkStepContext(StrictModel):
    """Frozen, arm-visible inputs for one campaign step, identical across every arm."""

    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    seed: int
    technique_id: str = Field(min_length=1)
    execution_domain: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    tactic: str = Field(min_length=1)
    declared_facts: list[str] = Field(default_factory=list)
    proposal_budget_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PriorWorkChoice(StrictModel):
    template_id: str = Field(min_length=1)
    bindings: dict[str, str] = Field(default_factory=dict)


def build_prior_work_prompt(
    context: PriorWorkStepContext, templates: list[ActionTemplate], catalog: BindingCatalog
) -> str:
    payload = {
        "objective": context.objective,
        "tactic": context.tactic,
        "technique_id": context.technique_id,
        "execution_domain": context.execution_domain,
        "declared_facts": sorted(context.declared_facts),
        "catalog": raw_template_view(templates),
        "available_bindings": binding_view(catalog),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _parse_choice(raw: str) -> PriorWorkChoice:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise MalformedProposalError("response contains no JSON object")
    try:
        return PriorWorkChoice.model_validate_json(raw[start : end + 1])
    except ValidationError as error:
        raise MalformedProposalError("response is not a valid prior-work choice") from error


def propose_prior_work_step(
    context: PriorWorkStepContext,
    *,
    templates: list[ActionTemplate],
    catalog: BindingCatalog,
    complete: CompletionFn,
) -> NeutralProposalRecord:
    """Generate one prior-work-style proposal as a neutral record, without deterministic admission.

    A malformed reply raises ``ValueError``: it is an invalid observation the caller records as a
    failed run, not something this planner silently repairs.
    """
    raw = complete(SYSTEM_PROMPT, build_prior_work_prompt(context, templates, catalog))
    choice = _parse_choice(raw)
    record = NeutralProposalRecord(
        proposal_id=f"{context.campaign_id}:{context.step_id}:{ArmId.prior_work_style.value}:{context.seed}",
        experiment_id=context.experiment_id,
        campaign_id=context.campaign_id,
        step_id=context.step_id,
        arm_id=ArmId.prior_work_style,
        seed=context.seed,
        technique_id=context.technique_id,
        execution_domain=context.execution_domain,
        template_id=choice.template_id,
        bindings=choice.bindings,
        known_facts=sorted(context.declared_facts),
        proposal_budget_sha256=context.proposal_budget_sha256,
        raw_output_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
    record.finalize_hash()
    return record
