#!/usr/bin/env python3
"""Summarise one frozen P17 paired campaign collection into a publishable evidence record.

Campaign-parametric: the real-controlled steps are derived from the receipt (the steps with no
simulated cells), so this builds the public record for any paired campaign. It writes only
publishable aggregates -- per step and arm counts, model stop reasons, budget and the observer and
oracle revisions -- copying no raw command, home path, address or hostname; a truncated generation
is reported and fails the build, because it would otherwise be mistaken for a model that chose not
to act. The C0026 record keeps its own dedicated builder; this serves additional campaigns.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_EXPERIMENTS = PROJECT_ROOT.parents[2] / "_private" / "experiments"
ADMITTED_ARM = "admitted"
PRIOR_WORK_ARM = "prior_work_style"
NATURAL_STOP_REASON = "stop"


def real_controlled_step_ids(receipt: dict) -> list[str]:
    """Step ids with no simulated cells in either arm, in occurrence order."""
    admitted = receipt["arms"][ADMITTED_ARM]
    observed = [
        step_id for step_id, summary in admitted.items() if summary["simulated"] == 0
    ]
    return sorted(observed, key=lambda step_id: admitted[step_id]["occurrence"])


def _arm_step_counts(receipt: dict, arm: str) -> dict[str, dict]:
    return {
        step_id: {
            "technique_id": summary["technique_id"],
            "target_observed": summary["target_observed"],
            "failed": summary["failed"],
            "simulated": summary["simulated"],
            "attempts_total": summary["attempts_total"],
            "failure_reasons": summary["failure_reasons"],
        }
        for step_id, summary in sorted(
            receipt["arms"][arm].items(), key=lambda item: item[1]["occurrence"]
        )
    }


def _observed_step_count(step_counts: dict[str, dict], step_ids: list[str], cells_per_arm: int) -> int:
    return sum(1 for step_id in step_ids if step_counts[step_id]["target_observed"] == cells_per_arm)


def _fully_failed_techniques(
    step_counts: dict[str, dict], step_ids: list[str], cells_per_arm: int
) -> list[str]:
    return [
        step_counts[step_id]["technique_id"]
        for step_id in step_ids
        if step_counts[step_id]["failed"] == cells_per_arm
    ]


def _generation_stop_reasons(private_root: Path) -> Counter:
    reasons: Counter = Counter()
    for proposal_path in sorted(private_root.glob(f"cells/{PRIOR_WORK_ARM}_*/s*/attempt_*/proposal.json")):
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        reasons[str(proposal["done_reason"])] += 1
    return reasons


def build_payload(private_root: Path) -> dict:
    receipt_bytes = (private_root / "receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    lock = json.loads((private_root / "collection-lock.json").read_bytes())
    config = lock["config"]
    cells_per_arm = len(config["seeds"]) * config["repetitions"]
    step_ids = real_controlled_step_ids(receipt)

    admitted = _arm_step_counts(receipt, ADMITTED_ARM)
    prior_work = _arm_step_counts(receipt, PRIOR_WORK_ARM)
    stop_reasons = _generation_stop_reasons(private_root)
    truncated = sum(count for reason, count in stop_reasons.items() if reason != NATURAL_STOP_REASON)
    prior_work_failed = _fully_failed_techniques(prior_work, step_ids, cells_per_arm)

    return {
        "question": (
            "On this campaign, does a deterministic admitted arm realize more step effects than a "
            "prior-work-style executed proposer, under one lock and an independent observer?"
        ),
        "campaign_id": receipt["campaign_id"],
        "collection_lock_sha256": receipt["collection_lock_sha256"],
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "model": config["model"],
        "ollama_model_digest": lock["ollama_model_digest"],
        "thinking_mode": lock["thinking_mode"],
        "temperature": config["temperature"],
        "top_p": config["top_p"],
        "max_output_tokens": config["max_output_tokens"],
        "retry_budget": config["retry_limit"],
        "seeds": config["seeds"],
        "repetitions": config["repetitions"],
        "cells_total": receipt["cells"],
        "cells_per_arm": cells_per_arm,
        "real_controlled_steps": len(step_ids),
        "admission_oracle_revision": lock["admission_oracle_revision"],
        "observer_revision": lock["observer_revision"],
        "arms": {ADMITTED_ARM: admitted, PRIOR_WORK_ARM: prior_work},
        "admitted_observed_steps": _observed_step_count(admitted, step_ids, cells_per_arm),
        "prior_work_observed_steps": _observed_step_count(prior_work, step_ids, cells_per_arm),
        "prior_work_fully_failed_techniques": prior_work_failed,
        "prior_work_generation_stop_reasons": dict(sorted(stop_reasons.items())),
        "prior_work_generations_total": sum(stop_reasons.values()),
        "prior_work_generations_truncated": truncated,
        "boundary": (
            "One campaign; outcomes identical across seeds and repetitions, so confidence intervals "
            "are degenerate. The prior-work arm receives only a report and generic feedback that "
            "does not reveal the effect contract, and is not a reproduction of any prior end-to-end "
            "system. P17 stays blocked."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(args.private_root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[campaign-comparison] wrote {args.output}")
    print(
        f"[campaign-comparison] {payload['campaign_id']}: admitted "
        f"{payload['admitted_observed_steps']}/{payload['real_controlled_steps']}, prior-work "
        f"{payload['prior_work_observed_steps']}/{payload['real_controlled_steps']} observed"
    )
    if payload["prior_work_generations_truncated"]:
        print("[campaign-comparison][FAIL] a truncated generation would masquerade as a choice")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
