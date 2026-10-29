#!/usr/bin/env python3
"""Audit a proposal-only collection before using its statistical analysis."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from itertools import product
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from collect_controlled_comparison import (  # noqa: E402
    COMPARABLE_ARMS,
    collection_budget_sha,
    collection_oracle_revision,
    formal_comparison_manifest,
    load_campaign_fixture,
)
from evaluation.collection_lock import SAFE_IDENTIFIER, CollectionLock, verify_collection_sources  # noqa: E402
from evaluation.comparison_runner import StepObservation, compute_arm_metrics, observe_step  # noqa: E402
from evaluation.controlled_comparison import ControlledComparisonManifest, RunLedger  # noqa: E402


def expected_cells(lock: CollectionLock) -> dict[str, tuple[str, str, int, str]]:
    """Rebuild the complete cell set from the frozen campaign selection."""
    cells: dict[str, tuple[str, str, int, str]] = {}
    for campaign, arm, seed in product(lock.campaigns, COMPARABLE_ARMS, lock.seeds):
        for step in load_campaign_fixture(campaign).steps:
            cell = (campaign, arm.value, seed, step.step_id)
            filename = f"{campaign}__{arm.value}__seed{seed}__{step.step_id}.json"
            if filename in cells:
                raise ValueError(f"duplicate expected cell: {filename}")
            cells[filename] = cell
    return cells


def _audit_request(observation: StepObservation, lock: CollectionLock, filename: str) -> None:
    generation = observation.generation
    if generation is None:
        raise ValueError(f"missing raw generation receipt: {filename}")
    if observation.emitted and observation.proposal_record is None:
        raise ValueError(f"missing retained proposal record: {filename}")
    request = json.loads(generation.request_body)
    if not isinstance(request, dict) or not isinstance(request.get("options"), dict):
        raise ValueError(f"request has invalid envelope: {filename}")
    options = request["options"]
    expected = {
        "model": lock.model,
        "stream": False,
        "think": lock.thinking_mode,
    }
    for field, value in expected.items():
        if request.get(field) != value:
            raise ValueError(f"request {field} differs from lock: {filename}")
    for field, value in (
        ("seed", observation.seed),
        ("temperature", lock.temperature),
        ("num_predict", lock.max_output_tokens),
    ):
        if options.get(field) != value:
            raise ValueError(f"request option {field} differs from lock: {filename}")
    messages = request.get("messages")
    if lock.schema_version >= 2 and options.get("top_p") != lock.top_p:
        raise ValueError(f"request option top_p differs from lock: {filename}")
    if (
        not isinstance(messages, list)
        or not all(isinstance(item, dict) for item in messages)
        or [item.get("role") for item in messages] != ["system", "user"]
    ):
        raise ValueError(f"request has incomplete prompt roles: {filename}")
    if any(not isinstance(item.get("content"), str) or not item["content"] for item in messages):
        raise ValueError(f"request has empty prompt content: {filename}")


def audit_cache_cells(
    cache_dir: Path,
    expected: dict[str, tuple[str, str, int, str]],
    lock: CollectionLock,
) -> list[StepObservation]:
    actual_names = {entry.name for entry in cache_dir.iterdir()}
    missing = sorted(expected.keys() - actual_names)
    unexpected = sorted(actual_names - expected.keys())
    if missing or unexpected:
        raise ValueError(f"cache cell set differs: {len(missing)} missing, {len(unexpected)} unexpected")
    observations: list[StepObservation] = []
    for filename, identity in sorted(expected.items()):
        try:
            observation = StepObservation.model_validate_json((cache_dir / filename).read_text())
        except ValidationError as error:
            fields = [".".join(map(str, item["loc"])) for item in error.errors(include_input=False)]
            raise ValueError(f"invalid cached cell {filename}: {fields}") from None
        actual_identity = (
            observation.campaign_id,
            observation.arm_id.value,
            observation.seed,
            observation.step_id,
        )
        if actual_identity != identity:
            raise ValueError(f"cached identity differs from filename: {filename}")
        _audit_request(observation, lock, filename)
        observations.append(observation)
    return observations


def audit_manifest(directory: Path, lock: CollectionLock, cell_count: int) -> None:
    lock_path = directory / "collection-lock.json"
    manifest = json.loads((directory / "manifest.json").read_text())
    expected = {
        "experiment_id": lock.experiment_id,
        "study_scope": "proposal_only",
        "arm_ids": [arm.value for arm in COMPARABLE_ARMS],
        "model": lock.model,
        "ollama_model_digest": lock.ollama_model_digest,
        "temperature": lock.temperature,
        "thinking_mode": lock.thinking_mode,
        "campaigns": lock.campaigns,
        "seeds": lock.seeds,
        "shuffle_seed": lock.shuffle_seed,
        "cells": cell_count,
        "collection_lock_sha256": hashlib.sha256(lock_path.read_bytes()).hexdigest(),
    }
    if lock.schema_version >= 2:
        expected.update(top_p=lock.top_p, runtime_id=lock.runtime_id)
    for field, value in expected.items():
        if manifest.get(field) != value:
            raise ValueError(f"manifest {field} differs from frozen collection")
    if lock.schema_version >= 3:
        comparison = ControlledComparisonManifest.model_validate_json(
            (directory / "comparison-manifest.json").read_text())
        if comparison != formal_comparison_manifest(lock):
            raise ValueError("formal comparison differs from frozen collection")
        ledger = RunLedger.model_validate_json((directory / "comparison-ledger.json").read_text())
        ledger.validate_against(comparison)


def audit_metrics(directory: Path, observations: list[StepObservation]) -> None:
    stored = json.loads((directory / "metrics.json").read_text())
    computed = {
        arm.value: compute_arm_metrics(observations, arm).model_dump()
        for arm in COMPARABLE_ARMS
    }
    if stored != computed:
        raise ValueError("stored metrics differ from cached observations")


def audit_semantic_replay(observations: list[StepObservation], lock: CollectionLock) -> None:
    """Recompute each cached decision from its raw model reply without network calls."""
    fixtures = {campaign: load_campaign_fixture(campaign) for campaign in lock.campaigns}
    steps = {
        (campaign, step.step_id): step
        for campaign, fixture in fixtures.items()
        for step in fixture.steps
    }
    budget_sha = collection_budget_sha(lock)
    oracle_revision = collection_oracle_revision(lock)
    for observation in observations:
        filename = (
            f"{observation.campaign_id}__{observation.arm_id.value}__"
            f"seed{observation.seed}__{observation.step_id}.json"
        )
        generation = observation.generation
        if generation is None:
            raise ValueError(f"missing raw generation receipt: {filename}")
        request = json.loads(generation.request_body)
        response = json.loads(generation.response_body)
        raw_output = response["message"]["content"]
        expected_messages = request["messages"]
        exchanges = 0

        def complete(system_prompt: str, user_prompt: str) -> str:
            nonlocal exchanges
            exchanges += 1
            actual_messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
            if exchanges != 1 or actual_messages != expected_messages:
                raise ValueError(f"generated prompt differs from frozen request: {filename}")
            return raw_output

        replayed = observe_step(
            observation.arm_id,
            steps[(observation.campaign_id, observation.step_id)],
            fixtures[observation.campaign_id],
            observation.seed,
            experiment_id=lock.experiment_id,
            budget_sha=budget_sha,
            oracle_revision=oracle_revision,
            complete=complete,
            retain_proposal=observation.proposal_record is not None,
        )
        if exchanges != 1 or replayed.model_dump(exclude={"generation"}) != observation.model_dump(exclude={"generation"}):
            raise ValueError(f"cached decision differs from raw model reply: {filename}")


def audit_collection(experiment_id: str) -> int:
    if SAFE_IDENTIFIER.fullmatch(experiment_id) is None:
        raise ValueError("experiment ID must be a simple identifier")
    directory = PROJECT_ROOT / "release/experiments/controlled_comparison" / experiment_id
    lock = verify_collection_sources(PROJECT_ROOT, directory)
    expected = expected_cells(lock)
    audit_manifest(directory, lock, len(expected))
    observations = audit_cache_cells(directory / "cache", expected, lock)
    audit_semantic_replay(observations, lock)
    audit_metrics(directory, observations)
    return len(observations)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", required=True)
    args = parser.parse_args()
    count = audit_collection(args.experiment_id)
    print(f"qualified collection preflight: {count} complete proposal cells")
    print("analysis and independent SUT effects require separate qualification")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
