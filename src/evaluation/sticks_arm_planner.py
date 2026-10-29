"""STICKS proposal arms for the controlled comparison.

Both STICKS arms use the same procedural representation and the same injected language model to
choose one realization per step. They differ in one step: ``sticks_without_admission`` emits every
proposal, while ``sticks_admitted`` passes the proposal through the deterministic verifier and
abstains when it is not admitted. That single difference isolates the effect of admission: the
admitted arm never emits a proposal the verifier would reject; its cost is abstention, not an
invalid step.

The language model is injected as a ``complete`` callable, so this module has no dependency on any
particular provider and is exercised in tests without a live model.
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable

from pydantic import Field, ValidationError

from concretization.models import (
    ActionTemplate,
    BindingCatalog,
    ProcedureProposal,
    StrictModel,
)
from concretization.verifier import assess_candidate
from evaluation.controlled_comparison import ArmId, NeutralProposalRecord
from evaluation.proposal_errors import MalformedProposalError
from evaluation.proposal_view import feasible_binding_view, feasible_template_view

# A completion callable maps (system_prompt, user_prompt) to the model's raw text response.
CompletionFn = Callable[[str, str], str]

SYSTEM_PROMPT = """You realize one attack step against a laboratory environment.
You receive the step, the facts already known to hold, and a typed action catalog in which every
template declares the facts it requires and the facts it produces. Choose the single template whose
required facts already hold and whose produced facts advance the step. Bind every parameter the
template declares, matching each parameter to a declared binding of the same kind. Return one JSON object:
{
  "template_id": string,        // one catalog template id
  "bindings": {string: string}  // parameter name -> declared binding id
}
Return only the JSON object.
"""


class SticksStepContext(StrictModel):
    """Frozen, arm-visible inputs for one campaign step, identical across every arm."""

    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    seed: int
    technique_id: str = Field(min_length=1)
    execution_domain: str = Field(min_length=1)
    known_facts: list[str] = Field(default_factory=list)
    proposal_budget_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SticksArmOutcome(StrictModel):
    arm_id: ArmId
    admitted: bool
    abstained: bool
    record: NeutralProposalRecord | None = None
    issue_codes: list[str] = Field(default_factory=list)


class _Choice(StrictModel):
    template_id: str = Field(min_length=1)
    bindings: dict[str, str] = Field(default_factory=dict)


def build_sticks_prompt(
    context: SticksStepContext, templates: list[ActionTemplate], catalog: BindingCatalog
) -> str:
    candidates = feasible_template_view(
        templates,
        technique_id=context.technique_id,
        execution_domain=context.execution_domain,
        known_facts=context.known_facts,
    )
    candidate_ids = {candidate["template_id"] for candidate in candidates}
    feasible_templates = [
        template for template in templates if template.template_id in candidate_ids
    ]
    payload = {
        "technique_id": context.technique_id,
        "execution_domain": context.execution_domain,
        "known_facts": sorted(context.known_facts),
        "catalog": candidates,
        "available_bindings": feasible_binding_view(catalog, feasible_templates),
    }
    return json.dumps(payload, indent=2, sort_keys=True)


def _parse_choice(raw: str) -> _Choice:
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise MalformedProposalError("response contains no JSON object")
    try:
        return _Choice.model_validate_json(raw[start : end + 1])
    except ValidationError as error:
        raise MalformedProposalError("response is not a valid STICKS choice") from error


def _neutral_record(
    context: SticksStepContext, arm_id: ArmId, choice: _Choice, raw: str
) -> NeutralProposalRecord:
    record = NeutralProposalRecord(
        proposal_id=f"{context.campaign_id}:{context.step_id}:{arm_id.value}:{context.seed}",
        experiment_id=context.experiment_id,
        campaign_id=context.campaign_id,
        step_id=context.step_id,
        arm_id=arm_id,
        seed=context.seed,
        technique_id=context.technique_id,
        execution_domain=context.execution_domain,
        template_id=choice.template_id,
        bindings=choice.bindings,
        known_facts=sorted(context.known_facts),
        proposal_budget_sha256=context.proposal_budget_sha256,
        raw_output_sha256=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
    record.finalize_hash()
    return record


def propose_sticks_step(
    context: SticksStepContext,
    *,
    templates: list[ActionTemplate],
    catalog: BindingCatalog,
    complete: CompletionFn,
    admit: bool,
) -> SticksArmOutcome:
    """Propose one realization; when ``admit`` is set, abstain unless the verifier admits it.

    A malformed reply raises ``ValueError``: the caller records it as a failed run rather than
    letting this planner silently repair it.
    """
    raw = complete(SYSTEM_PROMPT, build_sticks_prompt(context, templates, catalog))
    choice = _parse_choice(raw)
    arm_id = ArmId.sticks_admitted if admit else ArmId.sticks_without_admission

    if not admit:
        return SticksArmOutcome(
            arm_id=arm_id,
            admitted=False,
            abstained=False,
            record=_neutral_record(context, arm_id, choice, raw),
        )

    proposal = ProcedureProposal(
        technique_id=context.technique_id,
        template_id=choice.template_id,
        bindings=choice.bindings,
        source="sticks_admitted_arm",
    )
    assessment = assess_candidate(
        proposal,
        technique_id=context.technique_id,
        execution_domain=context.execution_domain,
        templates={template.template_id: template for template in templates},
        catalog=catalog,
        known_facts=set(context.known_facts),
    )
    if not assessment.accepted:
        return SticksArmOutcome(
            arm_id=arm_id,
            admitted=False,
            abstained=True,
            issue_codes=[issue.code for issue in assessment.issues],
        )
    return SticksArmOutcome(
        arm_id=arm_id,
        admitted=True,
        abstained=False,
        record=_neutral_record(context, arm_id, choice, raw),
    )
