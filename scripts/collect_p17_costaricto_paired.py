#!/usr/bin/env python3
"""Collect the STICKS P17 paired comparison on CostaRicto, under one frozen lock.

Same protocol as the C0026 P30 collection, driven by the campaign-parametric core
(``evaluation.p17_paired_collection``): admitted and prior-work-style arms interleaved in one
globally shuffled grid of (seed, repetition, arm) cells, a shared independent observer, a per-cell
reset and the retry budget. This harness only wires CostaRicto's model, lab transport, admitted
executors and target probe; the orchestration lives in the core.

``--dry-run`` replaces the model, transport, admitted executor and probe with deterministic fakes.
The real run needs the C0026/CostaRicto lab (`bash scripts/up_lab.sh --campaign 0.costaricto
--provider qemu`) and a loopback Ollama model. This does not touch the P30 lock or the C0045 v23.
"""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.admitted_step_execution import AdmittedExecutionResult  # noqa: E402
from evaluation.controlled_comparison import canonical_sha256  # noqa: E402
from evaluation.p17_paired_collection import (  # noqa: E402
    ARMS,
    CollectionBindings,
    CollectionConfig,
    CollectionRevisions,
    SimulatedStep,
    collect,
)
from evaluation.prior_work_execution import (  # noqa: E402
    CompletionOutcome,
    EffectProbeResult,
    PriorWorkStepReport,
    TargetExecutionResult,
)

CAMPAIGN_ID = "0.costaricto"
SUT_PROFILE_ID = "0.costaricto"
TARGET_HOST_ID = "target-linux-1"
TARGET_PRINCIPAL = "reconuser"
CONTRACT_PATH = PROJECT_ROOT / "data" / "runtime_contracts" / "costaricto.json"
REPORTS_PATH = PROJECT_ROOT / "data" / "p17" / "prior_work_reports" / "0.costaricto.json"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
# The two paired steps (discovery, collection) write only under /tmp/sticks_costaricto, owned by
# reconuser, so a plain removal clears a cell without sudo. A reset failure halts the run (not
# masked). The transfer step is excluded (its registered executor runs as a different principal).
TARGET_RESET_SCRIPT = "rm -rf /tmp/sticks_costaricto"


def load_reports_and_document() -> tuple[list[PriorWorkStepReport], dict]:
    document = json.loads(REPORTS_PATH.read_text(encoding="utf-8"))
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


def simulated_steps_from_contract() -> list[SimulatedStep]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return [
        SimulatedStep(
            step_id=f"s{occurrence['occurrence']}",
            occurrence=occurrence["occurrence"],
            technique_id=occurrence["technique_id"],
        )
        for occurrence in contract["occurrences"]
        if occurrence["mode"] != "real_controlled"
    ]


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
    import subprocess

    from executors.lab_transport import run_bash_on_target_vm

    def run_command(command: str, timeout_seconds: int, execution_user: str) -> TargetExecutionResult:
        started = time.perf_counter()
        # A model command that hangs (for example a server left running on the SSH channel) is a
        # model behaviour, not an infrastructure fault: classify the timeout as a typed non-zero
        # result the loop records as a failed attempt. Other transport faults still raise.
        try:
            result = run_bash_on_target_vm(
                SUT_PROFILE_ID, command, execution_user=execution_user, timeout=timeout_seconds
            )
        except subprocess.TimeoutExpired:
            return TargetExecutionResult(
                command=command,
                returncode=124,
                stdout="",
                stderr=f"command_timed_out_after_{timeout_seconds}s",
                elapsed_seconds=time.perf_counter() - started,
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
    from runners.costaricto_capability_observers import (
        costaricto_effect_request,
        observe_costaricto_effect,
    )

    def observe(report: PriorWorkStepReport) -> EffectProbeResult:
        request = costaricto_effect_request(
            report.observer_authority_id, scope, uuid4().hex, report.occurrence
        )
        observation = observe_costaricto_effect(request)
        return EffectProbeResult(
            authority_id=report.observer_authority_id,
            predicate_id=report.predicate_id,
            passed=observation.passed,
            raw_observation=observation.model_dump_json(),
        )

    return observe


def _executor_bindings() -> dict[str, tuple[str, str]]:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    return {
        occurrence["technique_id"]: (occurrence["executor_id"], occurrence["executor_sha256"])
        for occurrence in contract["occurrences"]
    }


def _verify_executor_binding(technique_id: str, executor, bindings: dict[str, tuple[str, str]]) -> None:
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
    from executors.executor_registry import registry
    from executors.registry_initializer import initialize_registry

    initialize_registry()
    bindings = _executor_bindings()

    def execute_admitted(technique_id: str) -> AdmittedExecutionResult:
        if technique_id not in bindings:
            raise ValueError(f"no runtime-contract binding for {technique_id}")
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


def build_dry_run_bindings() -> CollectionBindings:
    def make_complete(seed: int):
        def complete(system_prompt: str, user_prompt: str) -> CompletionOutcome:
            text = json.dumps({"command": "true", "rationale": "dry-run"})
            return CompletionOutcome(text=text, done_reason="stop", response_body=text)

        return complete

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

    return CollectionBindings(
        make_complete=lambda seed: make_complete(seed),
        run_command=run_command,
        execute_admitted=execute_admitted,
        observe_effect=observe,
        reset_target=lambda: None,
    )


def build_live_bindings(config: CollectionConfig, model_digest: str) -> CollectionBindings:
    from executors.lab_transport import run_bash_on_target_vm

    scope = discover_lab_scope(config.experiment_id)

    def reset_target() -> None:
        run_bash_on_target_vm(
            SUT_PROFILE_ID, TARGET_RESET_SCRIPT, execution_user=TARGET_PRINCIPAL, timeout=30
        )

    return CollectionBindings(
        make_complete=lambda seed: build_ollama_completion(config, seed, model_digest),
        run_command=build_lab_command_runner(),
        execute_admitted=build_lab_admitted_executor(),
        observe_effect=build_lab_effect_observer(scope),
        reset_target=reset_target,
    )


def build_lock_payload(
    config: CollectionConfig,
    document: dict,
    *,
    model_digest: str,
    runtime_id: str,
    oracle_revision: str,
    observer_revision: str,
) -> dict:
    source_relatives = (
        f"data/p17/prior_work_reports/{config.campaign_id}.json",
        "data/runtime_contracts/costaricto.json",
        "src/evaluation/prior_work_execution.py",
        "src/evaluation/admitted_step_execution.py",
        "src/evaluation/p17_paired_collection.py",
        "src/evaluation/feedback_cycle.py",
        "src/evaluation/controlled_comparison.py",
        "src/concretization/verifier.py",
        "src/executors/executor_registry.py",
        "src/runners/costaricto_capability_observers.py",
        "src/runners/capability_authority.py",
        "scripts/probe_costaricto_effects.py",
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--model", default="qwen3.6:latest")
    parser.add_argument("--seeds", type=int, nargs="+", default=[101, 102, 103])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--shuffle-seed", type=int, default=20261104)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    parser.add_argument("--timeout-seconds", type=int, default=120)
    parser.add_argument("--retry-limit", type=int, default=3)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reports, document = load_reports_and_document()
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

    if args.dry_run:
        model_digest, runtime_id = "0" * 64, "dry-run"
        bindings = build_dry_run_bindings()
    else:
        model_digest = ollama_model_digest(config.model)
        runtime_id = ollama_runtime_id()
        bindings = build_live_bindings(config, model_digest)

    lock_payload = build_lock_payload(
        config,
        document,
        model_digest=model_digest,
        runtime_id=runtime_id,
        oracle_revision=oracle_revision,
        observer_revision=observer_revision,
    )
    lock_bytes = json.dumps(lock_payload, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    (run_root / "collection-lock.json").write_bytes(lock_bytes)
    revisions = CollectionRevisions(
        admission_oracle=oracle_revision,
        observer=observer_revision,
        collection_lock_sha256=hashlib.sha256(lock_bytes).hexdigest(),
        proposal_budget_sha256=canonical_sha256(config.model_dump(mode="json")),
        max_attempts=config.retry_limit,
    )

    receipt = collect(
        reports=reports,
        simulated_steps=simulated_steps_from_contract(),
        config=config,
        bindings=bindings,
        revisions=revisions,
        run_root=run_root,
        receipt_extra={
            "collection_lock_sha256": revisions.collection_lock_sha256,
            "arm_note": "Paired local comparison on campaign 0.costaricto; the prior-work arm is not a reproduction of any prior end-to-end system.",
        },
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
