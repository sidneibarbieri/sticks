"""Run the bounded, non-interactive Stage 2 planning curation protocol.

The controller keeps three authorities separate: a provider may propose abstract
template metadata, deterministic code decides admission, and only an existing
hash-bound implementation witness may make an admitted template available to
the realization search.  It never emits commands or executes a campaign.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field

from contracts.procedural_ir import ProceduralPlan

from .fact_semantics import (
    FactSemanticAudit,
    FactSemanticsRegistry,
    audit_fact_semantics,
)
from .models import ActionTemplate, BindingCatalog, StrictModel
from .pipeline import action_catalog_hash
from .provider import ProviderConfig
from .realization_space import RealizationSpace, enumerate_realization_space
from .target_queue import TemplateGenerationQueue, build_template_generation_queue
from .template_generation import (
    TemplateGenerationBatch,
    context_bindings_from_generation_batch,
    generate_template_candidates,
)
from .template_overlay import (
    TemplateImplementationWitness,
    TemplateOverlay,
    build_template_overlay,
)


class Stage2CurationLimits(StrictModel):
    """Declared finite limits for one planning-only curation pass."""

    desired_procedure_assignments_per_step: int = Field(default=2, ge=1)
    desired_behavior_contracts_per_step: int = Field(default=2, ge=1)
    maximum_generation_targets: int = Field(default=12, ge=1)
    maximum_realizations: int = Field(default=64, ge=1)
    maximum_search_states: int = Field(default=10000, ge=1)
    maximum_candidates_per_step: int = Field(default=512, ge=1)
    maximum_attempts_per_target: int = Field(default=3, ge=1)


class CurationOutcome(str, Enum):
    """A non-overlapping observation emitted by the controller."""

    catalog_sufficient = "catalog_sufficient"
    trusted_behavior_contract_gap = "trusted_behavior_contract_gap"
    generation_context_unavailable = "generation_context_unavailable"
    generation_budget_deferred = "generation_budget_deferred"
    no_admitted_candidate = "no_admitted_candidate"
    planning_only_candidate = "planning_only_candidate"
    implementation_bound_candidate = "implementation_bound_candidate"


class BoundaryStatus(str, Enum):
    verified = "verified"
    absent = "absent"
    outside_scope = "outside_scope"


class CurationBoundary(StrictModel):
    """An explicit guarantee or non-claim at the planning boundary."""

    boundary_id: str
    status: BoundaryStatus
    detail: str


class Stage2CurationLedger(StrictModel):
    """Hash-bound receipt for one non-interactive Stage 2 curation pass."""

    schema_version: str = "1"
    controller_policy: str = "bounded_proposal_deterministic_admission_exact_witness_binding"
    operational_status: Literal["not_run"] = "not_run"
    campaign_id: str
    controller_input_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    source_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_semantics_registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_action_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    post_overlay_action_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_fact_semantic_audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    post_overlay_fact_semantic_audit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider_config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    baseline_realization_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generation_queue_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    template_generation_batch_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    template_overlay_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    post_overlay_realization_space_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    runtime_manual_decision_count: int = Field(default=0, ge=0, le=0)
    proposal_target_count: int = Field(ge=0)
    provider_request_count: int = Field(ge=0)
    admitted_candidate_count: int = Field(ge=0)
    rejected_candidate_count: int = Field(ge=0)
    planning_only_candidate_count: int = Field(ge=0)
    implementation_bound_candidate_count: int = Field(ge=0)
    baseline_realization_count: int = Field(ge=0)
    post_overlay_realization_count: int = Field(ge=0)
    baseline_procedure_assignment_variant_count: int = Field(ge=0)
    post_overlay_procedure_assignment_variant_count: int = Field(ge=0)
    baseline_behavior_contract_variant_count: int = Field(ge=0)
    post_overlay_behavior_contract_variant_count: int = Field(ge=0)
    outcomes: list[CurationOutcome] = Field(default_factory=list)
    boundaries: list[CurationBoundary] = Field(default_factory=list)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        self.content_sha256 = _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )


class Stage2CurationResult(StrictModel):
    """The complete planning record produced by :func:`run_stage2_curation`."""

    schema_version: str = "1"
    operational_status: Literal["not_run"] = "not_run"
    baseline_fact_semantic_audit: FactSemanticAudit
    baseline_realization_space: RealizationSpace
    generation_queue: TemplateGenerationQueue
    template_generation_batch: TemplateGenerationBatch
    template_overlay: TemplateOverlay
    post_overlay_fact_semantic_audit: FactSemanticAudit
    post_overlay_realization_space: RealizationSpace
    ledger: Stage2CurationLedger


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _model_list_hash(models: list[StrictModel]) -> str:
    return _canonical_hash([model.model_dump(mode="json") for model in models])


def _validate_content_hash(model: StrictModel, label: str) -> None:
    content_sha256 = getattr(model, "content_sha256", "")
    expected = _canonical_hash(model.model_dump(mode="json", exclude={"content_sha256"}))
    if not content_sha256 or content_sha256 != expected:
        raise ValueError(f"{label} content hash mismatch")


def _sorted_templates(templates: list[ActionTemplate]) -> list[ActionTemplate]:
    identifiers = [template.template_id for template in templates]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("action template identifiers must be unique")
    return sorted(templates, key=lambda template: template.template_id)


def _controller_input_hash(
    *,
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    fact_semantics_registry: FactSemanticsRegistry,
    base_action_catalog_sha256: str,
    provider_config: ProviderConfig,
    witnesses: list[TemplateImplementationWitness],
    limits: Stage2CurationLimits,
) -> str:
    return _canonical_hash(
        {
            "source_plan_sha256": plan.content_sha256,
            "binding_catalog_sha256": catalog.content_sha256,
            "fact_semantics_registry_sha256": fact_semantics_registry.content_sha256,
            "base_action_catalog_sha256": base_action_catalog_sha256,
            "provider_config": provider_config.model_dump(mode="json"),
            "witness_source_sha256": _model_list_hash(witnesses),
            "limits": limits.model_dump(mode="json"),
        }
    )


def _outcomes(
    queue: TemplateGenerationQueue,
    batch: TemplateGenerationBatch,
    overlay: TemplateOverlay,
) -> list[CurationOutcome]:
    outcomes: list[CurationOutcome] = []
    if queue.total_procedure_assignment_deficit == 0 and queue.total_behavior_contract_deficit == 0:
        outcomes.append(CurationOutcome.catalog_sufficient)
    if queue.total_behavior_contract_deficit:
        outcomes.append(CurationOutcome.trusted_behavior_contract_gap)
    if any(
        need.requested_additional_procedure_assignment_count > 0 and not need.context_constructible
        for need in queue.needs
    ):
        outcomes.append(CurationOutcome.generation_context_unavailable)
    if queue.unselected_procedure_assignment_deficit:
        outcomes.append(CurationOutcome.generation_budget_deferred)
    if queue.selected_target_count and not batch.admitted_count:
        outcomes.append(CurationOutcome.no_admitted_candidate)
    if overlay.planning_only_count:
        outcomes.append(CurationOutcome.planning_only_candidate)
    if overlay.implementation_bound_count:
        outcomes.append(CurationOutcome.implementation_bound_candidate)
    return outcomes


def _boundaries(overlay: TemplateOverlay) -> list[CurationBoundary]:
    implementation_status = (
        BoundaryStatus.absent if overlay.planning_only_count else BoundaryStatus.verified
    )
    implementation_detail = (
        "At least one admitted candidate remains planning_only because no valid, "
        "hash-bound laboratory implementation witness was supplied."
        if overlay.planning_only_count
        else "Every admitted candidate is either rejected or has a valid implementation witness."
    )
    return [
        CurationBoundary(
            boundary_id="runtime_manual_decision",
            status=BoundaryStatus.verified,
            detail=(
                "The controller contains no runtime manual acceptance, rejection, "
                "prompt-adjustment, or realization-selection branch."
            ),
        ),
        CurationBoundary(
            boundary_id="semantic_fact_registry",
            status=BoundaryStatus.verified,
            detail=(
                "Every fact used by the base and promoted template catalogs has a unique "
                "versioned semantic identity and an allowed planning origin. This static "
                "audit does not establish a live state or observed effect."
            ),
        ),
        CurationBoundary(
            boundary_id="implementation_witness",
            status=implementation_status,
            detail=implementation_detail,
        ),
        CurationBoundary(
            boundary_id="independent_effect_evidence",
            status=BoundaryStatus.outside_scope,
            detail=(
                "The controller performs planning only; it neither executes a campaign "
                "nor observes a declared effect."
            ),
        ),
    ]


def _write_model(path: Path, model: StrictModel) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(model.model_dump_json(indent=2) + "\n")


def _write_result(result: Stage2CurationResult, output_dir: Path) -> None:
    _write_model(
        output_dir / "baseline-fact-semantics-audit.json",
        result.baseline_fact_semantic_audit,
    )
    _write_model(output_dir / "baseline-realization-space.json", result.baseline_realization_space)
    _write_model(output_dir / "template-generation-queue.json", result.generation_queue)
    _write_model(output_dir / "template-generation-batch.json", result.template_generation_batch)
    _write_model(output_dir / "template-overlay.json", result.template_overlay)
    _write_model(
        output_dir / "post-overlay-fact-semantics-audit.json",
        result.post_overlay_fact_semantic_audit,
    )
    _write_model(
        output_dir / "post-overlay-realization-space.json",
        result.post_overlay_realization_space,
    )
    _write_model(output_dir / "stage2-curation-ledger.json", result.ledger)


def run_stage2_curation(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    fact_semantics_registry: FactSemanticsRegistry,
    base_templates: list[ActionTemplate],
    provider_config: ProviderConfig,
    *,
    implementation_witnesses: list[TemplateImplementationWitness],
    artifact_root: Path,
    output_dir: Path,
    limits: Stage2CurationLimits | None = None,
) -> Stage2CurationResult:
    """Execute one bounded Stage 2 planning pass and write immutable receipts.

    ``output_dir`` must not exist.  Existing evidence is never overwritten, and provider
    failures propagate after preserving any call records already written below that directory.
    """

    active_limits = limits or Stage2CurationLimits()
    if output_dir.exists():
        raise FileExistsError(f"Stage 2 output directory already exists: {output_dir}")
    if not artifact_root.is_dir():
        raise NotADirectoryError(f"artifact root is not a directory: {artifact_root}")
    if not plan.validate_hash():
        raise ValueError("source procedural plan hash mismatch")
    if not catalog.validate_hash():
        raise ValueError("binding catalog hash mismatch")
    if not fact_semantics_registry.validate_hash():
        raise ValueError("fact semantic registry hash mismatch")

    base = _sorted_templates(base_templates)
    base_action_catalog_sha256 = action_catalog_hash(base)
    baseline_fact_semantic_audit = audit_fact_semantics(
        fact_semantics_registry,
        catalog,
        base,
    )
    if not baseline_fact_semantic_audit.conformant:
        raise ValueError("base action catalog fails the semantic fact audit")
    baseline = enumerate_realization_space(
        plan,
        catalog,
        base,
        maximum_realizations=active_limits.maximum_realizations,
        maximum_search_states=active_limits.maximum_search_states,
        maximum_candidates_per_step=active_limits.maximum_candidates_per_step,
    )
    _validate_content_hash(baseline, "baseline realization space")
    queue = build_template_generation_queue(
        plan,
        catalog,
        base,
        desired_procedure_assignments_per_step=(
            active_limits.desired_procedure_assignments_per_step
        ),
        desired_behavior_contracts_per_step=(active_limits.desired_behavior_contracts_per_step),
        maximum_targets=active_limits.maximum_generation_targets,
        maximum_realizations=active_limits.maximum_realizations,
        maximum_search_states=active_limits.maximum_search_states,
        realization_space=baseline,
    )
    _validate_content_hash(queue, "template generation queue")

    output_dir.mkdir(parents=True, exist_ok=False)
    batch = generate_template_candidates(
        queue.targets,
        base,
        provider_config,
        output_dir=output_dir / "provider-evidence",
        max_attempts_per_target=active_limits.maximum_attempts_per_target,
    )
    _validate_content_hash(batch, "template generation batch")
    if batch.base_action_catalog_sha256 != base_action_catalog_sha256:
        raise ValueError("template generation batch targets another action catalog")

    overlay = build_template_overlay(
        base,
        batch.templates,
        context_bindings_from_generation_batch(batch),
        implementation_witnesses,
        artifact_root=artifact_root,
    )
    _validate_content_hash(overlay, "template overlay")
    if overlay.base_action_catalog_sha256 != base_action_catalog_sha256:
        raise ValueError("template overlay targets another action catalog")
    if overlay.candidate_source_sha256 != _model_list_hash(batch.templates):
        raise ValueError("template overlay targets another candidate batch")

    post_overlay_templates = _sorted_templates([*base, *overlay.implementation_bound_templates])
    post_overlay_action_catalog_sha256 = action_catalog_hash(post_overlay_templates)
    post_overlay_fact_semantic_audit = audit_fact_semantics(
        fact_semantics_registry,
        catalog,
        post_overlay_templates,
    )
    if not post_overlay_fact_semantic_audit.conformant:
        raise ValueError("promoted action catalog fails the semantic fact audit")
    post_overlay = enumerate_realization_space(
        plan,
        catalog,
        post_overlay_templates,
        maximum_realizations=active_limits.maximum_realizations,
        maximum_search_states=active_limits.maximum_search_states,
        maximum_candidates_per_step=active_limits.maximum_candidates_per_step,
        template_overlay_sha256=overlay.content_sha256,
    )
    _validate_content_hash(post_overlay, "post-overlay realization space")

    admitted_candidate_count = batch.admitted_count
    ledger = Stage2CurationLedger(
        campaign_id=plan.campaign_id,
        controller_input_sha256=_controller_input_hash(
            plan=plan,
            catalog=catalog,
            fact_semantics_registry=fact_semantics_registry,
            base_action_catalog_sha256=base_action_catalog_sha256,
            provider_config=provider_config,
            witnesses=implementation_witnesses,
            limits=active_limits,
        ),
        source_plan_sha256=plan.content_sha256,
        binding_catalog_sha256=catalog.content_sha256,
        fact_semantics_registry_sha256=fact_semantics_registry.content_sha256,
        base_action_catalog_sha256=base_action_catalog_sha256,
        post_overlay_action_catalog_sha256=post_overlay_action_catalog_sha256,
        baseline_fact_semantic_audit_sha256=baseline_fact_semantic_audit.content_sha256,
        post_overlay_fact_semantic_audit_sha256=post_overlay_fact_semantic_audit.content_sha256,
        provider_config_sha256=_canonical_hash(provider_config.model_dump(mode="json")),
        baseline_realization_space_sha256=baseline.content_sha256,
        generation_queue_sha256=queue.content_sha256,
        template_generation_batch_sha256=batch.content_sha256,
        template_overlay_sha256=overlay.content_sha256,
        post_overlay_realization_space_sha256=post_overlay.content_sha256,
        proposal_target_count=queue.selected_target_count,
        provider_request_count=batch.request_count,
        admitted_candidate_count=admitted_candidate_count,
        rejected_candidate_count=max(0, batch.target_count - admitted_candidate_count),
        planning_only_candidate_count=overlay.planning_only_count,
        implementation_bound_candidate_count=overlay.implementation_bound_count,
        baseline_realization_count=baseline.realization_count,
        post_overlay_realization_count=post_overlay.realization_count,
        baseline_procedure_assignment_variant_count=(baseline.procedure_assignment_variant_count),
        post_overlay_procedure_assignment_variant_count=(
            post_overlay.procedure_assignment_variant_count
        ),
        baseline_behavior_contract_variant_count=(baseline.behavior_contract_variant_count),
        post_overlay_behavior_contract_variant_count=(post_overlay.behavior_contract_variant_count),
        outcomes=_outcomes(queue, batch, overlay),
        boundaries=_boundaries(overlay),
    )
    ledger.finalize_hash()
    result = Stage2CurationResult(
        baseline_fact_semantic_audit=baseline_fact_semantic_audit,
        baseline_realization_space=baseline,
        generation_queue=queue,
        template_generation_batch=batch,
        template_overlay=overlay,
        post_overlay_fact_semantic_audit=post_overlay_fact_semantic_audit,
        post_overlay_realization_space=post_overlay,
        ledger=ledger,
    )
    _write_result(result, output_dir)
    return result
