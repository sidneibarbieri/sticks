#!/usr/bin/env python3
"""Summarise the frozen P17 paired comparison into a publishable evidence record.

The frozen private collection runs two arms over the C0026 steps under one lock: the deterministic
STICKS admitted arm and a prior-work-style executed proposer (a frozen local model that reads a
report and emits a command). This step reads that frozen receipt and the per-attempt generation
records and writes only publishable aggregates — per step and arm counts, the model stop reasons,
the budget and the observer and oracle revisions. It copies no raw command, home path, address or
hostname; every generation is checked for truncation, because a truncated reply would otherwise be
mistaken for a model that chose not to act.

The informative quantity is the contrast between arms under an independent observer, on one
campaign (only C0026 has an executable admitted plan). It is not a comparative operational claim
over prior work and not a reproduction of any prior end-to-end system.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The private frozen evidence lives under the repository root (artifact -> sticks -> research ->
# repo root), not inside the artifact tree, so it never enters the published surface.
DEFAULT_PRIVATE_ROOT = (
    PROJECT_ROOT.parents[2] / "_private" / "experiments" / "STICKS_P17_PAIRED_20261103"
)
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "prior_work_comparison" / "c0026_paired.json"
CAMPAIGN_ID = "0.c0026"
PRIOR_WORK_ARM = "prior_work_style"
ADMITTED_ARM = "admitted"
REAL_CONTROLLED_STEPS = ("s2", "s3", "s4", "s5", "s6")
NATURAL_STOP_REASON = "stop"


def _arm_step_counts(receipt: dict, arm: str) -> dict[str, dict]:
    """Per-step observed/failed/simulated counts for one arm, publishable as-is."""
    return {
        step_id: {
            "technique_id": summary["technique_id"],
            "target_observed": summary["target_observed"],
            "failed": summary["failed"],
            "simulated": summary["simulated"],
            "attempts_total": summary["attempts_total"],
            "failure_reasons": summary["failure_reasons"],
        }
        for step_id, summary in sorted(receipt["arms"][arm].items())
    }


def _observed_step_count(step_counts: dict[str, dict], cells_per_arm: int) -> int:
    """How many of the real-controlled steps were observed in every cell."""
    return sum(
        1
        for step_id in REAL_CONTROLLED_STEPS
        if step_counts[step_id]["target_observed"] == cells_per_arm
    )


def _failed_technique(step_counts: dict[str, dict], cells_per_arm: int) -> str | None:
    """The one real-controlled technique the arm failed in every cell, if any."""
    failed = [
        step_counts[step_id]["technique_id"]
        for step_id in REAL_CONTROLLED_STEPS
        if step_counts[step_id]["failed"] == cells_per_arm
    ]
    if len(failed) > 1:
        raise ValueError("more than one fully-failed technique; prose would be ambiguous")
    return failed[0] if failed else None


def _generation_stop_reasons(private_root: Path) -> Counter:
    """Count the model stop reason of every prior-work generation attempt retained on disk."""
    reasons: Counter = Counter()
    pattern = f"cells/{PRIOR_WORK_ARM}_*/s*/attempt_*/proposal.json"
    for proposal_path in sorted(private_root.glob(pattern)):
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        reasons[str(proposal["done_reason"])] += 1
    return reasons


def build_payload(private_root: Path) -> dict:
    """Build the publishable record from the frozen private receipt and generation records."""
    receipt_bytes = (private_root / "receipt.json").read_bytes()
    receipt = json.loads(receipt_bytes)
    lock = json.loads((private_root / "collection-lock.json").read_bytes())
    config = lock["config"]
    cells_per_arm = len(config["seeds"]) * config["repetitions"]

    admitted = _arm_step_counts(receipt, ADMITTED_ARM)
    prior_work = _arm_step_counts(receipt, PRIOR_WORK_ARM)
    stop_reasons = _generation_stop_reasons(private_root)
    truncated = sum(count for reason, count in stop_reasons.items() if reason != NATURAL_STOP_REASON)

    return {
        "question": (
            "On one campaign, does a deterministic admitted arm realize more step effects than a "
            "prior-work-style executed proposer, under one lock and an independent observer?"
        ),
        "campaign_id": CAMPAIGN_ID,
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
        "real_controlled_steps": len(REAL_CONTROLLED_STEPS),
        "admission_oracle_revision": lock["admission_oracle_revision"],
        "observer_revision": lock["observer_revision"],
        "arms": {ADMITTED_ARM: admitted, PRIOR_WORK_ARM: prior_work},
        "admitted_observed_steps": _observed_step_count(admitted, cells_per_arm),
        "prior_work_observed_steps": _observed_step_count(prior_work, cells_per_arm),
        "prior_work_failed_technique": _failed_technique(prior_work, cells_per_arm),
        "prior_work_failed_cells": prior_work["s6"]["failed"],
        "prior_work_generation_stop_reasons": dict(sorted(stop_reasons.items())),
        "prior_work_generations_total": sum(stop_reasons.values()),
        "prior_work_generations_truncated": truncated,
        "boundary": (
            "One campaign (only C0026 has an executable admitted plan); outcomes identical across "
            "seeds and repetitions, so confidence intervals are degenerate. The prior-work arm "
            "receives only a report and generic feedback that does not reveal the effect contract, "
            "and is not a reproduction of any prior end-to-end system. P17 stays blocked."
        ),
    }


def main() -> int:
    payload = build_payload(DEFAULT_PRIVATE_ROOT)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[prior-work-comparison] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        f"[prior-work-comparison] admitted observed {payload['admitted_observed_steps']}/"
        f"{payload['real_controlled_steps']} steps, prior-work "
        f"{payload['prior_work_observed_steps']}/{payload['real_controlled_steps']} "
        f"(failed {payload['prior_work_failed_technique']} in {payload['prior_work_failed_cells']} "
        f"of {payload['cells_per_arm']} cells)"
    )
    if payload["prior_work_generations_truncated"]:
        print("[prior-work-comparison][FAIL] a truncated generation would masquerade as a choice")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
