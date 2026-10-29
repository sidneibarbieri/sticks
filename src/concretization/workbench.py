"""Application service for the local causal-realization workbench."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Literal

from pydantic import Field

from contracts.procedural_ir import ProceduralPlan

from .fact_semantics import FactSemanticsRegistry, audit_fact_semantics
from .models import ActionTemplate, BindingCatalog, StrictModel
from .realization_space import RealizationSpace, enumerate_realization_space
from .target_queue import TemplateGenerationQueue, build_template_generation_queue


class CampaignIndexEntry(StrictModel):
    campaign_id: str = Field(pattern=r"^C\d{4}$")
    campaign_name: str | None = None
    status: Literal["compiled", "not_compiled"]
    step_count: int | None = Field(default=None, ge=1)
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    path: str | None = None
    reason: str | None = None


class CampaignIndex(StrictModel):
    schema_version: str
    bundle_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_count: int = Field(ge=0)
    compiled_count: int = Field(ge=0)
    not_compiled_count: int = Field(ge=0)
    campaigns: list[CampaignIndexEntry] = Field(default_factory=list)


class CampaignAvailability(StrictModel):
    campaign_id: str
    campaign_name: str
    corpus_status: Literal["compiled", "not_compiled"]
    step_count: int | None = Field(default=None, ge=1)
    plan_path: str | None = None
    binding_catalog_path: str | None = None
    semantic_fact_status: Literal["not_assessed", "conformant", "nonconformant"] = "not_assessed"
    semantic_fact_audit_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    enumeration_ready: bool
    availability_reason: str


class CampaignInventory(StrictModel):
    schema_version: str = "1"
    campaign_count: int = Field(ge=0)
    compiled_count: int = Field(ge=0)
    enumeration_ready_count: int = Field(ge=0)
    semantic_conformant_count: int = Field(ge=0)
    campaigns: list[CampaignAvailability] = Field(default_factory=list)


class WorkbenchEnumerationRequest(StrictModel):
    campaign_id: str = Field(pattern=r"^C\d{4}$")
    maximum_realizations: int = Field(default=64, ge=1, le=256)
    maximum_search_states: int = Field(default=10000, ge=1, le=100000)
    maximum_candidates_per_step: int = Field(default=512, ge=1, le=2048)
    desired_procedure_assignments_per_step: int = Field(default=2, ge=1, le=8)
    desired_behavior_contracts_per_step: int = Field(default=2, ge=1, le=8)
    maximum_generation_targets: int = Field(default=12, ge=1, le=64)


class WorkbenchEnumerationResponse(StrictModel):
    schema_version: str = "1"
    interface_scope: Literal["planning_only"] = "planning_only"
    campaign: CampaignAvailability
    request: WorkbenchEnumerationRequest
    result: RealizationSpace
    generation_queue: TemplateGenerationQueue


class WorkbenchCurationReadinessRequest(StrictModel):
    """Bounds for a static corpus audit of Stage 2 planning inputs."""

    maximum_realizations: int = Field(default=64, ge=1, le=256)
    maximum_search_states: int = Field(default=10000, ge=1, le=100000)
    maximum_candidates_per_step: int = Field(default=512, ge=1, le=2048)
    desired_procedure_assignments_per_step: int = Field(default=2, ge=1, le=8)
    desired_behavior_contracts_per_step: int = Field(default=2, ge=1, le=8)
    maximum_generation_targets: int = Field(default=12, ge=1, le=64)


class CurationReadinessStatus(str, Enum):
    not_compiled = "not_compiled"
    binding_catalog_absent = "binding_catalog_absent"
    semantic_fact_audit_failed = "semantic_fact_audit_failed"
    no_admissible_realization = "no_admissible_realization"
    bounded_planning_ready = "bounded_planning_ready"


class CurationReadinessRow(StrictModel):
    campaign_id: str = Field(pattern=r"^C\d{4}$")
    campaign_name: str
    corpus_status: Literal["compiled", "not_compiled"]
    curation_status: CurationReadinessStatus
    reason: str
    source_plan_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    binding_catalog_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    semantic_fact_status: Literal["not_assessed", "conformant", "nonconformant"] = "not_assessed"
    semantic_fact_audit_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    realization_count: int = Field(default=0, ge=0)
    enumeration_status: str | None = None
    total_procedure_assignment_deficit: int = Field(default=0, ge=0)
    total_behavior_contract_deficit: int = Field(default=0, ge=0)
    selected_generation_target_count: int = Field(default=0, ge=0)
    deferred_procedure_assignment_deficit: int = Field(default=0, ge=0)
    unconstructible_generation_need_count: int = Field(default=0, ge=0)


class CurationReadinessReport(StrictModel):
    schema_version: str = "1"
    interface_scope: Literal["planning_only"] = "planning_only"
    operational_status: Literal["not_run"] = "not_run"
    evaluation_claim: str = (
        "frozen_stage2_planning_input_coverage_not_provider_generation_or_campaign_execution"
    )
    request: WorkbenchCurationReadinessRequest
    campaign_count: int = Field(ge=0)
    frozen_input_ready_count: int = Field(ge=0)
    bounded_planning_ready_count: int = Field(ge=0)
    rows: list[CurationReadinessRow] = Field(default_factory=list)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()

    def validate_hash(self) -> bool:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return (
            bool(self.content_sha256) and self.content_sha256 == hashlib.sha256(encoded).hexdigest()
        )


class RealizationWorkbench:
    """Load only frozen artifact inputs and expose bounded planning operations."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = artifact_root.resolve()
        self._plans_root = self._artifact_root / "release" / "plans"
        self._enterprise_root = self._plans_root / "enterprise"
        self._index_path = self._enterprise_root / "index.json"
        self._templates_path = (
            self._artifact_root / "data" / "concretization" / "action_templates.json"
        )
        self._fact_semantics_path = (
            self._artifact_root / "data" / "concretization" / "fact_semantics.json"
        )
        for required_path in (
            self._index_path,
            self._templates_path,
            self._fact_semantics_path,
        ):
            if not required_path.is_file():
                raise FileNotFoundError(f"required workbench input is absent: {required_path}")
        self._fact_semantics = self._load_fact_semantics()

    def campaign_inventory(self) -> CampaignInventory:
        campaign_index = self._load_campaign_index()
        campaigns = [self._availability(entry) for entry in campaign_index.campaigns]
        ready_count = sum(campaign.enumeration_ready for campaign in campaigns)
        semantic_conformant_count = sum(
            campaign.semantic_fact_status == "conformant" for campaign in campaigns
        )
        return CampaignInventory(
            campaign_count=campaign_index.campaign_count,
            compiled_count=campaign_index.compiled_count,
            enumeration_ready_count=ready_count,
            semantic_conformant_count=semantic_conformant_count,
            campaigns=campaigns,
        )

    def enumerate_campaign(
        self,
        request: WorkbenchEnumerationRequest,
    ) -> WorkbenchEnumerationResponse:
        campaign = self._campaign(request.campaign_id)
        if not campaign.enumeration_ready:
            raise ValueError(
                f"campaign {request.campaign_id} is not enumeration-ready: "
                f"{campaign.availability_reason}"
            )
        if campaign.plan_path is None or campaign.binding_catalog_path is None:
            raise ValueError("enumeration-ready campaign lacks a frozen input path")
        plan = ProceduralPlan.model_validate_json(
            self._artifact_path(campaign.plan_path).read_text(encoding="utf-8")
        )
        bindings = BindingCatalog.model_validate_json(
            self._artifact_path(campaign.binding_catalog_path).read_text(encoding="utf-8")
        )
        templates = self._load_templates()
        result = enumerate_realization_space(
            plan,
            bindings,
            templates,
            maximum_realizations=request.maximum_realizations,
            maximum_search_states=request.maximum_search_states,
            maximum_candidates_per_step=request.maximum_candidates_per_step,
        )
        generation_queue = build_template_generation_queue(
            plan,
            bindings,
            templates,
            desired_procedure_assignments_per_step=(request.desired_procedure_assignments_per_step),
            desired_behavior_contracts_per_step=(request.desired_behavior_contracts_per_step),
            maximum_targets=request.maximum_generation_targets,
            realization_space=result,
        )
        return WorkbenchEnumerationResponse(
            campaign=campaign,
            request=request,
            result=result,
            generation_queue=generation_queue,
        )

    def audit_curation_readiness(
        self,
        request: WorkbenchCurationReadinessRequest | None = None,
    ) -> CurationReadinessReport:
        """Audit every indexed campaign without calling a provider or executing it."""

        active_request = request or WorkbenchCurationReadinessRequest()
        inventory = self.campaign_inventory()
        rows: list[CurationReadinessRow] = []
        for campaign in inventory.campaigns:
            if campaign.corpus_status == "not_compiled":
                rows.append(
                    CurationReadinessRow(
                        campaign_id=campaign.campaign_id,
                        campaign_name=campaign.campaign_name,
                        corpus_status=campaign.corpus_status,
                        curation_status=CurationReadinessStatus.not_compiled,
                        reason=campaign.availability_reason,
                        semantic_fact_status=campaign.semantic_fact_status,
                        semantic_fact_audit_sha256=campaign.semantic_fact_audit_sha256,
                    )
                )
                continue
            if not campaign.enumeration_ready:
                status = (
                    CurationReadinessStatus.semantic_fact_audit_failed
                    if campaign.semantic_fact_status == "nonconformant"
                    else CurationReadinessStatus.binding_catalog_absent
                )
                rows.append(
                    CurationReadinessRow(
                        campaign_id=campaign.campaign_id,
                        campaign_name=campaign.campaign_name,
                        corpus_status=campaign.corpus_status,
                        curation_status=status,
                        reason=campaign.availability_reason,
                        semantic_fact_status=campaign.semantic_fact_status,
                        semantic_fact_audit_sha256=campaign.semantic_fact_audit_sha256,
                    )
                )
                continue

            response = self.enumerate_campaign(
                WorkbenchEnumerationRequest(
                    campaign_id=campaign.campaign_id,
                    maximum_realizations=active_request.maximum_realizations,
                    maximum_search_states=active_request.maximum_search_states,
                    maximum_candidates_per_step=active_request.maximum_candidates_per_step,
                    desired_procedure_assignments_per_step=(
                        active_request.desired_procedure_assignments_per_step
                    ),
                    desired_behavior_contracts_per_step=(
                        active_request.desired_behavior_contracts_per_step
                    ),
                    maximum_generation_targets=(active_request.maximum_generation_targets),
                )
            )
            result = response.result
            queue = response.generation_queue
            status = (
                CurationReadinessStatus.bounded_planning_ready
                if result.realization_count
                else CurationReadinessStatus.no_admissible_realization
            )
            rows.append(
                CurationReadinessRow(
                    campaign_id=campaign.campaign_id,
                    campaign_name=campaign.campaign_name,
                    corpus_status=campaign.corpus_status,
                    curation_status=status,
                    reason=(
                        "frozen inputs admit at least one bounded planning realization"
                        if result.realization_count
                        else "frozen inputs admit no complete bounded planning realization"
                    ),
                    source_plan_sha256=result.source_plan_sha256,
                    binding_catalog_sha256=result.binding_catalog_sha256,
                    semantic_fact_status=campaign.semantic_fact_status,
                    semantic_fact_audit_sha256=campaign.semantic_fact_audit_sha256,
                    realization_count=result.realization_count,
                    enumeration_status=result.enumeration_status.value,
                    total_procedure_assignment_deficit=(queue.total_procedure_assignment_deficit),
                    total_behavior_contract_deficit=(queue.total_behavior_contract_deficit),
                    selected_generation_target_count=queue.selected_target_count,
                    deferred_procedure_assignment_deficit=(
                        queue.unselected_procedure_assignment_deficit
                    ),
                    unconstructible_generation_need_count=sum(
                        need.requested_additional_procedure_assignment_count > 0
                        and not need.context_constructible
                        for need in queue.needs
                    ),
                )
            )
        report = CurationReadinessReport(
            request=active_request,
            campaign_count=len(rows),
            frozen_input_ready_count=inventory.enumeration_ready_count,
            bounded_planning_ready_count=sum(
                row.curation_status is CurationReadinessStatus.bounded_planning_ready
                for row in rows
            ),
            rows=rows,
        )
        report.finalize_hash()
        return report

    def _campaign(self, campaign_id: str) -> CampaignAvailability:
        inventory = self.campaign_inventory()
        matches = [item for item in inventory.campaigns if item.campaign_id == campaign_id]
        if not matches:
            raise ValueError(f"unknown campaign id: {campaign_id}")
        return matches[0]

    def _load_campaign_index(self) -> CampaignIndex:
        campaign_index = CampaignIndex.model_validate_json(
            self._index_path.read_text(encoding="utf-8")
        )
        if campaign_index.campaign_count != len(campaign_index.campaigns):
            raise ValueError("campaign index count does not match its rows")
        compiled_count = sum(entry.status == "compiled" for entry in campaign_index.campaigns)
        if campaign_index.compiled_count != compiled_count:
            raise ValueError("campaign index compiled count does not match its rows")
        if campaign_index.not_compiled_count != len(campaign_index.campaigns) - compiled_count:
            raise ValueError("campaign index not-compiled count does not match its rows")
        campaign_ids = [entry.campaign_id for entry in campaign_index.campaigns]
        if len(campaign_ids) != len(set(campaign_ids)):
            raise ValueError("campaign index identifiers must be unique")
        return campaign_index

    def _availability(self, entry: CampaignIndexEntry) -> CampaignAvailability:
        if entry.status == "not_compiled":
            return CampaignAvailability(
                campaign_id=entry.campaign_id,
                campaign_name=entry.campaign_name or entry.campaign_id,
                corpus_status=entry.status,
                enumeration_ready=False,
                availability_reason=entry.reason or "procedural plan is unavailable",
            )
        if entry.path is None or entry.step_count is None:
            raise ValueError(f"compiled campaign {entry.campaign_id} lacks plan metadata")
        corpus_plan = self._enterprise_root / entry.path
        selected_plan = self._plans_root / f"{entry.campaign_id}.procedural-plan.json"
        if not selected_plan.is_file():
            selected_plan = corpus_plan
        if selected_plan.is_file():
            self._validate_plan_metadata(entry, selected_plan)
        binding_catalog = self._plans_root / f"{entry.campaign_id}.binding-catalog.json"
        semantic_status: Literal["not_assessed", "conformant", "nonconformant"] = "not_assessed"
        semantic_audit_sha256: str | None = None
        ready = selected_plan.is_file() and binding_catalog.is_file()
        if ready:
            catalog = BindingCatalog.model_validate_json(
                binding_catalog.read_text(encoding="utf-8")
            )
            semantic_audit = audit_fact_semantics(
                self._fact_semantics,
                catalog,
                self._load_templates(),
            )
            semantic_status = "conformant" if semantic_audit.conformant else "nonconformant"
            semantic_audit_sha256 = semantic_audit.content_sha256
            ready = semantic_audit.conformant
        if not binding_catalog.is_file():
            reason = "binding catalog is absent from the evaluated deep slice"
        elif semantic_status == "nonconformant":
            reason = "binding catalog fails the versioned semantic fact audit"
        else:
            reason = "frozen plan, binding catalog, and semantic facts are conformant"
        return CampaignAvailability(
            campaign_id=entry.campaign_id,
            campaign_name=entry.campaign_name or entry.campaign_id,
            corpus_status=entry.status,
            step_count=entry.step_count,
            plan_path=self._relative_path(selected_plan) if selected_plan.is_file() else None,
            binding_catalog_path=(
                self._relative_path(binding_catalog) if binding_catalog.is_file() else None
            ),
            semantic_fact_status=semantic_status,
            semantic_fact_audit_sha256=semantic_audit_sha256,
            enumeration_ready=ready,
            availability_reason=reason,
        )

    def _validate_plan_metadata(self, entry: CampaignIndexEntry, path: Path) -> None:
        plan = ProceduralPlan.model_validate_json(path.read_text(encoding="utf-8"))
        if not plan.validate_hash():
            raise ValueError(f"campaign plan hash mismatch: {entry.campaign_id}")
        if entry.content_sha256 is None or plan.content_sha256 != entry.content_sha256:
            raise ValueError(f"campaign index hash mismatch: {entry.campaign_id}")
        if plan.campaign_id != entry.campaign_id:
            raise ValueError(f"campaign index identifier mismatch: {entry.campaign_id}")
        if len(plan.steps) != entry.step_count:
            raise ValueError(f"campaign index step count mismatch: {entry.campaign_id}")

    def _load_templates(self) -> list[ActionTemplate]:
        payload = json.loads(self._templates_path.read_text(encoding="utf-8"))
        raw_templates = payload.get("templates")
        if not isinstance(raw_templates, list):
            raise ValueError("action template catalog has no templates list")
        return [ActionTemplate.model_validate(item) for item in raw_templates]

    def _load_fact_semantics(self) -> FactSemanticsRegistry:
        registry = FactSemanticsRegistry.model_validate_json(
            self._fact_semantics_path.read_text(encoding="utf-8")
        )
        if not registry.validate_hash():
            raise ValueError("fact semantic registry hash mismatch")
        return registry

    def _relative_path(self, path: Path) -> str:
        resolved = path.resolve()
        if not resolved.is_relative_to(self._artifact_root):
            raise ValueError("workbench input resolves outside the artifact")
        return resolved.relative_to(self._artifact_root).as_posix()

    def _artifact_path(self, relative_path: str) -> Path:
        path = (self._artifact_root / relative_path).resolve()
        if not path.is_relative_to(self._artifact_root):
            raise ValueError("workbench input resolves outside the artifact")
        if not path.is_file():
            raise FileNotFoundError(f"workbench input is absent: {relative_path}")
        return path
