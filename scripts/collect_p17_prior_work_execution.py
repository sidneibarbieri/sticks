#!/usr/bin/env python3
"""Collect the STICKS P17 prior-work EXECUTED arm on one campaign, under a frozen lock.

For each (seed, repetition) cell the observed campaign steps run in order through the bounded
report->command->execute->observe loop (``evaluation.prior_work_execution``); the simulated step is
recorded directly. The grid is globally shuffled with a fixed seed, each cell is cached (resume is
free and never re-spends), and every attempt records the model stop reason so a truncated reply is
a typed failure, never a (false) abstention. The frozen receipt reports, per step, the observed and
failed counts with their typed failure reasons and the spread across repetitions.

``--dry-run`` replaces the live model, the lab transport and the probe with deterministic fakes so
the harness is validated without a provisioned lab or a model. The real run requires the C0026 lab
(``bash scripts/up_lab.sh --campaign 0.c0026 --provider qemu``) and a loopback Ollama model.

This arm is ``prior_work_style`` executed locally; it is never a reproduction of a prior end-to-end
system (for example Choi et al.).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import StrictModel  # noqa: E402
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
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
# Artifacts the attacker creates; removed before each cell so repetitions are independent. Source
# fixtures seeded by provisioning are never touched.
TARGET_RESET_SCRIPT = (
    "rm -rf /tmp/sticks_t1005 /tmp/sticks_downloaded_payload.sh "
    "/tmp/sticks_collected_data.tar.gz /tmp/sticks_chunk.* /tmp/sticks_dynamic_resolution.txt; "
    "sudo sed -i '/c2.dynamic.local/d' /etc/hosts 2>/dev/null || "
    "sed -i '/c2.dynamic.local/d' /etc/hosts 2>/dev/null || true"
)


class CollectionConfig(StrictModel):
    """Frozen collection parameters for one prior-work executed campaign."""

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
    step_id: str
    occurrence: int
    technique_id: str
    effect_class: str
    attempts: int
    failure_reason: str | None = None


class CellResult(StrictModel):
    seed: int
    repetition: int
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
    """Hash the admission oracle sources (the verifier and the comparison contract)."""
    sources = {
        relative: hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        for relative in (
            "src/concretization/verifier.py",
            "src/evaluation/controlled_comparison.py",
        )
    }
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode("utf-8")).hexdigest()


def ollama_model_digest(model: str) -> str:
    request = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/tags")
    with urllib.request.urlopen(request, timeout=10) as response:
        tags = json.load(response)
    matches = [entry["digest"] for entry in tags["models"] if entry["name"] == model]
    if len(matches) != 1 or len(matches[0]) != 64:
        raise ValueError(f"Ollama did not return a single valid digest for {model}")
    return matches[0]


def ollama_runtime_id() -> str:
    request = urllib.request.Request(f"{OLLAMA_BASE_URL}/api/version")
    with urllib.request.urlopen(request, timeout=10) as response:
        return f"ollama:{json.load(response)['version']}"


def build_ollama_completion(config: CollectionConfig, seed: int, expected_digest: str):
    """Return a completion callable that exposes the stop reason for the truncation gate."""

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
            f"{OLLAMA_BASE_URL}/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
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


def observer_revision_for(reports: list[PriorWorkStepReport]) -> str:
    from runners.capability_authority import registered_authority_revision

    return registered_authority_revision({report.observer_authority_id for report in reports})


def build_dry_run_bindings(reports: list[PriorWorkStepReport]):
    """Deterministic fakes: every observed step succeeds on the first attempt."""

    def complete(system_prompt: str, user_prompt: str) -> CompletionOutcome:
        text = json.dumps({"command": "true", "rationale": "dry-run"})
        return CompletionOutcome(text=text, done_reason="stop", response_body=text)

    def run_command(command: str, timeout_seconds: int, execution_user: str) -> TargetExecutionResult:
        return TargetExecutionResult(
            command=command, returncode=0, stdout="", stderr="", elapsed_seconds=0.0
        )

    def observe(report: PriorWorkStepReport) -> EffectProbeResult:
        raw = json.dumps({"passed": True, "dry_run": True}, sort_keys=True)
        return EffectProbeResult(
            authority_id=report.observer_authority_id,
            predicate_id=report.predicate_id,
            passed=True,
            raw_observation=raw,
        )

    return complete, run_command, observe


def run_cell(
    *,
    seed: int,
    repetition: int,
    reports: list[PriorWorkStepReport],
    make_complete,
    run_command,
    observe_effect,
    reset_target,
    oracle_revision: str,
    observer_revision: str,
    lock_sha256: str,
    budget_sha256: str,
    cell_root: Path,
) -> CellResult:
    reset_target()
    steps = [
        StepOutcome(
            step_id=f"s{SIMULATED_OCCURRENCE}",
            occurrence=SIMULATED_OCCURRENCE,
            technique_id=SIMULATED_TECHNIQUE,
            effect_class=EffectClass.simulated.value,
            attempts=0,
        )
    ]
    for report in reports:
        result = run_prior_work_step(
            report,
            seed=seed,
            complete=make_complete(seed),
            run_command=run_command,
            observe_effect=observe_effect,
            admission_oracle_revision=oracle_revision,
            observer_revision=observer_revision,
            collection_lock_sha256=lock_sha256,
            proposal_budget_sha256=budget_sha256,
            evidence_root=cell_root,
            max_attempts=1 + _retry_budget(report),
        )
        terminal = result.attempts[-1].feedback
        steps.append(
            StepOutcome(
                step_id=report.step_id,
                occurrence=report.occurrence,
                technique_id=report.technique_id,
                effect_class=terminal.effect.effect_class.value,
                attempts=len(result.attempts),
                failure_reason=terminal.failure_reason,
            )
        )
    return CellResult(seed=seed, repetition=repetition, steps=steps)


def _retry_budget(report: PriorWorkStepReport) -> int:
    # The retry budget is uniform; the per-report hook keeps the call site explicit for future
    # per-step budgets without changing the loop contract.
    return _RETRY_BUDGET


_RETRY_BUDGET = 2


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
        "src/evaluation/feedback_cycle.py",
        "src/evaluation/controlled_comparison.py",
        "src/concretization/verifier.py",
        "src/runners/c0026_capability_observers.py",
        "src/runners/capability_authority.py",
        "scripts/probe_c0026_target.py",
    )
    source_sha256 = {
        relative: hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
        for relative in source_relatives
    }
    payload = {
        "schema": "sticks-p17-prior-work-collection-lock/v1",
        "config": config.model_dump(mode="json"),
        "ollama_model_digest": model_digest,
        "ollama_runtime_id": runtime_id,
        "thinking_mode": False,
        "admission_oracle_revision": oracle_revision,
        "observer_revision": observer_revision,
        "reports_schema_version": document["schema_version"],
        "source_sha256": source_sha256,
    }
    return payload


def aggregate_receipt(config: CollectionConfig, cells: list[CellResult]) -> dict[str, object]:
    by_step: dict[str, dict[str, object]] = {}
    for cell in cells:
        for step in cell.steps:
            bucket = by_step.setdefault(
                step.step_id,
                {
                    "occurrence": step.occurrence,
                    "technique_id": step.technique_id,
                    "target_observed": 0,
                    "simulated": 0,
                    "failed": 0,
                    "failure_reasons": {},
                    "attempts_total": 0,
                },
            )
            bucket["attempts_total"] += step.attempts
            if step.effect_class == EffectClass.target_observed.value:
                bucket["target_observed"] += 1
            elif step.effect_class == EffectClass.simulated.value:
                bucket["simulated"] += 1
            else:
                bucket["failed"] += 1
                reasons = bucket["failure_reasons"]
                reasons[step.failure_reason] = reasons.get(step.failure_reason, 0) + 1
    return {
        "schema": "sticks-p17-prior-work-receipt/v1",
        "arm_id": "prior_work_style",
        "arm_note": "Executed prior-work baseline on the local C0026 lab; not a reproduction of any prior end-to-end system.",
        "campaign_id": config.campaign_id,
        "cells": len(cells),
        "seeds": config.seeds,
        "repetitions": config.repetitions,
        "steps": by_step,
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


def main() -> int:
    global _RETRY_BUDGET
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
    _RETRY_BUDGET = config.retry_limit - 1
    oracle_revision = admission_oracle_revision()
    observer_revision = observer_revision_for(reports)
    if oracle_revision == observer_revision:
        raise ValueError("independent observer must differ from the admission oracle")

    run_root = args.run_root.resolve()
    run_root.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        model_digest = "0" * 64
        runtime_id = "dry-run"
        complete_fn, run_command, observe_effect = build_dry_run_bindings(reports)

        def make_complete(seed: int):
            return complete_fn

        def reset_target() -> None:
            return None

    else:
        model_digest = ollama_model_digest(config.model)
        runtime_id = ollama_runtime_id()
        scope = discover_lab_scope(config.experiment_id)
        from executors.lab_transport import run_bash_on_target_vm

        run_command = build_lab_command_runner()
        observe_effect = build_lab_effect_observer(scope)

        def make_complete(seed: int):
            return build_ollama_completion(config, seed, model_digest)

        def reset_target() -> None:
            run_bash_on_target_vm(
                SUT_PROFILE_ID, TARGET_RESET_SCRIPT, execution_user=TARGET_PRINCIPAL, timeout=30
            )

    lock_payload = build_lock_payload(
        config,
        document,
        model_digest=model_digest,
        runtime_id=runtime_id,
        oracle_revision=oracle_revision,
        observer_revision=observer_revision,
    )
    lock_path = run_root / "collection-lock.json"
    lock_bytes = json.dumps(lock_payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    lock_path.write_bytes(lock_bytes)
    lock_sha256 = hashlib.sha256(lock_bytes).hexdigest()
    budget_sha256 = canonical_sha256(config.model_dump(mode="json"))

    cells_grid = [
        (seed, repetition)
        for seed in config.seeds
        for repetition in range(1, config.repetitions + 1)
    ]
    random.Random(config.shuffle_seed).shuffle(cells_grid)

    cells: list[CellResult] = []
    for seed, repetition in cells_grid:
        cell_root = run_root / "cells" / f"seed_{seed}_rep_{repetition}"
        cached = cell_root / "cell_result.json"
        if cached.exists():
            cells.append(CellResult.model_validate_json(cached.read_text(encoding="utf-8")))
            continue
        cell_root.mkdir(parents=True, exist_ok=False)
        result = run_cell(
            seed=seed,
            repetition=repetition,
            reports=reports,
            make_complete=make_complete,
            run_command=run_command,
            observe_effect=observe_effect,
            reset_target=reset_target,
            oracle_revision=oracle_revision,
            observer_revision=observer_revision,
            lock_sha256=lock_sha256,
            budget_sha256=budget_sha256,
            cell_root=cell_root,
        )
        cached.write_text(result.model_dump_json(indent=2), encoding="utf-8")
        cells.append(result)
        print(f"cell seed={seed} rep={repetition} done", flush=True)

    receipt = aggregate_receipt(config, cells)
    receipt["collection_lock_sha256"] = lock_sha256
    (run_root / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
