"""Derive bounded, campaign-aware template-generation targets."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field

from contracts.procedural_ir import ProceduralPlan, ProcedureStep

from .models import ActionTemplate, BindingCatalog, BindingScope, StrictModel
from .pipeline import action_catalog_hash
from .realization_space import (
    EnumerationStatus,
    RealizationSpace,
    enumerate_realization_space,
)
from .template_generation import TemplateGenerationTarget
from .template_proposer import (
    TemplateProposalContext,
    TrustedBehaviorContract,
    trusted_behavior_contract,
)


class GenerationNeed(StrictModel):
    source_step_index: int = Field(ge=0)
    technique_id: str
    candidate_count: int = Field(ge=0)
    realized_procedure_assignment_count: int = Field(ge=0)
    realized_behavior_contract_count: int = Field(ge=0)
    trusted_behavior_contract_count: int = Field(ge=0)
    requested_additional_procedure_assignment_count: int = Field(ge=0)
    unmet_behavior_contract_count: int = Field(ge=0)
    selected_target_count: int = Field(ge=0)
    context_constructible: bool
    reason: str


class TemplateGenerationQueue(StrictModel):
    schema_version: str = "1"
    campaign_id: str
    source_plan_sha256: str
    binding_catalog_sha256: str
    action_catalog_sha256: str
    realization_space_sha256: str
    enumeration_status: EnumerationStatus
    desired_procedure_assignments_per_step: int = Field(ge=1)
    desired_behavior_contracts_per_step: int = Field(ge=1)
    maximum_targets: int = Field(ge=1)
    total_procedure_assignment_deficit: int = Field(ge=0)
    total_behavior_contract_deficit: int = Field(ge=0)
    selected_target_count: int = Field(ge=0)
    unselected_procedure_assignment_deficit: int = Field(ge=0)
    operational_status: Literal["not_run"] = "not_run"
    needs: list[GenerationNeed] = Field(default_factory=list)
    targets: list[TemplateGenerationTarget] = Field(default_factory=list)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()


def _technique_summary(step: ProcedureStep) -> str:
    parts = [step.name, f"execution domain: {step.execution_domain}"]
    if step.platforms:
        parts.append("platforms: " + ", ".join(sorted(step.platforms)))
    if step.system_requirements:
        parts.append("requirements: " + "; ".join(step.system_requirements))
    if step.procedure_descriptions:
        parts.append("source procedure: " + " ".join(step.procedure_descriptions))
    return " | ".join(parts)[:2400]


def _step_contract_templates(
    step: ProcedureStep,
    templates: list[ActionTemplate],
) -> list[ActionTemplate]:
    return [
        template
        for template in templates
        if step.technique_id in template.technique_ids
        and template.execution_domain == step.execution_domain
    ]


def _trusted_contracts(
    templates: list[ActionTemplate],
) -> list[TrustedBehaviorContract]:
    unique: dict[str, TrustedBehaviorContract] = {}
    for template in templates:
        contract = trusted_behavior_contract(template)
        signature = json.dumps(contract.model_dump(mode="json"), sort_keys=True)
        unique.setdefault(signature, contract)
    return [unique[signature] for signature in sorted(unique)]


def _exemplar_ids(
    step: ProcedureStep,
    templates: list[ActionTemplate],
    *,
    maximum: int = 5,
) -> list[str]:
    ranked = sorted(
        templates,
        key=lambda template: (
            step.technique_id not in template.technique_ids,
            template.execution_domain != step.execution_domain,
            template.template_id,
        ),
    )
    return [template.template_id for template in ranked[:maximum]]


def _proposal_context(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    *,
    source_step_index: int,
) -> TemplateProposalContext | None:
    step = plan.steps[source_step_index]
    matching = _step_contract_templates(step, templates)
    if not matching:
        return None
    required_facts = set(catalog.initial_facts)
    useful_effects = set(catalog.goal_facts)
    for template in matching:
        required_facts.update(template.requires)
        useful_effects.update(template.produces)
    context = TemplateProposalContext(
        campaign_id=plan.campaign_id,
        source_step_index=source_step_index,
        source_plan_sha256=plan.content_sha256,
        binding_catalog_sha256=catalog.content_sha256,
        execution_domain=step.execution_domain,
        admissible_required_facts=sorted(required_facts),
        admissible_produced_facts=sorted(useful_effects),
        available_binding_kinds=sorted(
            {binding.kind for binding in catalog.bindings if binding.scope is BindingScope.lab}
        ),
        existing_template_ids=sorted(template.template_id for template in matching),
        admissible_behavior_contracts=_trusted_contracts(matching),
    )
    context.finalize_hash()
    return context


def build_template_generation_queue(
    plan: ProceduralPlan,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
    *,
    desired_procedure_assignments_per_step: int = 2,
    desired_behavior_contracts_per_step: int = 2,
    maximum_targets: int = 12,
    maximum_realizations: int = 64,
    maximum_search_states: int = 10000,
    realization_space: RealizationSpace | None = None,
) -> TemplateGenerationQueue:
    """Select procedure-variant requests without granting semantic authority to a provider."""

    if desired_procedure_assignments_per_step < 1:
        raise ValueError("desired procedure-assignment count must be positive")
    if desired_behavior_contracts_per_step < 1:
        raise ValueError("desired behavior-contract count must be positive")
    if maximum_targets < 1:
        raise ValueError("maximum target count must be positive")
    expected_action_catalog_sha256 = action_catalog_hash(
        sorted(templates, key=lambda template: template.template_id)
    )
    if realization_space is None:
        realization_space = enumerate_realization_space(
            plan,
            catalog,
            templates,
            maximum_realizations=maximum_realizations,
            maximum_search_states=maximum_search_states,
        )
    if not realization_space.validate_hash():
        raise ValueError("realization space hash mismatch")
    for realization in realization_space.realizations:
        if not realization.validate_hash():
            raise ValueError("realization candidate hash mismatch")
        if not realization.graph.validate_hash():
            raise ValueError("realization graph hash mismatch")
    if realization_space.source_plan_sha256 != plan.content_sha256:
        raise ValueError("realization space targets another source plan")
    if realization_space.binding_catalog_sha256 != catalog.content_sha256:
        raise ValueError("realization space targets another binding catalog")
    if realization_space.action_catalog_sha256 != expected_action_catalog_sha256:
        raise ValueError("realization space targets another action catalog")
    contexts: dict[int, TemplateProposalContext | None] = {}
    procedure_deficits: dict[int, int] = {}
    behavior_deficits: dict[int, int] = {}
    ranked_needs: list[tuple[tuple[int, int, int, int], int, int]] = []
    for coverage in realization_space.step_realization_coverage:
        procedure_deficit = max(
            0,
            desired_procedure_assignments_per_step
            - coverage.realized_procedure_assignment_count,
        )
        behavior_deficit = max(
            0,
            desired_behavior_contracts_per_step - coverage.realized_behavior_contract_count,
        )
        procedure_deficits[coverage.source_step_index] = procedure_deficit
        behavior_deficits[coverage.source_step_index] = behavior_deficit
        if procedure_deficit or behavior_deficit:
            contexts[coverage.source_step_index] = _proposal_context(
                plan,
                catalog,
                templates,
                source_step_index=coverage.source_step_index,
            )
        if procedure_deficit and contexts.get(coverage.source_step_index) is not None:
            priority = (
                coverage.realized_procedure_assignment_count > 0,
                coverage.candidate_count > 0,
                -procedure_deficit,
                coverage.source_step_index,
            )
            ranked_needs.append(
                (priority, coverage.source_step_index, procedure_deficit)
            )
    ranked_needs.sort()

    selected_by_step: dict[int, int] = {}
    targets: list[TemplateGenerationTarget] = []
    for _, source_step_index, procedure_deficit in ranked_needs:
        context = contexts[source_step_index]
        if context is None:
            continue
        step = plan.steps[source_step_index]
        selected_count = min(procedure_deficit, maximum_targets - len(targets))
        for variant_index in range(1, selected_count + 1):
            targets.append(
                TemplateGenerationTarget(
                    target_id=(
                        f"{plan.campaign_id}:{source_step_index}:"
                        f"{step.technique_id}:v{variant_index}"
                    ),
                    technique_id=step.technique_id,
                    technique_summary=_technique_summary(step),
                    exemplar_template_ids=_exemplar_ids(step, templates),
                    context=context,
                )
            )
        selected_by_step[source_step_index] = selected_count

    coverage_by_step = {
        coverage.source_step_index: coverage
        for coverage in realization_space.step_realization_coverage
    }
    needs: list[GenerationNeed] = []
    for source_step_index, coverage in sorted(coverage_by_step.items()):
        procedure_deficit = procedure_deficits[source_step_index]
        behavior_deficit = behavior_deficits[source_step_index]
        if not procedure_deficit and not behavior_deficit:
            continue
        context = contexts.get(source_step_index)
        selected = selected_by_step.get(source_step_index, 0)
        if context is None:
            reason = "no trusted behavior contract exists for this source step"
        elif selected:
            reason = (
                "selected from measured procedure-assignment deficit under an existing "
                "trusted behavior contract"
            )
        elif procedure_deficit:
            reason = "deferred by the declared target budget"
        else:
            reason = (
                "behavior-contract diversity is measured but cannot be expanded by an "
                "untrusted proposal"
            )
        needs.append(
            GenerationNeed(
                source_step_index=source_step_index,
                technique_id=coverage.technique_id,
                candidate_count=coverage.candidate_count,
                realized_procedure_assignment_count=(
                    coverage.realized_procedure_assignment_count
                ),
                realized_behavior_contract_count=(
                    coverage.realized_behavior_contract_count
                ),
                trusted_behavior_contract_count=(
                    len(context.admissible_behavior_contracts) if context is not None else 0
                ),
                requested_additional_procedure_assignment_count=procedure_deficit,
                unmet_behavior_contract_count=behavior_deficit,
                selected_target_count=selected,
                context_constructible=context is not None,
                reason=reason,
            )
        )

    result = TemplateGenerationQueue(
        campaign_id=plan.campaign_id,
        source_plan_sha256=plan.content_sha256,
        binding_catalog_sha256=catalog.content_sha256,
        action_catalog_sha256=expected_action_catalog_sha256,
        realization_space_sha256=realization_space.content_sha256,
        enumeration_status=realization_space.enumeration_status,
        desired_procedure_assignments_per_step=(
            desired_procedure_assignments_per_step
        ),
        desired_behavior_contracts_per_step=desired_behavior_contracts_per_step,
        maximum_targets=maximum_targets,
        total_procedure_assignment_deficit=sum(procedure_deficits.values()),
        total_behavior_contract_deficit=sum(behavior_deficits.values()),
        selected_target_count=len(targets),
        unselected_procedure_assignment_deficit=(
            sum(procedure_deficits.values()) - len(targets)
        ),
        needs=needs,
        targets=targets,
    )
    result.finalize_hash()
    return result
