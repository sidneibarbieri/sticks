"""Admitted (deterministic STICKS) arm of the STICKS P17 executed comparison.

The admitted arm runs the registered STICKS executor for each campaign step on the lab target and
confirms the effect with the SAME independent probe the prior-work arm uses, so the two arms differ
only in how the command is produced: a deterministic STICKS realization here, a model reading a
report in ``evaluation.prior_work_execution``. There is no retry budget — the realization is
deterministic, so one attempt is the whole arm.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

from pydantic import Field

from concretization.models import StrictModel
from evaluation.controlled_comparison import (
    EffectClass,
    IndependentEffectObservation,
    StepEffectObservation,
    canonical_sha256,
)
from evaluation.prior_work_execution import (
    EffectObserver,
    PriorWorkStepReport,
    write_evidence_json,
)


class AdmittedExecutionResult(StrictModel):
    """Raw outcome of running one deterministic STICKS executor on the target."""

    technique_id: str = Field(min_length=1)
    ok: bool
    stdout: str
    stderr: str


# technique_id -> AdmittedExecutionResult. The real executor dispatches the registered STICKS
# realization for the campaign; a fake stands in for tests.
AdmittedExecutor = Callable[[str], AdmittedExecutionResult]


class AdmittedStepOutcome(StrictModel):
    effect: StepEffectObservation
    observation: IndependentEffectObservation
    failure_reason: str | None = None

    @property
    def effect_observed(self) -> bool:
        return self.effect.effect_class == EffectClass.target_observed


def _admitted_handoff_sha256(
    report: PriorWorkStepReport, collection_lock_sha256: str, result: AdmittedExecutionResult
) -> str:
    """Bind the observation to this step, lock and executor outcome (an admitted-arm handoff)."""
    return canonical_sha256(
        {
            "kind": "admitted_execution_handoff",
            "experiment_id": report.experiment_id,
            "campaign_id": report.campaign_id,
            "step_id": report.step_id,
            "technique_id": report.technique_id,
            "collection_lock_sha256": collection_lock_sha256,
            "executor_result_sha256": canonical_sha256(result.model_dump(mode="json")),
        }
    )


def _confirm_effect(
    report: PriorWorkStepReport, result: AdmittedExecutionResult, observe_effect: EffectObserver
) -> tuple[bool, str, str, str | None]:
    """Observe the effect via the independent probe only if the executor reported success."""
    if not result.ok:
        skipped = json.dumps(
            {"skipped": True, "reason": "executor_failed", "stderr": result.stderr[:500]},
            sort_keys=True,
        )
        return False, skipped, report.predicate_id, "executor_failed"
    probe = observe_effect(report)
    if probe.passed:
        return True, probe.raw_observation, probe.predicate_id, None
    return (
        False,
        probe.raw_observation,
        probe.predicate_id,
        "effect_not_confirmed_by_independent_probe",
    )


def run_admitted_step(
    report: PriorWorkStepReport,
    *,
    seed: int,
    execute_admitted: AdmittedExecutor,
    observe_effect: EffectObserver,
    admission_oracle_revision: str,
    observer_revision: str,
    collection_lock_sha256: str,
    evidence_root: Path,
) -> AdmittedStepOutcome:
    """Run the deterministic STICKS realization for one step and observe it independently."""
    if admission_oracle_revision == observer_revision:
        raise ValueError("independent observer must differ from the admission oracle")
    step_root = evidence_root / report.step_id / "admitted"
    step_root.mkdir(parents=True, exist_ok=False)

    result = execute_admitted(report.technique_id)
    write_evidence_json(step_root / "executor_result.json", result.model_dump(mode="json"))

    observed, probe_raw, predicate_id, failure_reason = _confirm_effect(
        report, result, observe_effect
    )
    raw_evidence_path = step_root / "independent_probe_raw.json"
    with raw_evidence_path.open("xb") as handle:
        handle.write(probe_raw.encode("utf-8"))

    effect = StepEffectObservation(
        step_id=report.step_id,
        effect_class=EffectClass.target_observed if observed else EffectClass.failed,
        predicate_id=predicate_id,
        raw_evidence_sha256=hashlib.sha256(probe_raw.encode("utf-8")).hexdigest(),
    )
    observation = IndependentEffectObservation(
        experiment_id=report.experiment_id,
        campaign_id=report.campaign_id,
        seed=seed,
        handoff_sha256=_admitted_handoff_sha256(report, collection_lock_sha256, result),
        admission_oracle_revision=admission_oracle_revision,
        observer_revision=observer_revision,
        effects=[effect],
    )
    observation.finalize_hash()
    write_evidence_json(
        step_root / "independent_observation.json", observation.model_dump(mode="json")
    )
    return AdmittedStepOutcome(effect=effect, observation=observation, failure_reason=failure_reason)
