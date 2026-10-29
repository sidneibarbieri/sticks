from __future__ import annotations

import json
import hashlib
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from evaluation.controlled_comparison import (  # noqa: E402
    AdmittedCampaignPlan,
    ArmDefinition,
    ArmId,
    BlindOracleInput,
    ConsumerExecutionReceipt,
    ControlledComparisonManifest,
    EffectClass,
    EvidenceReference,
    EvidenceRole,
    ExecutionBridgeStep,
    ExecutionHandoff,
    ExecutionSemanticBridge,
    GeneratorBudget,
    IndependentEffectObservation,
    NeutralProposalRecord,
    RunLedger,
    RunRecord,
    RunStatus,
    StepEffectObservation,
    evaluate_blind_proposal,
    validate_proposal_record,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def budget(**updates: object) -> GeneratorBudget:
    values: dict[str, object] = {
        "model_id": "local-model:1",
        "model_artifact_sha256": SHA_A,
        "runtime_id": "runtime:1",
        "prompt_template_sha256": SHA_B,
        "temperature": 0.0,
        "top_p": 1.0,
        "max_output_tokens": 512,
        "max_proposal_calls_per_step": 1,
        "max_retries_per_step": 0,
        "timeout_seconds_per_step": 60,
    }
    values.update(updates)
    return GeneratorBudget.model_validate(values)


def manifest(*, mismatched_budget: bool = False) -> ControlledComparisonManifest:
    shared_budget = budget()
    return ControlledComparisonManifest(
        experiment_id="comparison-1",
        protocol_sha256=SHA_A,
        campaigns=["C0010"],
        seeds=[1, 2, 3, 4, 5],
        arms=[
            ArmDefinition(arm_id=ArmId.prior_work_style, proposal_budget=shared_budget),
            ArmDefinition(
                arm_id=ArmId.sticks_without_admission,
                proposal_budget=(
                    budget(max_output_tokens=513) if mismatched_budget else shared_budget
                ),
            ),
            ArmDefinition(arm_id=ArmId.sticks_admitted, proposal_budget=shared_budget),
            ArmDefinition(
                arm_id=ArmId.sticks_autosut_executed,
                consumes_arm=ArmId.sticks_admitted,
            ),
        ],
        oracle_revision=SHA_B,
        action_catalog_sha256=SHA_A,
    )


def test_collection_ready_requires_matched_budgets() -> None:
    manifest().validate_collection_ready()
    with pytest.raises(ValueError, match="identical proposal budgets"):
        manifest(mismatched_budget=True).validate_collection_ready()


def test_ledger_requires_every_planned_run() -> None:
    experiment = manifest()
    records = [
        RunRecord(
            campaign_id=campaign_id,
            arm_id=ArmId(arm_id),
            seed=seed,
            status=RunStatus.unsupported,
            unsupported_reason="synthetic fixture",
        )
        for campaign_id, arm_id, seed in sorted(experiment.planned_run_keys())
    ]
    ledger = RunLedger(experiment_id=experiment.experiment_id, records=records)
    ledger.validate_against(experiment)
    ledger.records.pop()
    with pytest.raises(ValueError, match="run accounting mismatch"):
        ledger.validate_against(experiment)


def test_failed_and_unsupported_runs_cannot_look_successful() -> None:
    with pytest.raises(ValidationError, match="requires evidence references"):
        RunRecord(
            campaign_id="C0010",
            arm_id=ArmId.sticks_admitted,
            seed=1,
            status=RunStatus.succeeded,
        )
    with pytest.raises(ValidationError, match="cannot contain failure metadata"):
        RunRecord(
            campaign_id="C0010",
            arm_id=ArmId.sticks_admitted,
            seed=1,
            status=RunStatus.succeeded,
            evidence=[EvidenceReference(path="evidence.json", sha256=SHA_A)],
            failure_code="TIMEOUT",
            failure_detail="synthetic timeout",
        )


def test_success_evidence_is_relative_and_hash_verified(tmp_path: Path) -> None:
    evidence_path = tmp_path / "run.json"
    evidence_path.write_text("{}\n", encoding="utf-8")
    digest = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    record = RunRecord(
        campaign_id="C0010",
        arm_id=ArmId.sticks_admitted,
        seed=1,
        status=RunStatus.succeeded,
        evidence=[EvidenceReference(path="run.json", sha256=digest)],
    )
    ledger = RunLedger(experiment_id="comparison-1", records=[record])
    ledger.validate_evidence(tmp_path)
    evidence_path.write_text('{"altered": true}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        ledger.validate_evidence(tmp_path)
    with pytest.raises(ValidationError, match="cannot traverse parents"):
        EvidenceReference(path="../run.json", sha256=digest)


def test_blind_oracle_input_rejects_arm_label_and_reuses_verifier() -> None:
    catalog = BindingCatalog(
        sut_id="sut-1",
        source_sha256=SHA_A,
        initial_facts=["host.reachable"],
        bindings=[],
    )
    catalog.finalize_hash()
    template = ActionTemplate(
        template_id="probe-host",
        technique_ids=["T0001"],
        execution_domain="linux",
        requires=["host.reachable"],
        produces=["host.probed"],
        evidence_predicates=["probe.exit_code == 0"],
        fidelity_ceiling="adapted",
        description="Benign host probe",
    )
    raw_input = {
        "blind_id": "blind-1",
        "campaign_id": "C0010",
        "step_id": "step-1",
        "technique_id": "T0001",
        "execution_domain": "linux",
        "template_id": "probe-host",
        "known_facts": ["host.reachable"],
        "source_record_sha256": SHA_B,
    }
    decision = evaluate_blind_proposal(
        BlindOracleInput.model_validate(raw_input),
        templates=[template],
        catalog=catalog,
        oracle_revision=SHA_A,
    )
    assert decision.accepted is True
    assert decision.issue_codes == []
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        BlindOracleInput.model_validate({**raw_input, "arm_id": "sticks_admitted"})


def test_proposal_record_blinds_arm_and_preserves_audit_assignment() -> None:
    experiment = manifest()
    proposal = NeutralProposalRecord(
        proposal_id="proposal-1",
        experiment_id=experiment.experiment_id,
        campaign_id="C0010",
        step_id="step-1",
        arm_id=ArmId.sticks_admitted,
        seed=1,
        technique_id="T0001",
        execution_domain="linux",
        template_id="probe-host",
        proposal_budget_sha256=budget().comparison_sha256(),
        raw_output_sha256=SHA_A,
    )
    proposal.finalize_hash()
    validate_proposal_record(proposal, experiment)
    oracle_input, assignment = proposal.blind("blind-1")
    assert "arm_id" not in oracle_input.model_dump()
    assert assignment.arm_id == ArmId.sticks_admitted
    proposal.proposal_budget_sha256 = SHA_B
    proposal.finalize_hash()
    with pytest.raises(ValueError, match="budget hash"):
        validate_proposal_record(proposal, experiment)


def test_execution_handoff_is_revision_bound_and_hash_validated() -> None:
    handoff = ExecutionHandoff(
        experiment_id="comparison-1",
        campaign_id="C0010",
        seed=1,
        producer_revision="a" * 40,
        consumer="autosut",
        consumer_revision="b" * 40,
        admitted_plan_sha256=SHA_A,
        procedural_plan_sha256=SHA_B,
        binding_catalog_sha256=SHA_A,
        action_catalog_sha256=SHA_B,
        execution_semantic_sha256=SHA_A,
    )
    handoff.finalize_hash()
    encoded = handoff.model_dump_json()
    assert ExecutionHandoff.model_validate_json(encoded).validate_hash()
    altered = json.loads(encoded)
    altered["seed"] = 2
    assert not ExecutionHandoff.model_validate(altered).validate_hash()


def admitted_proposal(**updates: object) -> NeutralProposalRecord:
    values: dict[str, object] = {
        "proposal_id": "proposal-1",
        "experiment_id": "comparison-1",
        "campaign_id": "C0010",
        "step_id": "s1",
        "arm_id": ArmId.sticks_admitted,
        "seed": 1,
        "technique_id": "T0001",
        "execution_domain": "linux",
        "template_id": "probe-host",
        "proposal_budget_sha256": SHA_A,
        "raw_output_sha256": SHA_B,
    }
    values.update(updates)
    proposal = NeutralProposalRecord.model_validate(values)
    proposal.finalize_hash()
    return proposal


def test_admitted_plan_binds_exact_proposal_sequence() -> None:
    plan = AdmittedCampaignPlan(
        experiment_id="comparison-1",
        campaign_id="C0010",
        seed=1,
        collection_lock_sha256=SHA_A,
        proposals=[admitted_proposal()],
    )
    plan.finalize_hash()
    assert plan.validate_hash()

    with pytest.raises(ValidationError, match="only admitted-arm proposals"):
        AdmittedCampaignPlan(
            experiment_id="comparison-1",
            campaign_id="C0010",
            seed=1,
            collection_lock_sha256=SHA_A,
            proposals=[admitted_proposal(arm_id=ArmId.prior_work_style)],
        )

    altered = plan.model_dump(mode="json")
    altered["proposals"][0]["template_id"] = "other-template"
    with pytest.raises(ValidationError, match="proposal record hash mismatch"):
        AdmittedCampaignPlan.model_validate(altered)


def write_execution_evidence(root: Path) -> list[EvidenceReference]:
    plan = AdmittedCampaignPlan(
        experiment_id="comparison-1",
        campaign_id="C0010",
        seed=1,
        collection_lock_sha256=SHA_A,
        proposals=[admitted_proposal()],
    )
    plan.finalize_hash()
    bridge = ExecutionSemanticBridge(
        experiment_id="comparison-1",
        campaign_id="C0010",
        runtime_campaign_id="0.c0010",
        seed=1,
        admitted_plan_sha256=plan.content_sha256,
        concretized_plan_sha256=SHA_A,
        runtime_contract_sha256=SHA_B,
        steps=[
            ExecutionBridgeStep(
                step_id="s1",
                occurrence=1,
                proposal_sha256=plan.proposals[0].content_sha256,
                technique_id="T0001",
                template_id="probe-host",
                bindings_sha256=SHA_A,
                executor_id="executors.fixture.probe",
                executor_sha256=SHA_B,
            )
        ],
    )
    bridge.finalize_hash()
    handoff = ExecutionHandoff(
        experiment_id="comparison-1",
        campaign_id="C0010",
        seed=1,
        producer_revision="a" * 40,
        consumer="autosut",
        consumer_revision="b" * 40,
        admitted_plan_sha256=plan.content_sha256,
        procedural_plan_sha256=SHA_B,
        binding_catalog_sha256=SHA_A,
        action_catalog_sha256=SHA_B,
        execution_semantic_sha256=bridge.content_sha256,
    )
    handoff.finalize_hash()
    receipt = ConsumerExecutionReceipt(
        experiment_id="comparison-1",
        campaign_id="C0010",
        seed=1,
        handoff_sha256=handoff.content_sha256,
        consumer_revision="b" * 40,
        raw_execution_sha256=SHA_A,
        status=RunStatus.succeeded,
    )
    receipt.finalize_hash()
    observation = IndependentEffectObservation(
        experiment_id="comparison-1",
        campaign_id="C0010",
        seed=1,
        handoff_sha256=handoff.content_sha256,
        admission_oracle_revision=SHA_A,
        observer_revision=SHA_B,
        effects=[
            StepEffectObservation(
                step_id="s1",
                effect_class=EffectClass.target_observed,
                predicate_id="target.fixture.present",
                raw_evidence_sha256=SHA_A,
            )
        ],
    )
    observation.finalize_hash()
    documents = {
        EvidenceRole.admitted_plan: ("admitted-plan.json", plan.model_dump_json()),
        EvidenceRole.execution_semantic_bridge: (
            "execution-semantic-bridge.json",
            bridge.model_dump_json(),
        ),
        EvidenceRole.execution_handoff: ("handoff.json", handoff.model_dump_json()),
        EvidenceRole.consumer_receipt: ("receipt.json", receipt.model_dump_json()),
        EvidenceRole.independent_observation: (
            "observation.json",
            observation.model_dump_json(),
        ),
    }
    references = []
    for role, (name, document) in documents.items():
        path = root / name
        path.write_text(document + "\n", encoding="utf-8")
        references.append(
            EvidenceReference(
                path=name,
                sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                role=role,
            )
        )
    return references


def test_execution_success_requires_typed_independent_evidence(tmp_path: Path) -> None:
    references = write_execution_evidence(tmp_path)
    record = RunRecord(
        campaign_id="C0010",
        arm_id=ArmId.sticks_autosut_executed,
        seed=1,
        status=RunStatus.succeeded,
        evidence=references,
    )
    ledger = RunLedger(experiment_id="comparison-1", records=[record])
    ledger.validate_evidence(tmp_path)
    ledger.validate_execution_evidence(tmp_path)

    with pytest.raises(ValidationError, match="exactly one admitted plan"):
        RunRecord(
            campaign_id="C0010",
            arm_id=ArmId.sticks_autosut_executed,
            seed=1,
            status=RunStatus.succeeded,
            evidence=references[:-1],
        )


def test_execution_observer_cannot_reuse_admission_authority() -> None:
    with pytest.raises(ValidationError, match="independent of the admission oracle"):
        IndependentEffectObservation(
            experiment_id="comparison-1",
            campaign_id="C0010",
            seed=1,
            handoff_sha256=SHA_A,
            admission_oracle_revision=SHA_B,
            observer_revision=SHA_B,
            effects=[
                StepEffectObservation(
                    step_id="s1",
                    effect_class=EffectClass.failed,
                    predicate_id="target.fixture.present",
                    raw_evidence_sha256=SHA_A,
                )
            ],
        )


def test_execution_evidence_must_match_handoff(tmp_path: Path) -> None:
    references = write_execution_evidence(tmp_path)
    receipt_path = tmp_path / "receipt.json"
    receipt = ConsumerExecutionReceipt.model_validate_json(receipt_path.read_text())
    receipt.handoff_sha256 = SHA_B
    receipt.finalize_hash()
    receipt_path.write_text(receipt.model_dump_json() + "\n", encoding="utf-8")
    receipt_reference = next(
        reference
        for reference in references
        if reference.role == EvidenceRole.consumer_receipt
    )
    receipt_reference.sha256 = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    record = RunRecord(
        campaign_id="C0010",
        arm_id=ArmId.sticks_autosut_executed,
        seed=1,
        status=RunStatus.succeeded,
        evidence=references,
    )
    ledger = RunLedger(experiment_id="comparison-1", records=[record])
    ledger.validate_evidence(tmp_path)
    with pytest.raises(ValueError, match="not bound to the execution handoff"):
        ledger.validate_execution_evidence(tmp_path)


def test_execution_handoff_must_name_exact_admitted_plan(tmp_path: Path) -> None:
    references = write_execution_evidence(tmp_path)
    handoff_path = tmp_path / "handoff.json"
    handoff = ExecutionHandoff.model_validate_json(handoff_path.read_text())
    handoff.admitted_plan_sha256 = SHA_B
    handoff.finalize_hash()
    handoff_path.write_text(handoff.model_dump_json() + "\n", encoding="utf-8")
    handoff_reference = next(
        reference
        for reference in references
        if reference.role == EvidenceRole.execution_handoff
    )
    handoff_reference.sha256 = hashlib.sha256(handoff_path.read_bytes()).hexdigest()
    record = RunRecord(
        campaign_id="C0010",
        arm_id=ArmId.sticks_autosut_executed,
        seed=1,
        status=RunStatus.succeeded,
        evidence=references,
    )
    ledger = RunLedger(experiment_id="comparison-1", records=[record])
    ledger.validate_evidence(tmp_path)
    with pytest.raises(ValueError, match="not bound to the admitted plan"):
        ledger.validate_execution_evidence(tmp_path)
