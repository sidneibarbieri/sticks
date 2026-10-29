"""Collect the controlled comparison: dispatch each arm, judge blindly, aggregate metrics.

One cell is a (campaign, arm, seed, step) tuple. Each arm produces a neutral proposal record (or,
for the admitted arm, abstains); the record is blinded and judged by the shared deterministic
oracle. The per-step observations aggregate into the arm metrics that populate the paper table:
validity rate, abstention rate, and template divergence across seeds.

The language model is injected as a ``complete`` callable so the collection is provider-agnostic
and exercised in tests without a live model. A malformed reply from an arm is recorded as an
invalid generation attempt, never silently repaired or excluded from the validity denominator.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Callable

from pydantic import Field, model_validator

from concretization.models import ActionTemplate, BindingCatalog, StrictModel
from evaluation.controlled_comparison import (
    AdmittedCampaignPlan,
    ArmId,
    NeutralProposalRecord,
    evaluate_blind_proposal,
)
from evaluation.prior_work_planner import PriorWorkStepContext, propose_prior_work_step
from evaluation.proposal_errors import MalformedProposalError
from evaluation.sticks_arm_planner import SticksStepContext, propose_sticks_step

CompletionFn = Callable[[str, str], str]


class StepFixture(StrictModel):
    step_id: str = Field(min_length=1)
    technique_id: str = Field(min_length=1)
    execution_domain: str = Field(min_length=1)
    objective: str = Field(min_length=1)
    tactic: str = Field(min_length=1)
    known_facts: list[str] = Field(default_factory=list)


class CampaignFixture(StrictModel):
    campaign_id: str = Field(min_length=1)
    steps: list[StepFixture] = Field(min_length=1)
    templates: list[ActionTemplate] = Field(min_length=1)
    catalog: BindingCatalog


class GenerationReceipt(StrictModel):
    """Exact model exchange retained for one proposal attempt."""

    request_body: str
    response_body: str
    raw_output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    recorded_at: str
    elapsed_seconds: float = Field(ge=0)
    attempt_count: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_raw_output(self) -> "GenerationReceipt":
        output = json.loads(self.response_body)["message"]["content"]
        if hashlib.sha256(output.encode("utf-8")).hexdigest() != self.raw_output_sha256:
            raise ValueError("generation receipt raw output hash mismatch")
        return self


class StepObservation(StrictModel):
    campaign_id: str
    arm_id: ArmId
    seed: int
    step_id: str
    emitted: bool
    abstained: bool
    oracle_admitted: bool | None = None
    template_id: str | None = None
    proposal_sha256: str | None = None
    proposal_record: NeutralProposalRecord | None = None
    issue_codes: list[str] = Field(default_factory=list)
    parse_error: str | None = None
    generation: GenerationReceipt | None = None

    @model_validator(mode="after")
    def validate_retained_proposal(self) -> "StepObservation":
        if self.proposal_record is None:
            return self
        if not self.emitted:
            raise ValueError("non-emitted observation cannot retain a proposal record")
        if not self.proposal_record.validate_hash():
            raise ValueError("retained proposal record hash mismatch")
        expected_identity = (
            self.campaign_id,
            self.arm_id,
            self.seed,
            self.step_id,
            self.template_id,
            self.proposal_sha256,
        )
        actual_identity = (
            self.proposal_record.campaign_id,
            self.proposal_record.arm_id,
            self.proposal_record.seed,
            self.proposal_record.step_id,
            self.proposal_record.template_id,
            self.proposal_record.content_sha256,
        )
        if actual_identity != expected_identity:
            raise ValueError("retained proposal record differs from observation")
        return self


class ArmMetrics(StrictModel):
    arm_id: ArmId
    steps: int
    emitted: int
    oracle_valid: int
    abstained: int
    parse_failures: int
    validity_rate: float
    abstention_rate: float
    mean_distinct_templates_per_step: float


def build_admitted_campaign_plan(
    observations: list[StepObservation],
    *,
    experiment_id: str,
    campaign_id: str,
    seed: int,
    collection_lock_sha256: str,
    expected_step_ids: list[str],
) -> AdmittedCampaignPlan:
    """Build the exact execution input or reject an incomplete admitted arm."""
    if len(expected_step_ids) != len(set(expected_step_ids)) or not expected_step_ids:
        raise ValueError("expected step identifiers must be unique and nonempty")
    selected = [
        observation
        for observation in observations
        if observation.campaign_id == campaign_id
        and observation.arm_id == ArmId.sticks_admitted
        and observation.seed == seed
    ]
    by_step = {observation.step_id: observation for observation in selected}
    if len(by_step) != len(selected):
        raise ValueError("admitted arm contains duplicate step observations")
    missing = [step_id for step_id in expected_step_ids if step_id not in by_step]
    unexpected = sorted(set(by_step) - set(expected_step_ids))
    if missing or unexpected:
        raise ValueError(
            f"admitted arm step accounting mismatch: missing={missing}, "
            f"unexpected={unexpected}"
        )
    proposals = []
    for step_id in expected_step_ids:
        observation = by_step[step_id]
        if (
            not observation.emitted
            or observation.abstained
            or observation.oracle_admitted is not True
            or observation.proposal_record is None
        ):
            raise ValueError(f"admitted arm has no executable proposal for {step_id}")
        proposals.append(observation.proposal_record)
    plan = AdmittedCampaignPlan(
        experiment_id=experiment_id,
        campaign_id=campaign_id,
        seed=seed,
        collection_lock_sha256=collection_lock_sha256,
        proposals=proposals,
    )
    plan.finalize_hash()
    return plan


def _prior_work_record(
    step: StepFixture, fixture: CampaignFixture, seed: int, experiment_id: str, budget_sha: str,
    complete: CompletionFn,
) -> NeutralProposalRecord:
    context = PriorWorkStepContext(
        experiment_id=experiment_id,
        campaign_id=fixture.campaign_id,
        step_id=step.step_id,
        seed=seed,
        technique_id=step.technique_id,
        execution_domain=step.execution_domain,
        objective=step.objective,
        tactic=step.tactic,
        declared_facts=step.known_facts,
        proposal_budget_sha256=budget_sha,
    )
    return propose_prior_work_step(
        context, templates=fixture.templates, catalog=fixture.catalog, complete=complete
    )


def _oracle_admits(
    record: NeutralProposalRecord, fixture: CampaignFixture, oracle_revision: str
) -> tuple[bool, list[str]]:
    oracle_input, _ = record.blind(blind_id=record.content_sha256)
    decision = evaluate_blind_proposal(
        oracle_input,
        templates=fixture.templates,
        catalog=fixture.catalog,
        oracle_revision=oracle_revision,
    )
    return decision.accepted, decision.issue_codes


def observe_step(
    arm_id: ArmId,
    step: StepFixture,
    fixture: CampaignFixture,
    seed: int,
    *,
    experiment_id: str,
    budget_sha: str,
    oracle_revision: str,
    complete: CompletionFn,
    retain_proposal: bool = False,
) -> StepObservation:
    """Run one arm on one step and judge the result with the blind oracle."""
    base = {
        "campaign_id": fixture.campaign_id,
        "arm_id": arm_id,
        "seed": seed,
        "step_id": step.step_id,
    }
    try:
        if arm_id == ArmId.prior_work_style:
            record: NeutralProposalRecord | None = _prior_work_record(
                step, fixture, seed, experiment_id, budget_sha, complete
            )
            abstained = False
            issue_codes: list[str] = []
        else:
            context = SticksStepContext(
                experiment_id=experiment_id,
                campaign_id=fixture.campaign_id,
                step_id=step.step_id,
                seed=seed,
                technique_id=step.technique_id,
                execution_domain=step.execution_domain,
                known_facts=step.known_facts,
                proposal_budget_sha256=budget_sha,
            )
            outcome = propose_sticks_step(
                context,
                templates=fixture.templates,
                catalog=fixture.catalog,
                complete=complete,
                admit=arm_id == ArmId.sticks_admitted,
            )
            record = outcome.record
            abstained = outcome.abstained
            issue_codes = outcome.issue_codes
    except MalformedProposalError as error:
        # The reply produced no proposal; analysis still counts this generation attempt.
        return StepObservation(**base, emitted=False, abstained=False, parse_error=str(error))

    if record is None:
        return StepObservation(**base, emitted=False, abstained=abstained, issue_codes=issue_codes)

    oracle_admitted, oracle_issues = _oracle_admits(record, fixture, oracle_revision)
    return StepObservation(
        **base,
        emitted=True,
        abstained=False,
        oracle_admitted=oracle_admitted,
        template_id=record.template_id,
        proposal_sha256=record.content_sha256,
        proposal_record=record if retain_proposal else None,
        issue_codes=oracle_issues,
    )


def compute_arm_metrics(observations: list[StepObservation], arm_id: ArmId) -> ArmMetrics:
    arm = [observation for observation in observations if observation.arm_id == arm_id]
    steps = len(arm)
    emitted = sum(1 for observation in arm if observation.emitted)
    oracle_valid = sum(1 for observation in arm if observation.oracle_admitted)
    abstained = sum(1 for observation in arm if observation.abstained)
    parse_failures = sum(1 for observation in arm if observation.parse_error is not None)

    # A step is identified by campaign and step id together: step ids repeat across campaigns, and
    # keying on the step id alone would merge unrelated steps and inflate divergence.
    templates_by_step: dict[tuple[str, str], set[str]] = defaultdict(set)
    for observation in arm:
        if observation.template_id is not None:
            templates_by_step[(observation.campaign_id, observation.step_id)].add(
                observation.template_id
            )
    distinct_values = [len(values) for values in templates_by_step.values()]
    mean_distinct = sum(distinct_values) / len(distinct_values) if distinct_values else 0.0

    attempted = sum(
        1 for observation in arm if observation.emitted or observation.parse_error is not None
    )
    return ArmMetrics(
        arm_id=arm_id,
        steps=steps,
        emitted=emitted,
        oracle_valid=oracle_valid,
        abstained=abstained,
        parse_failures=parse_failures,
        validity_rate=oracle_valid / attempted if attempted else 0.0,
        abstention_rate=abstained / steps if steps else 0.0,
        mean_distinct_templates_per_step=mean_distinct,
    )
