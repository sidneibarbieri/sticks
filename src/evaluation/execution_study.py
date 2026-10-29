"""Qualify one revision-bound execution arm without weakening runtime evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from pydantic import BaseModel

from evaluation.controlled_comparison import (
    AdmittedCampaignPlan,
    ConsumerExecutionReceipt,
    EffectClass,
    ExecutionHandoff,
    ExecutionSemanticBridge,
    IndependentEffectObservation,
    RunStatus,
    StepEffectObservation,
    canonical_sha256,
)
from runners.capability_authority import (
    registered_authority_revision,
    validate_registered_predicate,
)
from runners.runtime_campaign_report import (
    RuntimeCampaignReport,
    RuntimeCampaignStep,
    parse_retained_campaign_report,
)

ExecutionConsumer = Callable[[str, Path], tuple[RuntimeCampaignReport, bytes]]


def build_execution_handoff(
    plan: AdmittedCampaignPlan,
    bridge: ExecutionSemanticBridge,
    *,
    producer_revision: str,
    consumer: str,
    consumer_revision: str,
    binding_catalog_sha256: str,
    action_catalog_sha256: str,
) -> ExecutionHandoff:
    """Bind an admitted plan and semantic bridge before runtime execution."""
    if not plan.validate_hash():
        raise ValueError("admitted plan content hash mismatch")
    if not bridge.validate_hash():
        raise ValueError("execution semantic bridge content hash mismatch")
    if (
        bridge.experiment_id != plan.experiment_id
        or bridge.campaign_id != plan.campaign_id
        or bridge.seed != plan.seed
        or bridge.admitted_plan_sha256 != plan.content_sha256
    ):
        raise ValueError("semantic bridge does not identify the admitted plan")
    handoff = ExecutionHandoff(
        experiment_id=plan.experiment_id,
        campaign_id=plan.campaign_id,
        seed=plan.seed,
        producer_revision=producer_revision,
        consumer=consumer,
        consumer_revision=consumer_revision,
        admitted_plan_sha256=plan.content_sha256,
        procedural_plan_sha256=bridge.concretized_plan_sha256,
        binding_catalog_sha256=binding_catalog_sha256,
        action_catalog_sha256=action_catalog_sha256,
        execution_semantic_sha256=bridge.content_sha256,
    )
    handoff.finalize_hash()
    return handoff


def _observed_effect(step: RuntimeCampaignStep) -> StepEffectObservation:
    if step.outcome is None:
        raise ValueError("observed runtime step lacks an outcome")
    observations = step.outcome.observations
    references = step.outcome.observation_references
    if not observations or len(observations) != len(references):
        raise ValueError("observed runtime step lacks exact observation references")
    if not all(observation.passed for observation in observations):
        raise ValueError("observed runtime step contains a failed predicate")
    loci = {observation.scope.locus for observation in observations}
    if loci == {"target"}:
        effect_class = EffectClass.target_observed
    elif loci == {"controller"}:
        effect_class = EffectClass.controller_observed
    else:
        raise ValueError("one runtime step cannot collapse mixed observation loci")
    predicate_ids = sorted({observation.predicate_id for observation in observations})
    if [reference.predicate_id for reference in references] != [
        observation.predicate_id for observation in observations
    ]:
        raise ValueError("observation references differ from measured predicates")
    for reference in references:
        validate_registered_predicate(reference.authority_id, reference.predicate_id)
    return StepEffectObservation(
        step_id=f"s{step.contract.occurrence}",
        effect_class=effect_class,
        predicate_id="+".join(predicate_ids),
        raw_evidence_sha256=canonical_sha256(
            [reference.record_sha256 for reference in references]
        ),
    )


def _nonobserved_effect(step: RuntimeCampaignStep) -> StepEffectObservation:
    effect_class = (
        EffectClass.simulated if step.status == "simulated" else EffectClass.failed
    )
    return StepEffectObservation(
        step_id=f"s{step.contract.occurrence}",
        effect_class=effect_class,
        predicate_id=(
            "simulation-contract"
            if effect_class == EffectClass.simulated
            else "runtime-failure"
        ),
        raw_evidence_sha256=canonical_sha256(step.model_dump(mode="json")),
    )


def qualify_runtime_execution(
    handoff: ExecutionHandoff,
    bridge: ExecutionSemanticBridge,
    report: RuntimeCampaignReport,
    *,
    raw_execution: bytes,
    admission_oracle_revision: str,
) -> tuple[ConsumerExecutionReceipt, IndependentEffectObservation]:
    """Verify exact runtime bindings and derive typed execution evidence."""
    if not handoff.validate_hash():
        raise ValueError("execution handoff content hash mismatch")
    if not bridge.validate_hash():
        raise ValueError("execution semantic bridge content hash mismatch")
    if handoff.execution_semantic_sha256 != bridge.content_sha256:
        raise ValueError("execution handoff is not bound to the semantic bridge")
    if report.campaign_id != bridge.runtime_campaign_id:
        raise ValueError("runtime report belongs to another campaign")
    if report.error_type is not None or report.error_message is not None:
        raise ValueError("runtime report contains a campaign-level failure")
    if len(report.steps) != len(bridge.steps):
        raise ValueError("runtime report and semantic bridge step counts differ")

    effects = []
    observer_authorities = set()
    for runtime_step, bridge_step in zip(report.steps, bridge.steps, strict=True):
        contract = runtime_step.contract
        if (
            contract.occurrence != bridge_step.occurrence
            or contract.technique_id != bridge_step.technique_id
            or contract.executor_id != bridge_step.executor_id
            or contract.executor_sha256 != bridge_step.executor_sha256
        ):
            raise ValueError(
                f"runtime contract differs from semantic bridge at s{bridge_step.occurrence}"
            )
        if runtime_step.outcome is not None:
            observer_authorities.update(
                reference.authority_id
                for reference in runtime_step.outcome.observation_references
            )
        effects.append(
            _observed_effect(runtime_step)
            if runtime_step.status == "observed"
            else _nonobserved_effect(runtime_step)
        )

    receipt = ConsumerExecutionReceipt(
        experiment_id=handoff.experiment_id,
        campaign_id=handoff.campaign_id,
        seed=handoff.seed,
        handoff_sha256=handoff.content_sha256,
        consumer_revision=handoff.consumer_revision,
        raw_execution_sha256=hashlib.sha256(raw_execution).hexdigest(),
        status=RunStatus.succeeded,
    )
    receipt.finalize_hash()
    observation = IndependentEffectObservation(
        experiment_id=handoff.experiment_id,
        campaign_id=handoff.campaign_id,
        seed=handoff.seed,
        handoff_sha256=handoff.content_sha256,
        admission_oracle_revision=admission_oracle_revision,
        observer_revision=registered_authority_revision(observer_authorities),
        effects=effects,
    )
    observation.finalize_hash()
    return receipt, observation


def _write_model(path: Path, model: BaseModel) -> None:
    content = model.model_dump_json(indent=2).encode("utf-8") + b"\n"
    with path.open("xb") as output:
        output.write(content)


def run_revision_bound_execution(
    plan: AdmittedCampaignPlan,
    bridge: ExecutionSemanticBridge,
    *,
    output_dir: Path,
    producer_revision: str,
    consumer: str,
    consumer_revision: str,
    binding_catalog_sha256: str,
    action_catalog_sha256: str,
    admission_oracle_revision: str,
    execute: ExecutionConsumer,
) -> tuple[ConsumerExecutionReceipt, IndependentEffectObservation]:
    """Persist the pre-execution contract, execute once, then qualify raw output."""
    handoff = build_execution_handoff(
        plan,
        bridge,
        producer_revision=producer_revision,
        consumer=consumer,
        consumer_revision=consumer_revision,
        binding_catalog_sha256=binding_catalog_sha256,
        action_catalog_sha256=action_catalog_sha256,
    )
    output_dir.mkdir(parents=True, exist_ok=False)
    _write_model(output_dir / "admitted-plan.json", plan)
    _write_model(output_dir / "execution-semantic-bridge.json", bridge)
    _write_model(output_dir / "execution-handoff.json", handoff)

    report, raw_execution = execute(bridge.runtime_campaign_id, output_dir / "runtime")
    retained_report = parse_retained_campaign_report(raw_execution.decode("utf-8"))
    if retained_report != report:
        raise ValueError("consumer report differs from retained execution bytes")
    receipt, observation = qualify_runtime_execution(
        handoff,
        bridge,
        report,
        raw_execution=raw_execution,
        admission_oracle_revision=admission_oracle_revision,
    )
    _write_model(output_dir / "consumer-receipt.json", receipt)
    _write_model(output_dir / "independent-observation.json", observation)
    return receipt, observation
