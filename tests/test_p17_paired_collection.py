"""Contract tests for the campaign-parametric paired collection core, using injected fakes."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.admitted_step_execution import AdmittedExecutionResult
from evaluation.prior_work_execution import (
    CompletionOutcome,
    EffectProbeResult,
    PriorWorkStepReport,
    TargetExecutionResult,
)
from evaluation.p17_paired_collection import (
    ARMS,
    CollectionBindings,
    CollectionConfig,
    CollectionRevisions,
    SimulatedStep,
    collect,
)

ORACLE = "a" * 64
OBSERVER = "b" * 64


def _report(step_id: str, occurrence: int, technique_id: str) -> PriorWorkStepReport:
    return PriorWorkStepReport(
        experiment_id="p17",
        campaign_id="0.costaricto",
        step_id=step_id,
        occurrence=occurrence,
        technique_id=technique_id,
        tactic="collection",
        execution_domain="linux",
        execution_user="reconuser",
        objective="do the thing",
        effect_contract="produce the declared target effect",
        declared_facts=["target:target-linux-1"],
        observer_authority_id="costaricto-collection",
        predicate_id="local-collection",
        timeout_seconds=30,
    )


def _config() -> CollectionConfig:
    return CollectionConfig(
        experiment_id="p17",
        campaign_id="0.costaricto",
        model="qwen3.6:latest",
        temperature=0.0,
        top_p=1.0,
        max_output_tokens=1024,
        timeout_seconds=120,
        retry_limit=3,
        seeds=[101, 102, 103],
        repetitions=3,
        shuffle_seed=20261104,
    )


def _bindings(*, prior_work_passes: bool) -> CollectionBindings:
    def make_complete(seed: int):
        def complete(system: str, user: str) -> CompletionOutcome:
            text = json.dumps({"command": "true", "rationale": "x"})
            return CompletionOutcome(text=text, done_reason="stop", response_body=text)

        return complete

    def run_command(command: str, timeout_seconds: int, execution_user: str) -> TargetExecutionResult:
        return TargetExecutionResult(
            command=command, returncode=0, stdout="", stderr="", elapsed_seconds=0.0
        )

    def execute_admitted(technique_id: str) -> AdmittedExecutionResult:
        return AdmittedExecutionResult(technique_id=technique_id, ok=True, stdout="", stderr="")

    def observe(report: PriorWorkStepReport) -> EffectProbeResult:
        raw = json.dumps({"passed": prior_work_passes}, sort_keys=True)
        return EffectProbeResult(
            authority_id=report.observer_authority_id,
            predicate_id=report.predicate_id,
            passed=prior_work_passes,
            raw_observation=raw,
        )

    return CollectionBindings(
        make_complete=make_complete,
        run_command=run_command,
        execute_admitted=execute_admitted,
        observe_effect=observe,
        reset_target=lambda: None,
    )


def _revisions() -> CollectionRevisions:
    return CollectionRevisions(
        admission_oracle=ORACLE,
        observer=OBSERVER,
        collection_lock_sha256="c" * 64,
        proposal_budget_sha256="d" * 64,
        max_attempts=3,
    )


def _run(tmp_path: Path, *, prior_work_passes: bool) -> dict:
    reports = [
        _report("s1", 1, "T1046"),
        _report("s2", 2, "T1105"),
        _report("s9", 9, "T1005"),
    ]
    simulated = [SimulatedStep(step_id="s3", occurrence=3, technique_id="T1090.003")]
    return collect(
        reports=reports,
        simulated_steps=simulated,
        config=_config(),
        bindings=_bindings(prior_work_passes=prior_work_passes),
        revisions=_revisions(),
        run_root=tmp_path,
        receipt_extra={"campaigns": "two"},
    )


def test_full_grid_is_eighteen_cells_both_arms_observed(tmp_path: Path) -> None:
    receipt = _run(tmp_path, prior_work_passes=True)
    assert receipt["cells"] == 18
    assert set(receipt["arms"]) == set(ARMS)
    for arm in ARMS:
        for step_id in ("s1", "s2", "s9"):
            assert receipt["arms"][arm][step_id]["target_observed"] == 9
        assert receipt["arms"][arm]["s3"]["simulated"] == 9
    assert receipt["campaigns"] == "two"


def test_resume_reuses_cached_cells(tmp_path: Path) -> None:
    _run(tmp_path, prior_work_passes=True)
    receipt = _run(tmp_path, prior_work_passes=True)
    assert receipt["cells"] == 18


def test_unconfirmed_effect_is_typed_failure(tmp_path: Path) -> None:
    # The fake probe gates both arms; an unconfirmed effect must be recorded as a failure, never
    # as an observation or a (false) simulation. The admitted-vs-prior-work contrast is a property
    # of the live lab, validated by the smoke and the full run, not by this orchestration test.
    receipt = _run(tmp_path, prior_work_passes=False)
    for arm in ARMS:
        for step_id in ("s1", "s2", "s9"):
            assert receipt["arms"][arm][step_id]["target_observed"] == 0
            assert receipt["arms"][arm][step_id]["failed"] == 9
        assert receipt["arms"][arm]["s3"]["simulated"] == 9
