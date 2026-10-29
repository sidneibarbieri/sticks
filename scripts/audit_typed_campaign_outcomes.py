#!/usr/bin/env python3
"""Audit scoped VM-run outcomes from sealed receipts and typed summaries."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from runners.capability_observations import verify_observation_reference
from runners.runtime_campaign_report import (
    RuntimeCampaignReport,
    parse_retained_campaign_report,
)
from scripts.finalize_isolated_lab_run import FINAL_RECEIPT, build_receipt


class CampaignOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: str
    run_id: str
    source_tree_sha256: str
    receipt_sha256: str
    observed_target: int = Field(ge=0)
    observed_controller: int = Field(ge=0)
    simulated: int = Field(ge=0)
    failed: int = Field(ge=0)
    total: int = Field(ge=0)

    @model_validator(mode="after")
    def check_population(self) -> CampaignOutcome:
        counted = (
            self.observed_target
            + self.observed_controller
            + self.simulated
            + self.failed
        )
        if counted != self.total:
            raise ValueError("Outcome classes do not sum to the run population")
        return self


def _read_json(file_path: Path) -> dict[str, Any]:
    return json.loads(file_path.read_text(encoding="utf-8"))


def verify_retained_observations(
    report: RuntimeCampaignReport, observation_root: Path
) -> None:
    """Bind each counted observed effect to its retained acquisition bytes."""
    for step in report.steps:
        if step.status != "observed":
            continue
        if step.outcome is None:
            raise ValueError("Observed step lacks an outcome")
        for observation, reference in zip(
            step.outcome.observations,
            step.outcome.observation_references,
            strict=True,
        ):
            if observation.scope != step.contract.scope:
                raise ValueError("Observation scope differs from the producing step")
            retained = verify_observation_reference(
                reference,
                run_root=observation_root,
                expected_scope=step.contract.scope,
                expected_predicate=observation.predicate_id,
            )
            if retained != observation or not retained.passed:
                raise ValueError("Retained observation differs from the typed summary")


def _observation_locus(step: dict[str, Any]) -> str:
    observations = step["outcome"]["observations"]
    if len(observations) != 1 or observations[0]["passed"] is not True:
        raise ValueError("Observed step needs one passed observation")
    locus = observations[0]["scope"]["locus"]
    if locus not in {"target", "controller"}:
        raise ValueError("Observed step has an unsupported locus")
    return locus


def summarize_run(
    receipt: dict[str, Any], summary: dict[str, Any], receipt_sha256: str
) -> CampaignOutcome:
    if receipt["cycle_passed"] is not True:
        raise ValueError("Run does not have a successful sealed cycle")
    if summary["schema_version"] != "runtime-campaign/v2":
        raise ValueError("Unsupported typed summary schema")
    run_id = receipt.get("run_id", receipt.get("runner_run_id"))
    if summary["campaign_id"] != receipt["campaign_id"] or summary["run_id"] != run_id:
        raise ValueError("Receipt and typed summary identify different runs")

    counts = {"target": 0, "controller": 0, "simulated": 0, "failed": 0}
    for step in summary["steps"]:
        status = step["status"]
        if status == "observed":
            counts[_observation_locus(step)] += 1
        elif status in {"simulated", "failed"}:
            if step["outcome"]["observations"]:
                raise ValueError("Non-observed step carries an observation")
            counts[status] += 1
        else:
            raise ValueError(f"Unsupported typed step status: {status}")

    observed = counts["target"] + counts["controller"]
    if (
        len(summary["steps"]) != summary["total_techniques"]
        or observed != summary["effects_observed"]
        or counts["simulated"] != summary["simulated"]
        or counts["failed"] != summary["failed"]
    ):
        raise ValueError("Typed summary totals disagree with the occurrences")
    for receipt_field, expected in (
        ("controller_effects_observed", counts["controller"]),
        ("guest_effects_observed", counts["target"]),
        ("runner_effects_observed", observed),
        ("runner_simulated", counts["simulated"]),
        ("simulated", counts["simulated"]),
        ("runner_total_techniques", len(summary["steps"])),
    ):
        if receipt_field in receipt and receipt[receipt_field] != expected:
            raise ValueError(f"Receipt disagrees with typed summary: {receipt_field}")

    return CampaignOutcome(
        campaign_id=receipt["campaign_id"],
        run_id=run_id,
        source_tree_sha256=receipt["source_tree_sha256"],
        receipt_sha256=receipt_sha256,
        observed_target=counts["target"],
        observed_controller=counts["controller"],
        simulated=counts["simulated"],
        failed=counts["failed"],
        total=len(summary["steps"]),
    )


def audit_run(run_root: Path) -> CampaignOutcome:
    run_root = run_root.resolve(strict=True)
    receipt_path = run_root / FINAL_RECEIPT
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    recorded_vm_states = receipt.get("vm_states")
    if not isinstance(recorded_vm_states, dict):
        raise ValueError("Final receipt lacks recorded VM teardown states")
    if receipt != build_receipt(run_root, recorded_vm_states=recorded_vm_states):
        raise ValueError("Final receipt no longer matches the run evidence")
    summary_relative = receipt.get("summary_path", receipt.get("runner_summary_path"))
    if not isinstance(summary_relative, str):
        raise ValueError("Final receipt does not name a typed summary")
    evidence_root = run_root / "evidence"
    summary_path = (evidence_root / summary_relative).resolve(strict=True)
    if not summary_path.is_relative_to(evidence_root.resolve(strict=True)):
        raise ValueError("Typed summary resolves outside the run evidence")
    summary_content = summary_path.read_text(encoding="utf-8")
    report = parse_retained_campaign_report(summary_content)
    verify_retained_observations(report, summary_path.parent)
    return summarize_run(
        receipt, json.loads(summary_content), hashlib.sha256(receipt_bytes).hexdigest()
    )


def audit_runs(run_roots: list[Path]) -> list[CampaignOutcome]:
    if not run_roots:
        raise ValueError("At least one run is required")
    outcomes = [audit_run(run_root) for run_root in run_roots]
    if len({outcome.run_id for outcome in outcomes}) != len(outcomes):
        raise ValueError("Run IDs must be distinct")
    if len({outcome.campaign_id for outcome in outcomes}) != len(outcomes):
        raise ValueError("Campaign IDs must be distinct for this comparison")
    if len({outcome.source_tree_sha256 for outcome in outcomes}) != 1:
        raise ValueError("Campaigns were not run from the same source tree")
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", action="append", type=Path, required=True)
    args = parser.parse_args()
    outcomes = audit_runs(args.run_root)
    print(
        json.dumps([item.model_dump() for item in outcomes], indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
