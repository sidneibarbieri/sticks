"""Contract tests for the prior-work executed feedback loop, using injected fakes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.controlled_comparison import EffectClass
from evaluation.prior_work_execution import (
    CompletionOutcome,
    EffectProbeResult,
    PriorWorkStepReport,
    TargetExecutionResult,
    build_report_prompt,
    parse_command,
    run_prior_work_step,
)
from evaluation.proposal_errors import MalformedProposalError

ORACLE_REVISION = "a" * 64
OBSERVER_REVISION = "b" * 64
LOCK_SHA256 = "c" * 64
BUDGET_SHA256 = "d" * 64


def _report() -> PriorWorkStepReport:
    return PriorWorkStepReport(
        experiment_id="p17-prior-work",
        campaign_id="0.c0026",
        step_id="s3",
        occurrence=3,
        technique_id="T1105",
        tactic="command-and-control",
        execution_domain="linux",
        execution_user="ubuntu",
        objective="Place the benign downloaded payload on the target.",
        effect_contract="File /tmp/sticks_downloaded_payload.sh holds exactly the benign script.",
        declared_facts=["target:target-linux-1"],
        observer_authority_id="c0026-payload",
        predicate_id="benign-payload",
        timeout_seconds=20,
    )


def _completion(text: str, done_reason: str = "stop") -> CompletionOutcome:
    return CompletionOutcome(
        text=text, done_reason=done_reason, response_body=json.dumps({"message": text})
    )


def _ok_command(command: str) -> str:
    return json.dumps({"command": command, "rationale": "does the thing"})


def _run(tmp_path: Path, *, complete, run_command, observe_effect, max_attempts):
    return run_prior_work_step(
        _report(),
        seed=7,
        complete=complete,
        run_command=run_command,
        observe_effect=observe_effect,
        admission_oracle_revision=ORACLE_REVISION,
        observer_revision=OBSERVER_REVISION,
        collection_lock_sha256=LOCK_SHA256,
        proposal_budget_sha256=BUDGET_SHA256,
        evidence_root=tmp_path,
        max_attempts=max_attempts,
    )


def _runner(returncode: int = 0):
    def run_command(command: str, timeout_seconds: int, execution_user: str) -> TargetExecutionResult:
        assert execution_user == "ubuntu"
        return TargetExecutionResult(
            command=command, returncode=returncode, stdout="", stderr="", elapsed_seconds=0.1
        )

    return run_command


def _observer(passed: bool):
    def observe_effect(report: PriorWorkStepReport) -> EffectProbeResult:
        return EffectProbeResult(
            authority_id=report.observer_authority_id,
            predicate_id=report.predicate_id,
            passed=passed,
            raw_observation=json.dumps({"passed": passed}, sort_keys=True),
        )

    return observe_effect


def test_parse_command_rejects_non_json() -> None:
    with pytest.raises(MalformedProposalError):
        parse_command("no json here")


def test_first_attempt_success(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        complete=lambda system, user: _completion(_ok_command("printf ... > /tmp/x")),
        run_command=_runner(),
        observe_effect=_observer(True),
        max_attempts=3,
    )
    assert result.effect_observed is True
    assert len(result.attempts) == 1
    assert result.attempts[0].feedback.effect.effect_class == EffectClass.target_observed
    assert result.attempts[0].feedback.failure_reason is None


def test_truncated_reply_is_typed_failure_then_retries(tmp_path: Path) -> None:
    replies = [
        _completion("partial thinking with no answer", done_reason="length"),
        _completion(_ok_command("printf ... > /tmp/x")),
    ]
    result = _run(
        tmp_path,
        complete=lambda system, user: replies.pop(0),
        run_command=_runner(),
        observe_effect=_observer(True),
        max_attempts=3,
    )
    assert result.effect_observed is True
    assert len(result.attempts) == 2
    first = result.attempts[0].feedback
    assert first.effect.effect_class == EffectClass.failed
    assert first.failure_reason == "proposal_truncated:done_reason=length"


def test_malformed_reply_is_typed_failure(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        complete=lambda system, user: _completion("{not valid json"),
        run_command=_runner(),
        observe_effect=_observer(True),
        max_attempts=1,
    )
    assert result.effect_observed is False
    assert result.attempts[0].feedback.failure_reason.startswith("malformed_proposal:")


def test_unconfirmed_effect_is_failure(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        complete=lambda system, user: _completion(_ok_command("true")),
        run_command=_runner(returncode=0),
        observe_effect=_observer(False),
        max_attempts=1,
    )
    assert result.effect_observed is False
    assert result.attempts[0].feedback.failure_reason == "effect_not_confirmed_by_independent_probe"


def test_command_failure_is_typed(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        complete=lambda system, user: _completion(_ok_command("false")),
        run_command=_runner(returncode=1),
        observe_effect=_observer(False),
        max_attempts=1,
    )
    assert result.attempts[0].feedback.failure_reason == "command_failed:returncode=1"


def test_prior_failure_is_fed_back_to_model(tmp_path: Path) -> None:
    seen_prompts: list[str] = []

    def complete(system: str, user: str) -> CompletionOutcome:
        seen_prompts.append(user)
        if len(seen_prompts) == 1:
            return _completion(_ok_command("false"))
        return _completion(_ok_command("printf ... > /tmp/x"))

    runners = [_runner(returncode=1), _runner(returncode=0)]
    observers = [_observer(False), _observer(True)]

    def run_command(command: str, timeout_seconds: int, execution_user: str) -> TargetExecutionResult:
        return runners[len(seen_prompts) - 1](command, timeout_seconds, execution_user)

    def observe_effect(report: PriorWorkStepReport) -> EffectProbeResult:
        return observers[len(seen_prompts) - 1](report)

    result = _run(
        tmp_path,
        complete=complete,
        run_command=run_command,
        observe_effect=observe_effect,
        max_attempts=2,
    )
    assert result.effect_observed is True
    assert len(seen_prompts) == 2
    second_prompt = json.loads(seen_prompts[1])
    assert second_prompt["previous_failed_attempts"][0]["command"] == "false"
    assert second_prompt["previous_failed_attempts"][0]["failure_reason"] == (
        "command_failed:returncode=1"
    )


def test_observer_must_differ_from_oracle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="independent observer"):
        run_prior_work_step(
            _report(),
            seed=7,
            complete=lambda system, user: _completion(_ok_command("true")),
            run_command=_runner(),
            observe_effect=_observer(True),
            admission_oracle_revision=ORACLE_REVISION,
            observer_revision=ORACLE_REVISION,
            collection_lock_sha256=LOCK_SHA256,
            proposal_budget_sha256=BUDGET_SHA256,
            evidence_root=tmp_path,
            max_attempts=1,
        )


def test_build_report_prompt_includes_history() -> None:
    from evaluation.prior_work_execution import AttemptSummary

    prompt = build_report_prompt(
        _report(), [AttemptSummary(number=1, command="false", failure_reason="command_failed")]
    )
    payload = json.loads(prompt)
    assert payload["previous_failed_attempts"][0]["command"] == "false"
    assert payload["intended_effect"].startswith("File /tmp/sticks_downloaded_payload.sh")
