"""Bind an admitted comparison plan to reviewed fixed-runtime semantics."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from evaluation.controlled_comparison import (
    AdmittedCampaignPlan,
    ExecutionBridgeStep,
    ExecutionSemanticBridge,
    canonical_sha256,
)
from evaluation.runtime_identity import expected_runtime_campaign


def _read_object(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"expected a JSON object: {path}")
    return document


def _ordered_rows(
    document: dict[str, Any], field: str, order_field: str
) -> list[dict[str, Any]]:
    rows = document.get(field)
    if (
        not isinstance(rows, list)
        or not rows
        or not all(isinstance(row, dict) for row in rows)
    ):
        raise ValueError(f"{field} must be a nonempty object list")
    ordered = sorted(rows, key=lambda row: row.get(order_field, 0))
    expected = list(range(1, len(ordered) + 1))
    if [row.get(order_field) for row in ordered] != expected:
        raise ValueError(f"{field} must have contiguous {order_field} values")
    return ordered


def _runtime_plan_sequences(
    runtime_rows: list[dict[str, Any]], concretized_steps: list[dict[str, Any]]
) -> list[int]:
    """Resolve the plan step consumed by each runtime occurrence.

    A plan explicitly aligned to the runtime is already positional. Otherwise,
    the contract must map each runtime occurrence back to the causal plan.
    """
    step_count = len(concretized_steps)
    if [row.get("technique_id") for row in runtime_rows] == [
        step.get("technique_id") for step in concretized_steps
    ]:
        return list(range(1, step_count + 1))
    declared = [row.get("plan_sequence") for row in runtime_rows]
    if all(value is None for value in declared):
        return list(range(1, step_count + 1))
    if any(not isinstance(value, int) for value in declared):
        raise ValueError("runtime plan_sequence must be an integer on every occurrence")
    sequences = [int(value) for value in declared]
    if sorted(sequences) != list(range(1, step_count + 1)):
        raise ValueError(
            "runtime plan_sequence must cover every causal step exactly once"
        )
    return sequences


def build_execution_semantic_bridge(
    plan: AdmittedCampaignPlan,
    *,
    concretized_plan_path: Path,
    runtime_contract_path: Path,
) -> ExecutionSemanticBridge:
    """Require exact proposal equality before selecting fixed runtime executors.

    This proves equality to reviewed inputs and executor bindings. It does not
    prove that an executor produces the intended effect; independent observers
    remain mandatory after execution.
    """
    if not plan.validate_hash():
        raise ValueError("admitted plan content hash mismatch")
    concretized = _read_object(concretized_plan_path)
    runtime = _read_object(runtime_contract_path)
    if concretized.get("campaign_id") != plan.campaign_id:
        raise ValueError("concretized plan campaign differs from admitted plan")
    runtime_campaign_id = runtime.get("campaign_id")
    if not isinstance(runtime_campaign_id, str) or not runtime_campaign_id:
        raise ValueError("runtime contract lacks campaign_id")
    if runtime_campaign_id != expected_runtime_campaign(plan.campaign_id):
        raise ValueError("runtime contract campaign differs from admitted plan")
    concretized_steps = _ordered_rows(concretized, "steps", "sequence")
    runtime_rows = _ordered_rows(runtime, "occurrences", "occurrence")
    if len(plan.proposals) != len(concretized_steps) or len(runtime_rows) != len(
        concretized_steps
    ):
        raise ValueError("admitted, concretized, and runtime step counts differ")

    proposals_by_step_id = {proposal.step_id: proposal for proposal in plan.proposals}
    if len(proposals_by_step_id) != len(plan.proposals):
        raise ValueError("admitted plan contains duplicate step identifiers")

    bridge_steps = []
    for runtime_row, plan_sequence in zip(
        runtime_rows,
        _runtime_plan_sequences(runtime_rows, concretized_steps),
        strict=True,
    ):
        expected = concretized_steps[plan_sequence - 1]
        step_id = f"s{plan_sequence}"
        proposal = proposals_by_step_id.get(step_id)
        if proposal is None:
            raise ValueError(f"admitted plan lacks proposal for {step_id}")
        expected_identity = (
            step_id,
            expected.get("technique_id"),
            expected.get("template_id"),
            expected.get("bindings"),
        )
        proposal_identity = (
            proposal.step_id,
            proposal.technique_id,
            proposal.template_id,
            proposal.bindings,
        )
        if proposal_identity != expected_identity:
            raise ValueError(
                f"admitted proposal differs from frozen semantics at {step_id}"
            )
        if runtime_row.get("technique_id") != proposal.technique_id:
            raise ValueError(
                f"runtime technique differs from admitted proposal at {step_id}"
            )
        executor_id = runtime_row.get("executor_id")
        executor_sha256 = runtime_row.get("executor_sha256")
        if not isinstance(executor_id, str) or not executor_id:
            raise ValueError(f"runtime executor identity missing at {step_id}")
        if not isinstance(executor_sha256, str):
            raise ValueError(f"runtime executor digest missing at {step_id}")
        bridge_steps.append(
            ExecutionBridgeStep(
                step_id=proposal.step_id,
                occurrence=runtime_row["occurrence"],
                proposal_sha256=proposal.content_sha256,
                technique_id=proposal.technique_id,
                template_id=proposal.template_id,
                bindings_sha256=canonical_sha256(proposal.bindings),
                executor_id=executor_id,
                executor_sha256=executor_sha256,
            )
        )

    bridge = ExecutionSemanticBridge(
        experiment_id=plan.experiment_id,
        campaign_id=plan.campaign_id,
        runtime_campaign_id=runtime_campaign_id,
        seed=plan.seed,
        admitted_plan_sha256=plan.content_sha256,
        concretized_plan_sha256=hashlib.sha256(
            concretized_plan_path.read_bytes()
        ).hexdigest(),
        runtime_contract_sha256=hashlib.sha256(
            runtime_contract_path.read_bytes()
        ).hexdigest(),
        steps=bridge_steps,
    )
    bridge.finalize_hash()
    return bridge
