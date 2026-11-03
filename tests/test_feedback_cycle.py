"""Execution feedback must remain bounded and retain negative attempts."""

import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.controlled_comparison import (
    ArmId,
    EffectClass,
    IndependentEffectObservation,
    NeutralProposalRecord,
    StepEffectObservation,
    canonical_sha256,
)
from evaluation.feedback_cycle import ExecutionFeedback, run_feedback_cycle

HASH = "a" * 64


def proposal(number: int) -> NeutralProposalRecord:
    record = NeutralProposalRecord(
        proposal_id=f"proposal-{number}",
        experiment_id="feedback-test",
        campaign_id="C0010",
        step_id="s1",
        arm_id=ArmId.prior_work_style,
        seed=1,
        technique_id="T1000",
        execution_domain="target",
        template_id=f"template-{number}",
        proposal_budget_sha256=HASH,
        raw_output_sha256=HASH,
    )
    record.finalize_hash()
    return record


def feedback(
    observed: bool, evidence_root: Path, *, step_id: str = "s1", number: int = 1
) -> ExecutionFeedback:
    receipt_path = evidence_root / f"receipt-{number}.json"
    raw_evidence_path = evidence_root / f"effect-{number}.json"
    receipt_path.write_bytes(f"receipt-{number}".encode())
    raw_evidence_path.write_bytes(f"effect-{number}".encode())
    effect = StepEffectObservation(
        step_id=step_id,
        effect_class=EffectClass.target_observed if observed else EffectClass.failed,
        predicate_id="target-process-cpu",
        raw_evidence_sha256=hashlib.sha256(raw_evidence_path.read_bytes()).hexdigest(),
    )
    observation = IndependentEffectObservation(
        experiment_id="feedback-test",
        campaign_id="C0010",
        seed=1,
        handoff_sha256=HASH,
        admission_oracle_revision=HASH,
        observer_revision="b" * 64,
        effects=[effect],
    )
    observation.finalize_hash()
    observation_path = evidence_root / f"observation-{number}.json"
    observation_path.write_text(observation.model_dump_json(), encoding="utf-8")
    return ExecutionFeedback(
        execution_receipt_path=receipt_path.name,
        execution_receipt_sha256=hashlib.sha256(receipt_path.read_bytes()).hexdigest(),
        raw_evidence_path=raw_evidence_path.name,
        independent_observation_path=observation_path.name,
        independent_observation_sha256=hashlib.sha256(
            observation_path.read_bytes()
        ).hexdigest(),
        independent_observation=observation,
        effect_observation_sha256=canonical_sha256(effect.model_dump(mode="json")),
        effect=effect,
        failure_reason=None if observed else "target effect absent",
    )


def test_feedback_is_passed_to_retry_and_all_attempts_are_retained(tmp_path):
    histories = []

    def propose(history):
        histories.append(history)
        return proposal(len(history) + 1)

    result = run_feedback_cycle(
        propose=propose,
        execute=lambda candidate: feedback(
            candidate.template_id == "template-2",
            tmp_path,
            number=int(candidate.template_id.rsplit("-", 1)[1]),
        ),
        evidence_root=tmp_path,
        max_attempts=3,
    )

    assert result.effect_observed
    assert [attempt.proposal.template_id for attempt in result.attempts] == [
        "template-1",
        "template-2",
    ]
    assert len(histories[0]) == 0
    assert histories[1][0].feedback.failure_reason == "target effect absent"


def test_exhaustion_retains_failure_evidence(tmp_path):
    result = run_feedback_cycle(
        propose=lambda history: proposal(len(history) + 1),
        execute=lambda candidate: feedback(
            False, tmp_path, number=int(candidate.template_id.rsplit("-", 1)[1])
        ),
        evidence_root=tmp_path,
        max_attempts=2,
    )
    assert not result.effect_observed
    assert len(result.attempts) == 2


def test_invalid_budget_and_feedback_fail_closed(tmp_path):
    with pytest.raises(ValueError, match="max_attempts"):
        run_feedback_cycle(
            propose=lambda history: proposal(1),
            execute=lambda candidate: feedback(True, tmp_path),
            evidence_root=tmp_path,
            max_attempts=0,
        )
    invalid = feedback(False, tmp_path).model_dump()
    invalid["failure_reason"] = None
    with pytest.raises(ValidationError, match="failure reason"):
        ExecutionFeedback.model_validate(invalid)


def test_effect_observation_must_match_its_hash_and_step(tmp_path):
    invalid = feedback(True, tmp_path).model_dump()
    invalid["effect_observation_sha256"] = HASH
    with pytest.raises(ValidationError, match="content hash mismatch"):
        ExecutionFeedback.model_validate(invalid)
    with pytest.raises(ValueError, match="different step"):
        run_feedback_cycle(
            propose=lambda history: proposal(1),
            execute=lambda candidate: feedback(True, tmp_path, step_id="s2"),
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_retry_cannot_change_cell_before_execution(tmp_path):
    executed = []

    def propose(history):
        candidate = proposal(len(history) + 1)
        if history:
            candidate.step_id = "s2"
            candidate.finalize_hash()
        return candidate

    def execute(candidate):
        executed.append(candidate.step_id)
        return feedback(False, tmp_path)

    with pytest.raises(ValueError, match="retry changed"):
        run_feedback_cycle(
            propose=propose, execute=execute, evidence_root=tmp_path, max_attempts=2
        )
    assert executed == ["s1"]


def test_mutated_proposal_is_rejected_before_execution(tmp_path):
    candidate = proposal(1)
    candidate.template_id = "changed"
    with pytest.raises(ValueError, match="content hash mismatch"):
        run_feedback_cycle(
            propose=lambda history: candidate,
            execute=lambda proposal: pytest.fail("execution must not start"),
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_tampered_retained_evidence_is_rejected(tmp_path):
    execution_feedback = feedback(True, tmp_path)
    (tmp_path / execution_feedback.raw_evidence_path).write_bytes(b"tampered")

    with pytest.raises(ValueError, match="retained evidence hash mismatch"):
        run_feedback_cycle(
            propose=lambda history: proposal(1),
            execute=lambda candidate: execution_feedback,
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_evidence_path_cannot_escape_experiment_root(tmp_path):
    execution_feedback = feedback(True, tmp_path)
    execution_feedback.raw_evidence_path = "../outside.json"

    with pytest.raises(ValueError, match="confined relative POSIX path"):
        run_feedback_cycle(
            propose=lambda history: proposal(1),
            execute=lambda candidate: execution_feedback,
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_feedback_requires_matching_independent_observation(tmp_path):
    execution_feedback = feedback(True, tmp_path)
    execution_feedback.independent_observation.campaign_id = "other-campaign"

    with pytest.raises(ValueError, match="different cell"):
        run_feedback_cycle(
            propose=lambda history: proposal(1),
            execute=lambda candidate: execution_feedback,
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_feedback_rejects_observation_file_tampering(tmp_path):
    execution_feedback = feedback(True, tmp_path)
    (tmp_path / execution_feedback.independent_observation_path).write_bytes(b"changed")

    with pytest.raises(ValueError, match="retained evidence hash mismatch"):
        run_feedback_cycle(
            propose=lambda history: proposal(1),
            execute=lambda candidate: execution_feedback,
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_feedback_effect_must_equal_the_independent_observation(tmp_path):
    execution_feedback = feedback(True, tmp_path)
    execution_feedback.independent_observation.effects = [
        feedback(False, tmp_path, number=2).effect
    ]

    with pytest.raises(ValueError, match="differs from independent observation"):
        run_feedback_cycle(
            propose=lambda history: proposal(1),
            execute=lambda candidate: execution_feedback,
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_observation_content_hash_is_checked_against_its_fields(tmp_path):
    execution_feedback = feedback(True, tmp_path)
    execution_feedback.independent_observation.observer_revision = "c" * 64

    with pytest.raises(ValueError, match="independent observation content hash"):
        execution_feedback.verify_files(tmp_path)
