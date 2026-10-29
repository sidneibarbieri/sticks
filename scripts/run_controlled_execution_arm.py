#!/usr/bin/env python3
"""Execute one admitted comparison cell through the revision-bound runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_ROOT))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from concretization.pipeline import action_catalog_hash  # noqa: E402
from evaluation.collection_lock import verify_collection_sources  # noqa: E402
from evaluation.comparison_runner import (  # noqa: E402
    StepObservation,
    build_admitted_campaign_plan,
)
from evaluation.execution_bridge import build_execution_semantic_bridge  # noqa: E402
from evaluation.execution_study import run_revision_bound_execution  # noqa: E402
from runners.campaign_runner import UnifiedCampaignRunner  # noqa: E402
from runners.runtime_campaign_report import RuntimeCampaignReport  # noqa: E402


def _git_revision() -> str:
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no", "--", "."],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    if status.stdout:
        raise ValueError("qualified execution requires a clean tracked artifact checkout")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _oracle_revision(source_sha256: dict[str, str]) -> str:
    paths = (
        "src/concretization/verifier.py",
        "src/evaluation/controlled_comparison.py",
    )
    sources = {path: source_sha256[path] for path in paths}
    return hashlib.sha256(
        json.dumps(sources, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _expected_step_ids(concretized_plan_path: Path) -> list[str]:
    document = json.loads(concretized_plan_path.read_text(encoding="utf-8"))
    steps = sorted(document["steps"], key=lambda step: step["sequence"])
    expected_sequences = list(range(1, len(steps) + 1))
    if [step["sequence"] for step in steps] != expected_sequences:
        raise ValueError("concretized plan sequence is not contiguous")
    return [f"s{sequence}" for sequence in expected_sequences]


def _load_observations(collection_dir: Path) -> list[StepObservation]:
    cache_dir = collection_dir / "cache"
    if not cache_dir.is_dir():
        raise ValueError("controlled comparison collection lacks a cache directory")
    return [
        StepObservation.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(cache_dir.glob("*.json"))
    ]


def _execute_runtime(
    runtime_campaign_id: str, runtime_output: Path
) -> tuple[RuntimeCampaignReport, bytes]:
    report = UnifiedCampaignRunner(
        runtime_campaign_id,
        output_dir=runtime_output,
        require_lab=True,
    ).run()
    if not isinstance(report, RuntimeCampaignReport):
        raise TypeError("controlled execution arm requires a typed runtime report")
    summary_path = runtime_output / "runtime-v2" / report.run_id / "summary.json"
    return report, summary_path.read_bytes()


def run(args: argparse.Namespace) -> int:
    collection_dir = args.collection_dir.resolve()
    lock = verify_collection_sources(PROJECT_ROOT, collection_dir)
    if args.campaign not in lock.campaigns or args.seed not in lock.seeds:
        raise ValueError("campaign and seed must belong to the frozen collection lock")
    revision = _git_revision()
    collection_lock_path = collection_dir / "collection-lock.json"
    collection_lock_sha256 = hashlib.sha256(collection_lock_path.read_bytes()).hexdigest()

    concretized_plan_path = (
        PROJECT_ROOT / "release" / "plans" / f"{args.campaign}.concretized-plan.json"
    )
    runtime_contract_path = (
        PROJECT_ROOT
        / "data"
        / "runtime_contracts"
        / f"{args.campaign.lower()}.json"
    )
    plan = build_admitted_campaign_plan(
        _load_observations(collection_dir),
        experiment_id=lock.experiment_id,
        campaign_id=args.campaign,
        seed=args.seed,
        collection_lock_sha256=collection_lock_sha256,
        expected_step_ids=_expected_step_ids(concretized_plan_path),
    )
    bridge = build_execution_semantic_bridge(
        plan,
        concretized_plan_path=concretized_plan_path,
        runtime_contract_path=runtime_contract_path,
    )
    catalog_path = (
        PROJECT_ROOT / "release" / "plans" / f"{args.campaign}.binding-catalog.json"
    )
    catalog = BindingCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))
    if not catalog.validate_hash():
        raise ValueError("binding catalog content hash mismatch")
    templates_document = json.loads(
        (PROJECT_ROOT / "data" / "concretization" / "action_templates.json").read_text(
            encoding="utf-8"
        )
    )
    templates = [
        ActionTemplate.model_validate(template)
        for template in templates_document["templates"]
    ]
    receipt, observation = run_revision_bound_execution(
        plan,
        bridge,
        output_dir=args.output_dir.resolve(),
        producer_revision=revision,
        consumer="sticks-runtime-v2",
        consumer_revision=revision,
        binding_catalog_sha256=catalog.content_sha256,
        action_catalog_sha256=action_catalog_hash(templates),
        admission_oracle_revision=_oracle_revision(lock.source_sha256),
        execute=_execute_runtime,
    )
    print(f"consumer_receipt_sha256={receipt.content_sha256}")
    print(f"independent_observation_sha256={observation.content_sha256}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--collection-dir", type=Path, required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
