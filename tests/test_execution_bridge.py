from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.controlled_comparison import (  # noqa: E402
    AdmittedCampaignPlan,
    ArmId,
    NeutralProposalRecord,
)
from evaluation.execution_bridge import build_execution_semantic_bridge  # noqa: E402

SHA_A = "a" * 64
SHA_B = "b" * 64
LOCK_SHA = "c" * 64


def admitted_plan(*, bindings: dict[str, str] | None = None) -> AdmittedCampaignPlan:
    proposal = NeutralProposalRecord(
        proposal_id="proposal-1",
        experiment_id="comparison-1",
        campaign_id="C0026",
        step_id="s1",
        arm_id=ArmId.sticks_admitted,
        seed=1,
        technique_id="T0001",
        execution_domain="linux",
        template_id="template-1",
        bindings=bindings or {"target": "target.primary"},
        proposal_budget_sha256=SHA_A,
        raw_output_sha256=SHA_B,
    )
    proposal.finalize_hash()
    plan = AdmittedCampaignPlan(
        experiment_id="comparison-1",
        campaign_id="C0026",
        seed=1,
        collection_lock_sha256=LOCK_SHA,
        proposals=[proposal],
    )
    plan.finalize_hash()
    return plan


def write_semantics(
    root: Path, *, runtime_technique: str = "T0001"
) -> tuple[Path, Path]:
    concretized_path = root / "concretized.json"
    runtime_path = root / "runtime.json"
    concretized_path.write_text(
        json.dumps(
            {
                "campaign_id": "C0026",
                "steps": [
                    {
                        "sequence": 1,
                        "technique_id": "T0001",
                        "template_id": "template-1",
                        "bindings": {"target": "target.primary"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    runtime_path.write_text(
        json.dumps(
            {
                "campaign_id": "0.c0026",
                "occurrences": [
                    {
                        "occurrence": 1,
                        "technique_id": runtime_technique,
                        "executor_id": "executors.fixture.execute",
                        "executor_sha256": SHA_A,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return concretized_path, runtime_path


def test_bridge_binds_exact_admitted_semantics_to_runtime(tmp_path: Path) -> None:
    concretized, runtime = write_semantics(tmp_path)
    bridge = build_execution_semantic_bridge(
        admitted_plan(),
        concretized_plan_path=concretized,
        runtime_contract_path=runtime,
    )
    assert bridge.validate_hash()
    assert bridge.runtime_campaign_id == "0.c0026"
    assert bridge.steps[0].template_id == "template-1"
    assert bridge.steps[0].executor_id == "executors.fixture.execute"


def test_bridge_rejects_another_campaign_with_identical_steps(tmp_path: Path) -> None:
    concretized, runtime = write_semantics(tmp_path)
    document = json.loads(runtime.read_text())
    document["campaign_id"] = "0.c0045"
    runtime.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="runtime contract campaign differs"):
        build_execution_semantic_bridge(
            admitted_plan(),
            concretized_plan_path=concretized,
            runtime_contract_path=runtime,
        )


def test_bridge_accepts_reviewed_shadowray_runtime_identity(tmp_path: Path) -> None:
    concretized, runtime = write_semantics(tmp_path)
    document = json.loads(concretized.read_text())
    document["campaign_id"] = "C0045"
    concretized.write_text(json.dumps(document))
    document = json.loads(runtime.read_text())
    document["campaign_id"] = "0.shadowray"
    runtime.write_text(json.dumps(document))
    original = admitted_plan()
    proposal = original.proposals[0].model_copy(update={"campaign_id": "C0045"})
    proposal.finalize_hash()
    selected = original.model_copy(
        update={"campaign_id": "C0045", "proposals": [proposal]}
    )
    selected.finalize_hash()
    bridge = build_execution_semantic_bridge(
        selected, concretized_plan_path=concretized, runtime_contract_path=runtime
    )
    assert bridge.runtime_campaign_id == "0.shadowray"


def test_bridge_rejects_binding_or_executor_semantic_drift(tmp_path: Path) -> None:
    concretized, runtime = write_semantics(tmp_path)
    with pytest.raises(ValueError, match="differs from frozen semantics"):
        build_execution_semantic_bridge(
            admitted_plan(bindings={"target": "another.target"}),
            concretized_plan_path=concretized,
            runtime_contract_path=runtime,
        )

    concretized, runtime = write_semantics(tmp_path, runtime_technique="T9999")
    with pytest.raises(ValueError, match="runtime technique differs"):
        build_execution_semantic_bridge(
            admitted_plan(),
            concretized_plan_path=concretized,
            runtime_contract_path=runtime,
        )


def test_bridge_accepts_current_c0026_frozen_semantics() -> None:
    concretized_path = PROJECT_ROOT / "release/plans/C0026.concretized-plan.json"
    runtime_path = PROJECT_ROOT / "data/runtime_contracts/c0026.json"
    concretized = json.loads(concretized_path.read_text(encoding="utf-8"))
    proposals = []
    for step in sorted(concretized["steps"], key=lambda item: item["sequence"]):
        proposal = NeutralProposalRecord(
            proposal_id=f"fixture-s{step['sequence']}",
            experiment_id="c0026-bridge-regression",
            campaign_id="C0026",
            step_id=f"s{step['sequence']}",
            arm_id=ArmId.sticks_admitted,
            seed=1,
            technique_id=step["technique_id"],
            execution_domain="linux",
            template_id=step["template_id"],
            bindings=step["bindings"],
            proposal_budget_sha256=SHA_A,
            raw_output_sha256=SHA_B,
        )
        proposal.finalize_hash()
        proposals.append(proposal)
    plan = AdmittedCampaignPlan(
        experiment_id="c0026-bridge-regression",
        campaign_id="C0026",
        seed=1,
        collection_lock_sha256=LOCK_SHA,
        proposals=proposals,
    )
    plan.finalize_hash()
    bridge = build_execution_semantic_bridge(
        plan,
        concretized_plan_path=concretized_path,
        runtime_contract_path=runtime_path,
    )
    assert bridge.validate_hash()
    assert len(bridge.steps) == 6
    assert [step.occurrence for step in bridge.steps] == list(range(1, 7))


def test_bridge_maps_current_c0010_runtime_order_to_causal_plan() -> None:
    concretized_path = PROJECT_ROOT / "release/plans/C0010.concretized-plan.json"
    runtime_path = PROJECT_ROOT / "data/runtime_contracts/c0010.json"
    concretized = json.loads(concretized_path.read_text(encoding="utf-8"))
    proposals = []
    for step in sorted(concretized["steps"], key=lambda item: item["sequence"]):
        proposal = NeutralProposalRecord(
            proposal_id=f"c0010-s{step['sequence']}",
            experiment_id="c0010-bridge-regression",
            campaign_id="C0010",
            step_id=f"s{step['sequence']}",
            arm_id=ArmId.sticks_admitted,
            seed=1,
            technique_id=step["technique_id"],
            execution_domain="mixed",
            template_id=step["template_id"],
            bindings=step["bindings"],
            proposal_budget_sha256=SHA_A,
            raw_output_sha256=SHA_B,
        )
        proposal.finalize_hash()
        proposals.append(proposal)
    plan = AdmittedCampaignPlan(
        experiment_id="c0010-bridge-regression",
        campaign_id="C0010",
        seed=1,
        collection_lock_sha256=LOCK_SHA,
        proposals=proposals,
    )
    plan.finalize_hash()

    bridge = build_execution_semantic_bridge(
        plan, concretized_plan_path=concretized_path, runtime_contract_path=runtime_path
    )

    assert [step.occurrence for step in bridge.steps] == list(range(1, 10))
    assert [step.step_id for step in bridge.steps] == [
        "s2",
        "s5",
        "s7",
        "s8",
        "s3",
        "s1",
        "s6",
        "s4",
        "s9",
    ]
