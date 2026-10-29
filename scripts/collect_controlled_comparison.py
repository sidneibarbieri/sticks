#!/usr/bin/env python3
"""Collect the controlled comparison over real campaign fixtures.

Loads a campaign's reference plan into per-step fixtures (with the sequential fact-state the
reference commits), then runs each arm through the shared collection runner. A local model serves
the proposals; the harness is frozen, so this script only collects and never edits it.

Smoke mode runs one seed on the first steps to confirm the live wiring before a full campaign.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from itertools import product
from pathlib import Path
from typing import Callable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import action_catalog_hash  # noqa: E402
from evaluation.comparison_runner import (  # noqa: E402
    CampaignFixture,
    GenerationReceipt,
    StepFixture,
    StepObservation,
    compute_arm_metrics,
    observe_step,
)
from evaluation.collection_lock import (  # noqa: E402
    CollectionLock,
    build_collection_lock,
    prepare_collection_directory,
)
from evaluation.controlled_comparison import (  # noqa: E402
    ArmId,
    ArmDefinition,
    ControlledComparisonManifest,
    GeneratorBudget,
    RunLedger,
    RunRecord,
    canonical_sha256,
)

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
COMPARABLE_ARMS = (
    ArmId.prior_work_style,
    ArmId.sticks_without_admission,
    ArmId.sticks_admitted,
)
MAX_OUTPUT_TOKENS = 512
TIMEOUT_SECONDS = 300
RETRY_LIMIT = 3


def collection_budget_sha(lock: CollectionLock) -> str:
    """Derive the proposal budget identifier from the frozen model settings."""
    if lock.schema_version >= 3:
        return formal_generator_budget(lock).comparison_sha256()
    fields = {
        "model": lock.model,
        "model_digest": lock.ollama_model_digest,
        "temperature": lock.temperature,
        "thinking_mode": lock.thinking_mode,
        "max_output_tokens": lock.max_output_tokens,
        "timeout_seconds": lock.timeout_seconds,
        "retry_limit": lock.retry_limit,
    }
    if lock.schema_version >= 2:
        fields.update(top_p=lock.top_p, runtime_id=lock.runtime_id)
    return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


def formal_generator_budget(lock: CollectionLock) -> GeneratorBudget:
    """Represent the frozen multi-arm prompt policy and generation resource limits."""
    if lock.schema_version < 3:
        raise ValueError("formal comparison requires collection schema 3 or newer")
    prompt_paths = (
        "src/evaluation/prior_work_planner.py",
        "src/evaluation/sticks_arm_planner.py",
        "src/evaluation/proposal_view.py",
        "src/evaluation/comparison_runner.py",
    )
    prompt_sources = {path: lock.source_sha256[path] for path in prompt_paths}
    return GeneratorBudget(
        model_id=lock.model,
        model_artifact_sha256=lock.ollama_model_digest,
        runtime_id=lock.runtime_id,
        prompt_template_sha256=canonical_sha256(prompt_sources),
        temperature=lock.temperature,
        top_p=lock.top_p,
        max_output_tokens=lock.max_output_tokens,
        max_proposal_calls_per_step=1,
        max_retries_per_step=lock.retry_limit - 1,
        timeout_seconds_per_step=lock.timeout_seconds,
    )


def formal_comparison_manifest(lock: CollectionLock) -> ControlledComparisonManifest:
    """Build the four-arm design from the frozen inputs without altering evidence."""
    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text())["templates"]
    ]
    budget = formal_generator_budget(lock)
    manifest = ControlledComparisonManifest(
        experiment_id=lock.experiment_id,
        protocol_sha256=canonical_sha256(lock.model_dump(mode="json")),
        campaigns=lock.campaigns,
        seeds=lock.seeds,
        arms=[
            ArmDefinition(arm_id=arm, proposal_budget=budget) for arm in COMPARABLE_ARMS
        ]
        + [
            ArmDefinition(
                arm_id=ArmId.sticks_autosut_executed, consumes_arm=ArmId.sticks_admitted
            )
        ],
        oracle_revision=collection_oracle_revision(lock),
        action_catalog_sha256=action_catalog_hash(templates),
    )
    manifest.validate_collection_ready()
    return manifest


def prepare_formal_comparison(directory: Path, lock: CollectionLock) -> None:
    """Write the four-arm design and planned grid before any model generation."""
    manifest = formal_comparison_manifest(lock)
    manifest_path = directory / "comparison-manifest.json"
    if manifest_path.exists():
        if (
            ControlledComparisonManifest.model_validate_json(manifest_path.read_text())
            != manifest
        ):
            raise ValueError("formal comparison differs from frozen manifest")
    else:
        with manifest_path.open("x") as output:
            output.write(manifest.model_dump_json(indent=2) + "\n")
    ledger_path = directory / "comparison-ledger.json"
    if not ledger_path.exists():
        ledger = RunLedger(
            experiment_id=lock.experiment_id,
            records=[
                RunRecord(campaign_id=campaign, arm_id=arm, seed=seed, status="planned")
                for campaign, arm, seed in sorted(manifest.planned_run_keys())
            ],
        )
        ledger.validate_against(manifest)
        with ledger_path.open("x") as output:
            output.write(ledger.model_dump_json(indent=2) + "\n")
    else:
        RunLedger.model_validate_json(ledger_path.read_text()).validate_against(
            manifest
        )


def collection_oracle_revision(lock: CollectionLock) -> str:
    """Derive the blinded oracle revision used by every collected cell."""
    sources = {
        path: lock.source_sha256[path]
        for path in (
            "src/concretization/verifier.py",
            "src/evaluation/controlled_comparison.py",
        )
    }
    return hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()


def align_plan_steps(
    procedural_steps: list[dict], concretized_steps: list[dict]
) -> list[tuple[dict, dict]]:
    """Reject plan pairs that would assign a step the wrong procedure context."""
    if len(procedural_steps) != len(concretized_steps):
        raise ValueError("procedural and concretized plans have different step counts")
    ordered_steps = sorted(concretized_steps, key=lambda step: step["sequence"])
    procedural_by_technique = {step["technique_id"]: step for step in procedural_steps}
    concretized_techniques = [step["technique_id"] for step in ordered_steps]
    if len(procedural_by_technique) != len(procedural_steps) or len(
        set(concretized_techniques)
    ) != len(ordered_steps):
        raise ValueError("repeated technique needs an explicit step identity")
    if set(procedural_by_technique) != set(concretized_techniques):
        raise ValueError("procedural and concretized plans have a technique mismatch")
    for expected_sequence, concretized_step in enumerate(ordered_steps, start=1):
        if concretized_step["sequence"] != expected_sequence:
            raise ValueError(
                f"concretized plan sequence mismatch at step {expected_sequence}"
            )
    return [
        (procedural_by_technique[step["technique_id"]], step) for step in ordered_steps
    ]


def load_campaign_fixture(campaign_id: str) -> CampaignFixture:
    procedural = json.loads(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text()
    )
    concretized = json.loads(
        (PLANS_DIR / f"{campaign_id}.concretized-plan.json").read_text()
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text()
    )
    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text())["templates"]
    ]
    aligned_steps = align_plan_steps(procedural["steps"], concretized["steps"])

    steps: list[StepFixture] = []
    known_facts = set(catalog.initial_facts)
    for procedural_step, concretized_step in aligned_steps:
        steps.append(
            StepFixture(
                step_id=f"s{concretized_step['sequence']}",
                technique_id=concretized_step["technique_id"],
                execution_domain=procedural_step["execution_domain"],
                objective=procedural_step.get("name")
                or concretized_step["technique_id"],
                tactic=(procedural_step.get("tactics") or ["unknown"])[0],
                known_facts=sorted(known_facts),
            )
        )
        known_facts |= set(concretized_step["produces"])
    return CampaignFixture(
        campaign_id=campaign_id, steps=steps, templates=templates, catalog=catalog
    )


def ollama_model_digest(model: str) -> str:
    with urllib.request.urlopen(
        "http://localhost:11434/api/tags", timeout=10
    ) as response:
        available = json.load(response)["models"]
    matches = [entry for entry in available if entry["name"] == model]
    if len(matches) != 1:
        raise ValueError(f"model tag is not uniquely available in Ollama: {model}")
    digest = matches[0]["digest"]
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
        raise ValueError(f"Ollama returned an invalid model digest for {model}")
    return digest


def ollama_runtime_id() -> str:
    with urllib.request.urlopen(
        "http://localhost:11434/api/version", timeout=10
    ) as response:
        version = json.load(response)["version"]
    if not isinstance(version, str) or not version.strip():
        raise ValueError("Ollama returned an empty runtime version")
    return f"ollama:{version}"


def ensure_thinking_mode_supported(model: str, thinking_mode: bool | str) -> None:
    request = urllib.request.Request(
        "http://localhost:11434/api/show",
        data=json.dumps({"model": model}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        values = json.load(response).get("thinking", {}).get("values", [])
    if thinking_mode not in values:
        raise ValueError(
            f"model {model} does not support thinking mode {thinking_mode!r}"
        )


def parse_thinking_mode(value: str) -> bool | str:
    if value == "off":
        return False
    if value == "on":
        return True
    return value


def ollama_completion(
    model: str,
    temperature: float,
    seed: int,
    expected_digest: str | None = None,
    thinking_mode: bool | str = False,
    receipt_sink: Callable[[GenerationReceipt], None] | None = None,
    top_p: float = 1.0,
    expected_runtime_id: str | None = None,
):
    def complete(system_prompt: str, user_prompt: str) -> str:
        if (
            expected_digest is not None
            and ollama_model_digest(model) != expected_digest
        ):
            raise RuntimeError(f"model artifact changed during collection: {model}")
        if (
            expected_runtime_id is not None
            and ollama_runtime_id() != expected_runtime_id
        ):
            raise RuntimeError("Ollama runtime changed during collection")
        body = json.dumps(
            {
                "model": model,
                "stream": False,
                "think": thinking_mode,
                "options": {
                    "temperature": temperature,
                    "top_p": top_p,
                    "seed": seed,
                    "num_predict": MAX_OUTPUT_TOKENS,
                },
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            "http://localhost:11434/api/chat",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        # A network or 5xx failure is transient and retried; the run halts if retries are
        # exhausted rather than recording a model failure that never happened.
        started = time.perf_counter()
        for attempt in range(RETRY_LIMIT):
            try:
                with urllib.request.urlopen(
                    request, timeout=TIMEOUT_SECONDS
                ) as response:
                    response_body = response.read().decode("utf-8")
                raw_output = json.loads(response_body)["message"]["content"]
                if receipt_sink is not None:
                    receipt_sink(
                        GenerationReceipt(
                            request_body=body.decode("utf-8"),
                            response_body=response_body,
                            raw_output_sha256=hashlib.sha256(
                                raw_output.encode("utf-8")
                            ).hexdigest(),
                            recorded_at=datetime.now(timezone.utc).isoformat(),
                            elapsed_seconds=time.perf_counter() - started,
                            attempt_count=attempt + 1,
                        )
                    )
                return raw_output
            except urllib.error.HTTPError as error:
                if error.code != 429 and error.code < 500:
                    raise
                if attempt == RETRY_LIMIT - 1:
                    raise
                time.sleep(2 * (attempt + 1))
            except (urllib.error.URLError, TimeoutError):
                if attempt == RETRY_LIMIT - 1:
                    raise
                time.sleep(2 * (attempt + 1))
        raise RuntimeError("unreachable")

    return complete


def run_smoke(args: argparse.Namespace) -> int:
    fixture = load_campaign_fixture(args.campaign)
    thinking_mode = parse_thinking_mode(args.thinking)
    ensure_thinking_mode_supported(args.model, thinking_mode)
    complete = ollama_completion(
        args.model,
        args.temperature,
        args.seed,
        thinking_mode=thinking_mode,
        top_p=args.top_p,
    )
    observations = []
    for arm_id in COMPARABLE_ARMS:
        for step in fixture.steps[: args.smoke_steps]:
            observation = observe_step(
                arm_id,
                step,
                fixture,
                args.seed,
                experiment_id=f"smoke-{args.campaign}",
                budget_sha="0" * 64,
                oracle_revision="0" * 64,
                complete=complete,
            )
            observations.append(observation)
            print(
                f"{arm_id.value:26} step={step.step_id:4} technique={step.technique_id:12} "
                f"emitted={observation.emitted} admitted={observation.oracle_admitted} "
                f"abstained={observation.abstained} template={observation.template_id}"
            )
    print("\n--- per-arm metrics (smoke) ---")
    for arm_id in COMPARABLE_ARMS:
        metrics = compute_arm_metrics(observations, arm_id)
        print(f"{arm_id.value:26} {metrics.model_dump_json()}")
    return 0


def run_full(args: argparse.Namespace) -> int:
    campaigns = args.campaigns.split(",")
    seeds = list(range(1, args.seeds + 1))
    experiment_id = args.experiment_id
    out_dir = (
        PROJECT_ROOT
        / "release"
        / "experiments"
        / "controlled_comparison"
        / experiment_id
    )
    model_digest = ollama_model_digest(args.model)
    runtime_id = ollama_runtime_id()
    thinking_mode = parse_thinking_mode(args.thinking)
    ensure_thinking_mode_supported(args.model, thinking_mode)
    collection_lock = build_collection_lock(
        PROJECT_ROOT,
        experiment_id=experiment_id,
        model=args.model,
        ollama_model_digest=model_digest,
        temperature=args.temperature,
        top_p=args.top_p,
        runtime_id=runtime_id,
        thinking_mode=thinking_mode,
        max_output_tokens=MAX_OUTPUT_TOKENS,
        timeout_seconds=TIMEOUT_SECONDS,
        retry_limit=RETRY_LIMIT,
        campaigns=campaigns,
        seeds=seeds,
        shuffle_seed=args.shuffle_seed,
    )
    lock_path = prepare_collection_directory(
        out_dir, collection_lock, project_root=PROJECT_ROOT
    )
    prepare_formal_comparison(out_dir, collection_lock)
    budget_sha = collection_budget_sha(collection_lock)
    oracle_revision = collection_oracle_revision(collection_lock)
    fixtures = {campaign: load_campaign_fixture(campaign) for campaign in campaigns}
    cache_dir = out_dir / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)

    cells = [
        (campaign, arm_id, seed, index)
        for campaign, arm_id, seed in product(campaigns, COMPARABLE_ARMS, seeds)
        for index in range(len(fixtures[campaign].steps))
    ]
    random.Random(args.shuffle_seed).shuffle(cells)
    expected_cache_names = {
        f"{campaign}__{arm_id.value}__seed{seed}__{fixtures[campaign].steps[index].step_id}.json"
        for campaign, arm_id, seed, index in cells
    }
    if len(expected_cache_names) != len(cells):
        raise ValueError("campaign steps do not have unique cache identities")
    unexpected_cache_names = {
        path.name for path in cache_dir.iterdir()
    } - expected_cache_names
    if unexpected_cache_names:
        raise ValueError(f"unexpected cached cells: {sorted(unexpected_cache_names)}")

    observations = []
    for position, (campaign, arm_id, seed, index) in enumerate(cells, start=1):
        step = fixtures[campaign].steps[index]
        cache_path = (
            cache_dir / f"{campaign}__{arm_id.value}__seed{seed}__{step.step_id}.json"
        )
        if cache_path.exists():
            cached = StepObservation.model_validate_json(cache_path.read_text())
            if (cached.campaign_id, cached.arm_id, cached.seed, cached.step_id) != (
                campaign,
                arm_id,
                seed,
                step.step_id,
            ):
                raise ValueError(
                    f"cached cell identity differs from its path: {cache_path}"
                )
            if cached.generation is None:
                raise ValueError(
                    f"prospective cached cell lacks a generation receipt: {cache_path}"
                )
            if cached.emitted and cached.proposal_record is None:
                raise ValueError(
                    f"prospective emitted cell lacks its proposal record: {cache_path}"
                )
            observations.append(cached)
            continue
        receipts: list[GenerationReceipt] = []
        complete = ollama_completion(
            args.model,
            args.temperature,
            seed,
            model_digest,
            thinking_mode,
            receipt_sink=receipts.append,
            top_p=collection_lock.top_p,
            expected_runtime_id=runtime_id,
        )
        observation = observe_step(
            arm_id,
            step,
            fixtures[campaign],
            seed,
            experiment_id=experiment_id,
            budget_sha=budget_sha,
            oracle_revision=oracle_revision,
            complete=complete,
            retain_proposal=True,
        )
        if len(receipts) != 1:
            raise RuntimeError(
                f"cell produced {len(receipts)} model exchanges: {cache_path.name}"
            )
        observation.generation = receipts[0]
        temporary_path = cache_path.with_suffix(".json.tmp")
        temporary_path.write_text(observation.model_dump_json(indent=2) + "\n")
        temporary_path.replace(cache_path)
        observations.append(observation)
        if position % 20 == 0:
            print(f"[{position}/{len(cells)}] collected", flush=True)

    metrics = {
        arm_id.value: compute_arm_metrics(observations, arm_id).model_dump()
        for arm_id in COMPARABLE_ARMS
    }
    manifest = {
        "experiment_id": experiment_id,
        "study_scope": "proposal_only",
        "arm_ids": [arm_id.value for arm_id in COMPARABLE_ARMS],
        "model": args.model,
        "ollama_model_digest": model_digest,
        "temperature": args.temperature,
        "top_p": collection_lock.top_p,
        "runtime_id": collection_lock.runtime_id,
        "thinking_mode": thinking_mode,
        "campaigns": campaigns,
        "seeds": seeds,
        "shuffle_seed": args.shuffle_seed,
        "cells": len(cells),
        "collection_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print("\n--- per-arm metrics (full) ---")
    for arm_id in COMPARABLE_ARMS:
        entry = metrics[arm_id.value]
        print(
            f"{arm_id.value:26} steps={entry['steps']} emitted={entry['emitted']} "
            f"valid={entry['oracle_valid']} abstained={entry['abstained']} "
            f"validity_rate={entry['validity_rate']:.3f} "
            f"abstention_rate={entry['abstention_rate']:.3f} "
            f"divergence={entry['mean_distinct_templates_per_step']:.3f}"
        )
    print(f"\nwrote {out_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--full", action="store_true", help="run the frozen multi-seed campaign"
    )
    parser.add_argument("--campaign", default="C0045", help="smoke campaign")
    parser.add_argument(
        "--campaigns", default="C0010,C0026,C0045", help="full-run campaigns"
    )
    parser.add_argument("--model", default="gpt-oss:20b")
    parser.add_argument("--temperature", type=float, default=0.7)
    parser.add_argument("--top-p", type=float, default=1.0)
    parser.add_argument(
        "--thinking",
        choices=("off", "on", "low", "medium", "high"),
        default="off",
        help="explicit Ollama thinking mode, checked against /api/show and frozen in the lock",
    )
    parser.add_argument("--seed", type=int, default=1, help="smoke seed")
    parser.add_argument("--seeds", type=int, default=5, help="full-run seed count")
    parser.add_argument("--shuffle-seed", type=int, default=20260907)
    parser.add_argument("--experiment-id", default="2026-09-07-local")
    parser.add_argument("--smoke-steps", type=int, default=1)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return run_full(args) if args.full else run_smoke(args)


if __name__ == "__main__":
    raise SystemExit(main())
