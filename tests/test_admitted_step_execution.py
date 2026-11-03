"""Contract tests for the admitted (deterministic STICKS) P17 arm, using injected fakes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evaluation.admitted_step_execution import (
    AdmittedExecutionResult,
    run_admitted_step,
)
from evaluation.controlled_comparison import EffectClass
from evaluation.prior_work_execution import EffectProbeResult, PriorWorkStepReport

ORACLE_REVISION = "a" * 64
OBSERVER_REVISION = "b" * 64
LOCK_SHA256 = "c" * 64


def _report() -> PriorWorkStepReport:
    return PriorWorkStepReport(
        experiment_id="p17-paired",
        campaign_id="0.c0026",
        step_id="s6",
        occurrence=6,
        technique_id="T1030",
        tactic="exfiltration",
        execution_domain="linux",
        execution_user="ubuntu",
        objective="Split the archive into size-limited fragments.",
        effect_contract="At least two fragments that reassemble to the archive.",
        declared_facts=["target:target-linux-1"],
        observer_authority_id="c0026-chunks",
        predicate_id="archive-chunks",
        timeout_seconds=30,
    )


def _executor(ok: bool):
    def execute_admitted(technique_id: str) -> AdmittedExecutionResult:
        assert technique_id == "T1030"
        return AdmittedExecutionResult(
            technique_id=technique_id, ok=ok, stdout="split done" if ok else "", stderr=""
        )

    return execute_admitted


def _observer(passed: bool):
    def observe_effect(report: PriorWorkStepReport) -> EffectProbeResult:
        return EffectProbeResult(
            authority_id=report.observer_authority_id,
            predicate_id=report.predicate_id,
            passed=passed,
            raw_observation=json.dumps({"passed": passed}, sort_keys=True),
        )

    return observe_effect


def _run(tmp_path: Path, *, executor_ok: bool, probe_passed: bool, observer=OBSERVER_REVISION):
    return run_admitted_step(
        _report(),
        seed=11,
        execute_admitted=_executor(executor_ok),
        observe_effect=_observer(probe_passed),
        admission_oracle_revision=ORACLE_REVISION,
        observer_revision=observer,
        collection_lock_sha256=LOCK_SHA256,
        evidence_root=tmp_path,
    )


def test_admitted_step_observed(tmp_path: Path) -> None:
    outcome = _run(tmp_path, executor_ok=True, probe_passed=True)
    assert outcome.effect_observed is True
    assert outcome.effect.effect_class == EffectClass.target_observed
    assert outcome.failure_reason is None
    assert outcome.observation.validate_hash() is True


def test_admitted_step_effect_not_confirmed(tmp_path: Path) -> None:
    outcome = _run(tmp_path, executor_ok=True, probe_passed=False)
    assert outcome.effect_observed is False
    assert outcome.failure_reason == "effect_not_confirmed_by_independent_probe"


def test_admitted_step_executor_failure(tmp_path: Path) -> None:
    outcome = _run(tmp_path, executor_ok=False, probe_passed=True)
    assert outcome.effect_observed is False
    assert outcome.failure_reason == "executor_failed"


def test_admitted_observer_must_differ_from_oracle(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="independent observer"):
        _run(tmp_path, executor_ok=True, probe_passed=True, observer=ORACLE_REVISION)


def test_admitted_evidence_files_written(tmp_path: Path) -> None:
    _run(tmp_path, executor_ok=True, probe_passed=True)
    step_root = tmp_path / "s6" / "admitted"
    assert (step_root / "executor_result.json").is_file()
    assert (step_root / "independent_observation.json").is_file()
    assert (step_root / "independent_probe_raw.json").is_file()
