"""Bounded execution feedback for an experimental proposal baseline.

This controller records each proposal and observed effect. It does not reproduce
any prior system's report parser, command generator, or failure classifier.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path, PurePosixPath

from pydantic import Field, model_validator

from concretization.models import StrictModel
from evaluation.controlled_comparison import (
    EffectClass,
    IndependentEffectObservation,
    NeutralProposalRecord,
    StepEffectObservation,
    canonical_sha256,
)


class ExecutionFeedback(StrictModel):
    execution_receipt_path: str = Field(min_length=1)
    execution_receipt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    raw_evidence_path: str = Field(min_length=1)
    independent_observation_path: str = Field(min_length=1)
    independent_observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    independent_observation: IndependentEffectObservation
    effect_observation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    effect: StepEffectObservation
    failure_reason: str | None = None

    @property
    def effect_observed(self) -> bool:
        return self.effect.effect_class == EffectClass.target_observed

    @model_validator(mode="after")
    def require_failure_reason(self) -> ExecutionFeedback:
        if self.effect_observation_sha256 != canonical_sha256(
            self.effect.model_dump(mode="json")
        ):
            raise ValueError("effect observation content hash mismatch")
        if self.effect_observed and self.failure_reason is not None:
            raise ValueError("successful effect cannot have a failure reason")
        if not self.effect_observed and not self.failure_reason:
            raise ValueError("failed effect requires a failure reason")
        return self

    def verify_files(self, evidence_root: Path) -> None:
        """Bind reported hashes to files confined to this experiment's evidence root."""
        _verify_file(
            evidence_root, self.execution_receipt_path, self.execution_receipt_sha256
        )
        _verify_file(
            evidence_root, self.raw_evidence_path, self.effect.raw_evidence_sha256
        )
        _verify_file(
            evidence_root,
            self.independent_observation_path,
            self.independent_observation_sha256,
        )
        if self.independent_observation.content_sha256 != canonical_sha256(
            self.independent_observation.model_dump(
                mode="json", exclude={"content_sha256"}
            )
        ):
            raise ValueError("independent observation content hash mismatch")
        observation_file = (
            evidence_root / self.independent_observation_path
        ).read_bytes()
        if (
            IndependentEffectObservation.model_validate_json(observation_file)
            != self.independent_observation
        ):
            raise ValueError("independent observation file differs from feedback")


def _verify_file(evidence_root: Path, relative_name: str, expected_hash: str) -> None:
    relative_path = PurePosixPath(relative_name)
    if (
        relative_path.is_absolute()
        or not relative_path.parts
        or any(part in (".", "..") for part in relative_path.parts)
        or "\\" in relative_name
    ):
        raise ValueError("evidence path must be a confined relative POSIX path")
    root = evidence_root.resolve(strict=True)
    path = (root / relative_name).resolve(strict=True)
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("evidence path escapes the experiment directory")
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash:
        raise ValueError("retained evidence hash mismatch")


class FeedbackAttempt(StrictModel):
    number: int = Field(ge=1)
    proposal: NeutralProposalRecord
    feedback: ExecutionFeedback


class FeedbackCycleResult(StrictModel):
    attempts: list[FeedbackAttempt] = Field(min_length=1)
    effect_observed: bool

    @model_validator(mode="after")
    def validate_trace(self) -> FeedbackCycleResult:
        first = self.attempts[0].proposal
        identity = (
            first.experiment_id,
            first.campaign_id,
            first.step_id,
            first.seed,
            first.arm_id,
        )
        proposal_ids = set()
        evidence_paths = set()
        for number, attempt in enumerate(self.attempts, start=1):
            candidate = attempt.proposal
            candidate_identity = (
                candidate.experiment_id,
                candidate.campaign_id,
                candidate.step_id,
                candidate.seed,
                candidate.arm_id,
            )
            if attempt.number != number or candidate_identity != identity:
                raise ValueError("feedback trace mixes attempts or experiment cells")
            if candidate.proposal_id in proposal_ids:
                raise ValueError("feedback trace repeats a proposal identifier")
            proposal_ids.add(candidate.proposal_id)
            paths = (
                attempt.feedback.execution_receipt_path,
                attempt.feedback.raw_evidence_path,
                attempt.feedback.independent_observation_path,
            )
            if any(path in evidence_paths for path in paths) or len(set(paths)) != len(
                paths
            ):
                raise ValueError("feedback trace reuses an evidence path")
            evidence_paths.update(paths)
            if number < len(self.attempts) and attempt.feedback.effect_observed:
                raise ValueError("feedback trace continues after an observed effect")
        if self.effect_observed != self.attempts[-1].feedback.effect_observed:
            raise ValueError("feedback result differs from the terminal attempt")
        return self


Propose = Callable[[tuple[FeedbackAttempt, ...]], NeutralProposalRecord]
Execute = Callable[[NeutralProposalRecord], ExecutionFeedback]


def run_feedback_cycle(
    *, propose: Propose, execute: Execute, evidence_root: Path, max_attempts: int
) -> FeedbackCycleResult:
    """Run a bounded serial loop; a failed attempt remains visible to the proposer."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be positive")
    attempts: list[FeedbackAttempt] = []
    for number in range(1, max_attempts + 1):
        proposal = propose(tuple(attempts))
        if not proposal.validate_hash():
            raise ValueError("proposal content hash mismatch")
        if attempts:
            first = attempts[0].proposal
            if (
                proposal.experiment_id,
                proposal.campaign_id,
                proposal.step_id,
                proposal.seed,
                proposal.arm_id,
            ) != (
                first.experiment_id,
                first.campaign_id,
                first.step_id,
                first.seed,
                first.arm_id,
            ):
                raise ValueError("retry changed the experiment cell")
        feedback = execute(proposal)
        if feedback.effect.step_id != proposal.step_id:
            raise ValueError("effect observation belongs to a different step")
        observation = feedback.independent_observation
        if (
            observation.experiment_id,
            observation.campaign_id,
            observation.seed,
        ) != (proposal.experiment_id, proposal.campaign_id, proposal.seed):
            raise ValueError("independent observation belongs to a different cell")
        if observation.effects != [feedback.effect]:
            raise ValueError("feedback effect differs from independent observation")
        feedback.verify_files(evidence_root)
        attempts.append(
            FeedbackAttempt(number=number, proposal=proposal, feedback=feedback)
        )
        if feedback.effect_observed:
            return FeedbackCycleResult(attempts=attempts, effect_observed=True)
    return FeedbackCycleResult(attempts=attempts, effect_observed=False)
