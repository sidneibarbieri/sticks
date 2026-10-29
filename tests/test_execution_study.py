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
    EffectClass,
    NeutralProposalRecord,
)
from evaluation.execution_bridge import build_execution_semantic_bridge  # noqa: E402
from evaluation.execution_study import (  # noqa: E402
    build_execution_handoff,
    qualify_runtime_execution,
    run_revision_bound_execution,
)
from runners.capability_facts import FactScope, ObservationReference  # noqa: E402
from runners.capability_observations import PredicateObservation  # noqa: E402
from runners.runtime_campaign_report import (  # noqa: E402
    RuntimeCampaignReport,
    RuntimeCampaignStep,
)
from runners.runtime_invocation import (  # noqa: E402
    RuntimeInvocationOutcome,
    RuntimeOccurrenceOutcome,
)
from runners.runtime_step_contracts import RuntimeStepContract  # noqa: E402

SHA_A = "a" * 64
SHA_B = "b" * 64
REVISION_A = "1" * 40
REVISION_B = "2" * 40


def execution_inputs(tmp_path: Path):
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
        bindings={"target": "target.primary"},
        proposal_budget_sha256=SHA_A,
        raw_output_sha256=SHA_B,
    )
    proposal.finalize_hash()
    plan = AdmittedCampaignPlan(
        experiment_id="comparison-1",
        campaign_id="C0026",
        seed=1,
        collection_lock_sha256="c" * 64,
        proposals=[proposal],
    )
    plan.finalize_hash()
    concretized = tmp_path / "concretized.json"
    runtime = tmp_path / "runtime.json"
    concretized.write_text(
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
    runtime.write_text(
        json.dumps(
            {
                "campaign_id": "0.c0026",
                "occurrences": [
                    {
                        "occurrence": 1,
                        "technique_id": "T0001",
                        "executor_id": "executors.fixture.execute",
                        "executor_sha256": SHA_A,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bridge = build_execution_semantic_bridge(
        plan,
        concretized_plan_path=concretized,
        runtime_contract_path=runtime,
    )
    handoff = build_execution_handoff(
        plan,
        bridge,
        producer_revision=REVISION_A,
        consumer="sticks-runtime-v2",
        consumer_revision=REVISION_B,
        binding_catalog_sha256=SHA_A,
        action_catalog_sha256=SHA_B,
    )
    return plan, bridge, handoff


def observed_report(*, executor_sha256: str = SHA_A, locus: str = "target"):
    scope = FactScope(
        run_id="run-1",
        environment_id="lab-1",
        epoch="epoch-1",
        locus=locus,
        host_id="target-1",
        principal="ubuntu",
    )
    contract = RuntimeStepContract(
        campaign_id="0.c0026",
        occurrence=1,
        technique_id="T0001",
        executor_id="executors.fixture.execute",
        executor_sha256=executor_sha256,
        mode="real_controlled",
        scope=scope,
        requirements=(),
        observers=(),
    )
    observation = PredicateObservation(
        scope=scope,
        predicate_id="collection-bytes",
        passed=True,
        established_facts=("effect:observed",),
        details={"fixture": True},
    )
    reference = ObservationReference(
        authority_id="c0026-collection",
        predicate_id=observation.predicate_id,
        record_path="observations/fixture.json",
        record_sha256=SHA_B,
    )
    outcome = RuntimeOccurrenceOutcome(
        invocation=RuntimeInvocationOutcome(
            executor_id=contract.executor_id,
            executor_completed=True,
            stdout="",
            stderr="",
            artifacts=(),
            declared_products=(),
        ),
        observations=(observation,),
        observation_references=(reference,),
        authorizing_facts=(),
    )
    step = RuntimeCampaignStep(contract=contract, status="observed", outcome=outcome)
    return RuntimeCampaignReport(
        schema_version="runtime-campaign/v2",
        campaign_id="0.c0026",
        run_id="run-1",
        infrastructure_provider="fixture",
        bootstrap=None,
        steps=(step,),
        runtime_facts=(),
        journal_references=(),
    )


def test_execution_study_binds_report_and_independent_observation(tmp_path: Path) -> None:
    _plan, bridge, handoff = execution_inputs(tmp_path)
    receipt, observation = qualify_runtime_execution(
        handoff,
        bridge,
        observed_report(),
        raw_execution=b'{"summary":"fixture"}',
        admission_oracle_revision=SHA_A,
    )
    assert receipt.validate_hash()
    assert observation.validate_hash()
    assert receipt.handoff_sha256 == handoff.content_sha256
    assert observation.effects[0].effect_class == EffectClass.target_observed
    assert observation.effects[0].predicate_id == "collection-bytes"


def test_execution_study_rejects_runtime_binding_drift(tmp_path: Path) -> None:
    _plan, bridge, handoff = execution_inputs(tmp_path)
    with pytest.raises(ValueError, match="differs from semantic bridge"):
        qualify_runtime_execution(
            handoff,
            bridge,
            observed_report(executor_sha256="c" * 64),
            raw_execution=b"{}",
            admission_oracle_revision=SHA_A,
        )


def test_execution_study_rejects_nonindependent_observer(tmp_path: Path) -> None:
    _plan, bridge, handoff = execution_inputs(tmp_path)
    _, independent = qualify_runtime_execution(
        handoff,
        bridge,
        observed_report(),
        raw_execution=b"{}",
        admission_oracle_revision=SHA_A,
    )
    with pytest.raises(ValueError, match="independent"):
        qualify_runtime_execution(
            handoff,
            bridge,
            observed_report(),
            raw_execution=b"{}",
            admission_oracle_revision=independent.observer_revision,
        )


def test_execution_study_rejects_unsupported_observation_locus(tmp_path: Path) -> None:
    _plan, bridge, handoff = execution_inputs(tmp_path)
    with pytest.raises(ValueError, match="mixed observation loci"):
        qualify_runtime_execution(
            handoff,
            bridge,
            observed_report(locus="attacker"),
            raw_execution=b"{}",
            admission_oracle_revision=SHA_A,
        )


def test_revision_bound_orchestrator_persists_five_documents(tmp_path: Path) -> None:
    plan, bridge, _handoff = execution_inputs(tmp_path)
    report = observed_report()

    def execute(campaign_id: str, runtime_dir: Path):
        assert campaign_id == "0.c0026"
        assert runtime_dir.name == "runtime"
        return report, report.model_dump_json(indent=2).encode("utf-8")

    output_dir = tmp_path / "study"
    receipt, observation = run_revision_bound_execution(
        plan,
        bridge,
        output_dir=output_dir,
        producer_revision=REVISION_A,
        consumer="sticks-runtime-v2",
        consumer_revision=REVISION_B,
        binding_catalog_sha256=SHA_A,
        action_catalog_sha256=SHA_B,
        admission_oracle_revision=SHA_A,
        execute=execute,
    )
    assert receipt.validate_hash()
    assert observation.validate_hash()
    assert {path.name for path in output_dir.iterdir()} == {
        "admitted-plan.json",
        "execution-semantic-bridge.json",
        "execution-handoff.json",
        "consumer-receipt.json",
        "independent-observation.json",
    }


def test_revision_bound_orchestrator_rejects_unretained_report(tmp_path: Path) -> None:
    plan, bridge, _handoff = execution_inputs(tmp_path)
    report = observed_report()
    different = report.model_copy(update={"infrastructure_provider": "other"})

    with pytest.raises(ValueError, match="differs from retained execution bytes"):
        run_revision_bound_execution(
            plan,
            bridge,
            output_dir=tmp_path / "study",
            producer_revision=REVISION_A,
            consumer="sticks-runtime-v2",
            consumer_revision=REVISION_B,
            binding_catalog_sha256=SHA_A,
            action_catalog_sha256=SHA_B,
            admission_oracle_revision=SHA_A,
            execute=lambda _campaign, _output: (
                report,
                different.model_dump_json(indent=2).encode("utf-8"),
            ),
        )
    assert not (tmp_path / "study" / "consumer-receipt.json").exists()
    assert not (tmp_path / "study" / "independent-observation.json").exists()
