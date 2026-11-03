#!/usr/bin/env python3
"""Collect the STICKS P17 PAIRED operational comparison on one campaign, under one frozen lock.

Both arms run in a single globally shuffled grid of (seed, repetition, arm) cells: the admitted
arm (deterministic STICKS executor) and the prior-work-style executed arm (a frozen model reads a
report and emits a command). They share the lab transport, the independent observer, the per-cell
target reset and the budget, and differ only in how each step's command is produced. One frozen
lock and one receipt cover both arms, so temporal drift hits them in balance.

Only campaign 0.c0026 has an executable admitted plan (C0010/C0045 are ineligible), so this is a
single-campaign comparison by necessity; that is recorded as an explicit limit, not worked around.

``--dry-run`` replaces the model, the lab transport, the admitted executor and the probe with
deterministic fakes so the harness is validated without a lab. The admitted arm never uses the
model; the prior-work arm never uses the registered executors.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import inspect
import random
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import StrictModel  # noqa: E402
from evaluation.admitted_step_execution import (  # noqa: E402
    AdmittedExecutionResult,
    run_admitted_step,
)
from evaluation.controlled_comparison import EffectClass, canonical_sha256  # noqa: E402
from evaluation.prior_work_execution import (  # noqa: E402
    CompletionOutcome,
    EffectProbeResult,
    PriorWorkStepReport,
    TargetExecutionResult,
    run_prior_work_step,
)
from pydantic import Field  # noqa: E402

CAMPAIGN_ID = "0.c0026"
SUT_PROFILE_ID = "0.c0026"
TARGET_HOST_ID = "target-linux-1"
TARGET_PRINCIPAL = "ubuntu"
SIMULATED_OCCURRENCE = 1
SIMULATED_TECHNIQUE = "T1583.001"
ARMS = ("admitted", "prior_work_style")
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
# Clear attacker artifacts with root so a cell starts clean regardless of which user a prior step
# created them as; source fixtures are left in place. A reset failure halts the run (not masked).
TARGET_RESET_SCRIPT = (
    "sudo -n rm -rf /tmp/sticks_t1005 /tmp/sticks_t1560_001 "
    "/tmp/sticks_downloaded_payload.sh /tmp/sticks_collected_data.tar.gz "
    "/tmp/sticks_chunk.* /tmp/sticks_dynamic_resolution.txt; "
    "sudo -n sed -i '/c2.dynamic.local/d' /etc/hosts"
)


class CollectionConfig(StrictModel):
    experiment_id: str
    campaign_id: str
    model: str
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


def load_reports(campaign_id: str) -> tuple[list[PriorWorkStepReport], dict[str, object]]:
    path = PROJECT_ROOT / "data/p17/prior_work_reports" / f"{campaign_id}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    reports = [
        PriorWorkStepReport(
            experiment_id=document["experiment_id"],
            campaign_id=document["campaign_id"],
            step_id=entry["step_id"],
            occurrence=entry["occurrence"],
            technique_id=entry["technique_id"],
            tactic=entry["tactic"],
            execution_domain=document["execution_domain"],
            execution_user=document["execution_user"],
            objective=entry["objective"],
            effect_contract=entry["effect_contract"],
            declared_facts=entry["declared_facts"],
            observer_authority_id=entry["observer_authority_id"],
            predicate_id=entry["predicate_id"],
            timeout_seconds=document["timeout_seconds"],
        )
        for entry in document["reports"]
    ]
    return reports, document


def admission_oracle_revision() -> str:
    sources = {
        relative: hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        for relative in (
            "src/concretization/verifier.py",
            "src/evaluation/controlled_comparison.py",
        )
    }
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode("utf-8")).hexdigest()


def observer_revision_for(reports: list[PriorWorkStepReport]) -> str:
    from runners.capability_authority import registered_authority_revision

    return registered_authority_revision({report.observer_authority_id for report in reports})


def ollama_model_digest(model: str) -> str:
    with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/tags", timeout=10) as response:
        tags = json.load(response)
    matches = [entry["digest"] for entry in tags["models"] if entry["name"] == model]
    if len(matches) != 1 or len(matches[0]) != 64:
        raise ValueError(f"Ollama did not return a single valid digest for {model}")
    return matches[0]


def ollama_runtime_id() -> str:
    with urllib.request.urlopen(f"{OLLAMA_BASE_URL}/api/version", timeout=10) as response:
        return f"ollama:{json.load(response)['version']}"


def build_ollama_completion(config: CollectionConfig, seed: int, expected_digest: str):
    def complete(system_prompt: str, user_prompt: str) -> CompletionOutcome:
        if ollama_model_digest(config.model) != expected_digest:
            raise RuntimeError("model artifact changed during collection")
        body = json.dumps(
            {
                "model": config.model,
                "stream": False,
                "think": False,
                "options": {
                    "temperature": config.temperature,
                    "top_p": config.top_p,
                    "seed": seed,
                    "num_predict": config.max_output_tokens,
                },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{OLLAMA_BASE_URL}/api/chat", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=config.timeout_seconds) as response:
            response_body = response.read().decode("utf-8")
        parsed = json.loads(response_body)
        return CompletionOutcome(
            text=parsed["message"]["content"],
            done_reason=parsed.get("done_reason") or "stop",
            response_body=response_body,
        )

    return complete


def build_lab_command_runner():
    from executors.lab_transport import run_bash_on_target_vm

    def run_command(command: str, timeout_seconds: int, execution_user: str) -> TargetExecutionResult:
        started = time.perf_counter()
        result = run_bash_on_target_vm(
            SUT_PROFILE_ID, command, execution_user=execution_user, timeout=timeout_seconds
        )
        return TargetExecutionResult(
            command=command,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            elapsed_seconds=time.perf_counter() - started,
        )

    return run_command


def build_lab_effect_observer(scope):
    from runners.c0026_capability_observers import effect_request, observe_c0026_effect

    def observe(report: PriorWorkStepReport) -> EffectProbeResult:
        request = effect_request(report.observer_authority_id, scope, uuid4().hex, report.occurrence)
        observation = observe_c0026_effect(request)
        return EffectProbeResult(
            authority_id=report.observer_authority_id,
            predicate_id=report.predicate_id,
            passed=observation.passed,
            raw_observation=observation.model_dump_json(),
        )

    return observe


def _load_c0026_executor_bindings() -> dict[str, tuple[str, str]]:
    """Map each C0026 technique to the executor identity and source digest the contract pins."""
    contract = json.loads(
        (PROJECT_ROOT / "data/runtime_contracts/c0026.json").read_text(encoding="utf-8")
    )
    return {
        occurrence["technique_id"]: (occurrence["executor_id"], occurrence["executor_sha256"])
        for occurrence in contract["occurrences"]
    }


def _verify_executor_binding(technique_id: str, executor, bindings: dict[str, tuple[str, str]]) -> None:
    """Reject any executor whose identity or source bytes differ from the pinned C0026 binding."""
    expected_id, expected_sha = bindings[technique_id]
    identity = f"{executor.__module__}.{executor.__qualname__}"
    if identity != expected_id:
        raise ValueError(f"admitted executor {identity} differs from contract {expected_id}")
    source_path = inspect.getsourcefile(executor)
    if source_path is None:
        raise ValueError(f"admitted executor for {technique_id} has no inspectable source")
    source_sha = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    if source_sha != expected_sha:
        raise ValueError(f"admitted executor source for {technique_id} differs from contract")


def build_lab_admitted_executor():
    """Return an admitted executor that dispatches the exact STICKS realization the contract pins.

    The registry is initialized so the campaign-scoped executors register, and each resolved
    executor is verified against the C0026 runtime-contract identity and source digest. A genuine
    executor failure raises inside the registered executor; it is left to propagate and halt the
    run rather than being recorded as an arm failure.
    """
    from executors.executor_registry import registry
    from executors.registry_initializer import initialize_registry

    initialize_registry()
    bindings = _load_c0026_executor_bindings()

    def execute_admitted(technique_id: str) -> AdmittedExecutionResult:
        if technique_id not in bindings:
            raise ValueError(f"no C0026 runtime-contract binding for {technique_id}")
        executor = registry.get_executor(technique_id, CAMPAIGN_ID)
        if executor is None:
            raise ValueError(f"no registered executor for {technique_id} on {CAMPAIGN_ID}")
        _verify_executor_binding(technique_id, executor, bindings)
        ok, stdout, stderr, _artifacts = executor(CAMPAIGN_ID, SUT_PROFILE_ID)
        return AdmittedExecutionResult(
            technique_id=technique_id, ok=bool(ok), stdout=stdout, stderr=stderr
        )

    return execute_admitted


def discover_lab_scope(experiment_id: str):
    from runners.lab_runtime_bootstrap import _discover_scope

    scope, _ = _discover_scope(
        sut_profile_id=SUT_PROFILE_ID,
        expected_host_id=TARGET_HOST_ID,
        principal=TARGET_PRINCIPAL,
        run_id=experiment_id,
        environment_id=experiment_id,
    )
    return scope


def build_dry_run_bindings():
    """Deterministic fakes: both arms observe every step on the first attempt."""

    def complete(system_prompt: str, user_prompt: str) -> CompletionOutcome:
        text = json.dumps({"command": "true", "rationale": "dry-run"})
        return CompletionOutcome(text=text, done_reason="stop", response_body=text)

    def run_command(command: str, timeout_seconds: int, execution_user: str) -> TargetExecutionResult:
        return TargetExecutionResult(
            command=command, returncode=0, stdout="", stderr="", elapsed_seconds=0.0
        )

    def execute_admitted(technique_id: str) -> AdmittedExecutionResult:
        return AdmittedExecutionResult(technique_id=technique_id, ok=True, stdout="", stderr="")

    def observe(report: PriorWorkStepReport) -> EffectProbeResult:
        raw = json.dumps({"passed": True, "dry_run": True}, sort_keys=True)
        return EffectProbeResult(
            authority_id=report.observer_authority_id,
            predicate_id=report.predicate_id,
            passed=True,
            raw_observation=raw,
        )

    return complete, run_command, execute_admitted, observe


def _simulated_step(arm: str) -> StepOutcome:
    return StepOutcome(
        arm=arm,
        step_id=f"s{SIMULATED_OCCURRENCE}",
        occurrence=SIMULATED_OCCURRENCE,
        technique_id=SIMULATED_TECHNIQUE,
        effect_class=EffectClass.simulated.value,
        attempts=0,
    )


def _prior_work_step_outcome(
    report: PriorWorkStepReport, *, seed: int, cell_root: Path, bindings: dict, revisions: dict
) -> StepOutcome:
    result = run_prior_work_step(
        report,
        seed=seed,
        complete=bindings["make_complete"](seed),
        run_command=bindings["run_command"],
        observe_effect=bindings["observe"],
        admission_oracle_revision=revisions["oracle"],
        observer_revision=revisions["observer"],
        collection_lock_sha256=revisions["lock"],
        proposal_budget_sha256=revisions["budget"],
        evidence_root=cell_root,
        max_attempts=revisions["max_attempts"],
    )
    terminal = result.attempts[-1].feedback
    return StepOutcome(
        arm="prior_work_style",
        step_id=report.step_id,
        occurrence=report.occurrence,
        technique_id=report.technique_id,
        effect_class=terminal.effect.effect_class.value,
        attempts=len(result.attempts),
        failure_reason=terminal.failure_reason,
    )


def _admitted_step_outcome(
    report: PriorWorkStepReport, *, seed: int, cell_root: Path, bindings: dict, revisions: dict
) -> StepOutcome:
    outcome = run_admitted_step(
        report,
        seed=seed,
        execute_admitted=bindings["execute_admitted"],
        observe_effect=bindings["observe"],
        admission_oracle_revision=revisions["oracle"],
        observer_revision=revisions["observer"],
        collection_lock_sha256=revisions["lock"],
        evidence_root=cell_root,
    )
    return StepOutcome(
        arm="admitted",
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
    reset_target,
    cell_root: Path,
    bindings: dict,
    revisions: dict,
) -> CellResult:
    reset_target()
    steps = [_simulated_step(arm)]
    for report in reports:
        if arm == "admitted":
            steps.append(
                _admitted_step_outcome(
                    report, seed=seed, cell_root=cell_root, bindings=bindings, revisions=revisions
                )
            )
        else:
            steps.append(
                _prior_work_step_outcome(
                    report, seed=seed, cell_root=cell_root, bindings=bindings, revisions=revisions
                )
            )
    return CellResult(seed=seed, repetition=repetition, arm=arm, steps=steps)


def build_lock_payload(
    config: CollectionConfig,
    document: dict[str, object],
    *,
    model_digest: str,
    runtime_id: str,
    oracle_revision: str,
    observer_revision: str,
) -> dict[str, object]:
    source_relatives = (
        f"data/p17/prior_work_reports/{config.campaign_id}.json",
        "src/evaluation/prior_work_execution.py",
        "src/evaluation/admitted_step_execution.py",
        "src/evaluation/feedback_cycle.py",
        "src/evaluation/controlled_comparison.py",
        "src/concretization/verifier.py",
        "src/executors/executor_registry.py",
        "src/runners/c0026_capability_observers.py",
        "src/runners/capability_authority.py",
        "scripts/probe_c0026_target.py",
    )
    source_sha256 = {
        relative: hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        for relative in source_relatives
    }
    return {
        "schema": "sticks-p17-paired-collection-lock/v1",
        "arms": list(ARMS),
        "config": config.model_dump(mode="json"),
        "ollama_model_digest": model_digest,
        "ollama_runtime_id": runtime_id,
        "thinking_mode": False,
        "admission_oracle_revision": oracle_revision,
        "observer_revision": observer_revision,
        "reports_schema_version": document["schema_version"],
        "source_sha256": source_sha256,
    }


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


def aggregate_receipt(config: CollectionConfig, cells: list[CellResult]) -> dict[str, object]:
    by_arm: dict[str, dict[str, dict[str, object]]] = {arm: {} for arm in ARMS}
    for cell in cells:
        for step in cell.steps:
            arm_steps = by_arm[step.arm]
            bucket = arm_steps.setdefault(
                step.step_id, _empty_step_bucket(step.occurrence, step.technique_id)
            )
            _fold_step(bucket, step)
    return {
        "schema": "sticks-p17-paired-receipt/v1",
        "arm_note": "Paired local comparison on campaign 0.c0026; the prior-work arm is not a reproduction of any prior end-to-end system.",
        "campaign_id": config.campaign_id,
        "single_campaign_limit": "Only 0.c0026 has an executable admitted plan; C0010/C0045 are ineligible, so this is a single-campaign comparison.",
        "cells": len(cells),
        "seeds": config.seeds,
        "repetitions": config.repetitions,
        "arms": {arm: by_arm[arm] for arm in ARMS},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--model", default="qwen3.6:latest")
    parser.add_argument("--seeds", type=int, nargs="+", default=[101, 102, 103])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--shuffle-seed", type=int, default=20261103)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--retry-limit", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _build_bindings(args, config, reports):
    """Wire the model, lab transport, admitted executor and probe (live or dry-run)."""
    if args.dry_run:
        complete_fn, run_command, execute_admitted, observe = build_dry_run_bindings()
        return (
            {
                "make_complete": lambda seed: complete_fn,
                "run_command": run_command,
                "execute_admitted": execute_admitted,
                "observe": observe,
            },
            {"model_digest": "0" * 64, "runtime_id": "dry-run", "reset": lambda: None},
        )
    model_digest = ollama_model_digest(config.model)
    runtime_id = ollama_runtime_id()
    scope = discover_lab_scope(config.experiment_id)
    from executors.lab_transport import run_bash_on_target_vm

    def reset_target() -> None:
        run_bash_on_target_vm(
            SUT_PROFILE_ID, TARGET_RESET_SCRIPT, execution_user=TARGET_PRINCIPAL, timeout=30
        )

    return (
        {
            "make_complete": lambda seed: build_ollama_completion(config, seed, model_digest),
            "run_command": build_lab_command_runner(),
            "execute_admitted": build_lab_admitted_executor(),
            "observe": build_lab_effect_observer(scope),
        },
        {"model_digest": model_digest, "runtime_id": runtime_id, "reset": reset_target},
    )


def main() -> int:
    args = parse_args()
    reports, document = load_reports(CAMPAIGN_ID)
    config = CollectionConfig(
        experiment_id=document["experiment_id"],
        campaign_id=CAMPAIGN_ID,
        model=args.model,
        temperature=args.temperature,
        top_p=args.top_p,
        max_output_tokens=args.max_output_tokens,
        timeout_seconds=args.timeout_seconds,
        retry_limit=args.retry_limit,
        seeds=args.seeds,
        repetitions=args.repetitions,
        shuffle_seed=args.shuffle_seed,
    )
    oracle_revision = admission_oracle_revision()
    observer_revision = observer_revision_for(reports)
    if oracle_revision == observer_revision:
        raise ValueError("independent observer must differ from the admission oracle")

    run_root = args.run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)
    bindings, infra = _build_bindings(args, config, reports)

    lock_payload = build_lock_payload(
        config,
        document,
        model_digest=infra["model_digest"],
        runtime_id=infra["runtime_id"],
        oracle_revision=oracle_revision,
        observer_revision=observer_revision,
    )
    lock_bytes = json.dumps(lock_payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (run_root / "collection-lock.json").write_bytes(lock_bytes)
    revisions = {
        "oracle": oracle_revision,
        "observer": observer_revision,
        "lock": hashlib.sha256(lock_bytes).hexdigest(),
        "budget": canonical_sha256(config.model_dump(mode="json")),
        "max_attempts": config.retry_limit,
    }

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
            reset_target=infra["reset"],
            cell_root=cell_root,
            bindings=bindings,
            revisions=revisions,
        )
        cached.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        cells.append(result)
        print(f"cell arm={arm} seed={seed} rep={repetition} done", flush=True)

    receipt = aggregate_receipt(config, cells)
    receipt["collection_lock_sha256"] = revisions["lock"]
    (run_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
