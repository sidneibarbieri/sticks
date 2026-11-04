"""Campaign-parametric core for the STICKS P17 paired collection.

A single globally shuffled grid of (seed, repetition, arm) cells over the admitted and
prior-work-style arms, sharing the lab transport, the independent observer, the per-cell target
reset and the budget. The campaign is a parameter: the reports, the simulated steps, and the model,
lab, admitted-executor and observer bindings are injected, so different campaigns share this code
and differ only in their data and wiring. One frozen lock and one receipt cover both arms, so
temporal drift hits them in balance.

A failed prior-work attempt (truncation, malformed reply, non-zero command, or an unconfirmed
effect) is typed and fed back within the budget; the admitted arm runs its deterministic executor
once. The simulated steps carry no target effect and are recorded directly. Infrastructure errors
are left to raise.
"""

from __future__ import annotations

import json
import random
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field

from concretization.models import StrictModel
from evaluation.admitted_step_execution import AdmittedExecutor, run_admitted_step
from evaluation.controlled_comparison import EffectClass
from evaluation.prior_work_execution import (
    CommandRunner,
    CompletionFn,
    EffectObserver,
    PriorWorkStepReport,
    run_prior_work_step,
)

ADMITTED_ARM = "admitted"
PRIOR_WORK_ARM = "prior_work_style"
ARMS = (ADMITTED_ARM, PRIOR_WORK_ARM)


class SimulatedStep(StrictModel):
    """A naive_simulated occurrence recorded directly, with no target effect."""

    step_id: str = Field(min_length=1)
    occurrence: int = Field(gt=0)
    technique_id: str = Field(min_length=1)


class CollectionConfig(StrictModel):
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    model: str = Field(min_length=1)
    temperature: float = Field(ge=0.0)
    top_p: float = Field(gt=0.0, le=1.0)
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0)
    retry_limit: int = Field(gt=0)
    seeds: list[int] = Field(min_length=1)
    repetitions: int = Field(gt=0)
    shuffle_seed: int


class StepOutcome(StrictModel):
    arm: str
    step_id: str
    occurrence: int
    technique_id: str
    effect_class: str
    attempts: int
    failure_reason: str | None = None


class CellResult(StrictModel):
    seed: int
    repetition: int
    arm: str
    steps: list[StepOutcome]


@dataclass(frozen=True)
class CollectionBindings:
    """Injected model, lab and observer wiring; callables, not data, so not a Pydantic model."""

    make_complete: Callable[[int], CompletionFn]
    run_command: CommandRunner
    execute_admitted: AdmittedExecutor
    observe_effect: EffectObserver
    reset_target: Callable[[], None]


@dataclass(frozen=True)
class CollectionRevisions:
    admission_oracle: str
    observer: str
    collection_lock_sha256: str
    proposal_budget_sha256: str
    max_attempts: int


def _simulated_outcome(arm: str, step: SimulatedStep) -> StepOutcome:
    return StepOutcome(
        arm=arm,
        step_id=step.step_id,
        occurrence=step.occurrence,
        technique_id=step.technique_id,
        effect_class=EffectClass.simulated.value,
        attempts=0,
    )


def _prior_work_outcome(
    report: PriorWorkStepReport,
    *,
    seed: int,
    cell_root: Path,
    bindings: CollectionBindings,
    revisions: CollectionRevisions,
) -> StepOutcome:
    result = run_prior_work_step(
        report,
        seed=seed,
        complete=bindings.make_complete(seed),
        run_command=bindings.run_command,
        observe_effect=bindings.observe_effect,
        admission_oracle_revision=revisions.admission_oracle,
        observer_revision=revisions.observer,
        collection_lock_sha256=revisions.collection_lock_sha256,
        proposal_budget_sha256=revisions.proposal_budget_sha256,
        evidence_root=cell_root,
        max_attempts=revisions.max_attempts,
    )
    terminal = result.attempts[-1].feedback
    return StepOutcome(
        arm=PRIOR_WORK_ARM,
        step_id=report.step_id,
        occurrence=report.occurrence,
        technique_id=report.technique_id,
        effect_class=terminal.effect.effect_class.value,
        attempts=len(result.attempts),
        failure_reason=terminal.failure_reason,
    )


def _admitted_outcome(
    report: PriorWorkStepReport,
    *,
    seed: int,
    cell_root: Path,
    bindings: CollectionBindings,
    revisions: CollectionRevisions,
) -> StepOutcome:
    outcome = run_admitted_step(
        report,
        seed=seed,
        execute_admitted=bindings.execute_admitted,
        observe_effect=bindings.observe_effect,
        admission_oracle_revision=revisions.admission_oracle,
        observer_revision=revisions.observer,
        collection_lock_sha256=revisions.collection_lock_sha256,
        evidence_root=cell_root,
    )
    return StepOutcome(
        arm=ADMITTED_ARM,
        step_id=report.step_id,
        occurrence=report.occurrence,
        technique_id=report.technique_id,
        effect_class=outcome.effect.effect_class.value,
        attempts=1,
        failure_reason=outcome.failure_reason,
    )


def run_cell(
    *,
    seed: int,
    repetition: int,
    arm: str,
    reports: list[PriorWorkStepReport],
    simulated_steps: list[SimulatedStep],
    bindings: CollectionBindings,
    revisions: CollectionRevisions,
    cell_root: Path,
) -> CellResult:
    """Reset the target, then run every step of one arm for one (seed, repetition) cell."""
    bindings.reset_target()
    steps = [_simulated_outcome(arm, step) for step in simulated_steps]
    for report in reports:
        if arm == ADMITTED_ARM:
            steps.append(
                _admitted_outcome(
                    report, seed=seed, cell_root=cell_root, bindings=bindings, revisions=revisions
                )
            )
        else:
            steps.append(
                _prior_work_outcome(
                    report, seed=seed, cell_root=cell_root, bindings=bindings, revisions=revisions
                )
            )
    steps.sort(key=lambda step: step.occurrence)
    return CellResult(seed=seed, repetition=repetition, arm=arm, steps=steps)


def _empty_step_bucket(occurrence: int, technique_id: str) -> dict[str, object]:
    return {
        "occurrence": occurrence,
        "technique_id": technique_id,
        "target_observed": 0,
        "simulated": 0,
        "failed": 0,
        "failure_reasons": {},
        "attempts_total": 0,
    }


def _fold_step(bucket: dict[str, object], step: StepOutcome) -> None:
    bucket["attempts_total"] += step.attempts
    if step.effect_class == EffectClass.target_observed.value:
        bucket["target_observed"] += 1
    elif step.effect_class == EffectClass.simulated.value:
        bucket["simulated"] += 1
    else:
        bucket["failed"] += 1
        reasons = bucket["failure_reasons"]
        reasons[step.failure_reason] = reasons.get(step.failure_reason, 0) + 1


def aggregate_receipt(
    config: CollectionConfig, cells: list[CellResult], extra_fields: dict[str, object]
) -> dict[str, object]:
    by_arm: dict[str, dict[str, dict[str, object]]] = {arm: {} for arm in ARMS}
    for cell in cells:
        for step in cell.steps:
            arm_steps = by_arm[step.arm]
            bucket = arm_steps.setdefault(
                step.step_id, _empty_step_bucket(step.occurrence, step.technique_id)
            )
            _fold_step(bucket, step)
    receipt = {
        "schema": "sticks-p17-paired-receipt/v1",
        "campaign_id": config.campaign_id,
        "cells": len(cells),
        "seeds": config.seeds,
        "repetitions": config.repetitions,
        "arms": {arm: by_arm[arm] for arm in ARMS},
    }
    receipt.update(extra_fields)
    return receipt


def collect(
    *,
    reports: list[PriorWorkStepReport],
    simulated_steps: list[SimulatedStep],
    config: CollectionConfig,
    bindings: CollectionBindings,
    revisions: CollectionRevisions,
    run_root: Path,
    receipt_extra: dict[str, object],
) -> dict[str, object]:
    """Run the full shuffled grid with per-cell caching and write the frozen receipt."""
    grid = [
        (seed, repetition, arm)
        for seed in config.seeds
        for repetition in range(1, config.repetitions + 1)
        for arm in ARMS
    ]
    random.Random(config.shuffle_seed).shuffle(grid)

    cells: list[CellResult] = []
    for seed, repetition, arm in grid:
        cell_root = run_root / "cells" / f"{arm}_seed_{seed}_rep_{repetition}"
        cached = cell_root / "cell_result.json"
        if cached.exists():
            cells.append(CellResult.model_validate_json(cached.read_text(encoding="utf-8")))
            continue
        cell_root.mkdir(parents=True, exist_ok=False)
        result = run_cell(
            seed=seed,
            repetition=repetition,
            arm=arm,
            reports=reports,
            simulated_steps=simulated_steps,
            bindings=bindings,
            revisions=revisions,
            cell_root=cell_root,
        )
        cached.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        cells.append(result)
        print(f"cell arm={arm} seed={seed} rep={repetition} done", flush=True)

    receipt = aggregate_receipt(config, cells, receipt_extra)
    (run_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
    )
    return receipt
