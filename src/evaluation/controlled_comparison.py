"""Contracts and integrity checks for controlled procedural comparisons."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from itertools import product
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from concretization.models import ActionTemplate, BindingCatalog, ProcedureProposal
from concretization.pipeline import action_catalog_hash
from concretization.verifier import assess_candidate

SHA256_PATTERN = r"^[0-9a-f]{64}$"
GIT_REVISION_PATTERN = r"^[0-9a-f]{40}$"
COMPARABLE_ARMS = {
    "prior_work_style",
    "sticks_without_admission",
    "sticks_admitted",
}
REQUIRED_ARMS = COMPARABLE_ARMS | {"sticks_autosut_executed"}


def canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArmId(str, Enum):
    prior_work_style = "prior_work_style"
    sticks_without_admission = "sticks_without_admission"
    sticks_admitted = "sticks_admitted"
    sticks_autosut_executed = "sticks_autosut_executed"


class RunStatus(str, Enum):
    planned = "planned"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    unsupported = "unsupported"


class EvidenceRole(str, Enum):
    generic = "generic"
    admitted_plan = "admitted_plan"
    execution_semantic_bridge = "execution_semantic_bridge"
    execution_handoff = "execution_handoff"
    consumer_receipt = "consumer_receipt"
    independent_observation = "independent_observation"


class EvidenceReference(StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    role: EvidenceRole = EvidenceRole.generic

    @model_validator(mode="after")
    def validate_relative_path(self) -> "EvidenceReference":
        candidate = Path(self.path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("evidence path must be relative and cannot traverse parents")
        return self

    def validate_file(self, root: Path) -> None:
        evidence_path = root / self.path
        if not evidence_path.is_file():
            raise FileNotFoundError(f"missing run evidence: {evidence_path}")
        observed = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
        if observed != self.sha256:
            raise ValueError(f"run evidence hash mismatch: {self.path}")


class GeneratorBudget(StrictModel):
    model_id: str = Field(min_length=1)
    model_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    runtime_id: str = Field(min_length=1)
    prompt_template_sha256: str = Field(pattern=SHA256_PATTERN)
    temperature: float = Field(ge=0.0)
    top_p: float = Field(gt=0.0, le=1.0)
    max_output_tokens: int = Field(gt=0)
    max_proposal_calls_per_step: int = Field(gt=0)
    max_retries_per_step: int = Field(ge=0)
    timeout_seconds_per_step: int = Field(gt=0)

    def comparison_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class ArmDefinition(StrictModel):
    arm_id: ArmId
    proposal_budget: GeneratorBudget | None = None
    consumes_arm: ArmId | None = None

    @model_validator(mode="after")
    def validate_execution_boundary(self) -> "ArmDefinition":
        if self.arm_id == ArmId.sticks_autosut_executed:
            if self.proposal_budget is not None:
                raise ValueError("execution arm cannot introduce a proposal budget")
            if self.consumes_arm != ArmId.sticks_admitted:
                raise ValueError("execution arm must consume sticks_admitted output")
            return self
        if self.proposal_budget is None:
            raise ValueError(f"{self.arm_id.value} requires a proposal budget")
        if self.consumes_arm is not None:
            raise ValueError(f"{self.arm_id.value} cannot consume another arm")
        return self


class ControlledComparisonManifest(StrictModel):
    schema_version: str = "1"
    experiment_id: str = Field(min_length=1)
    protocol_sha256: str = Field(pattern=SHA256_PATTERN)
    campaigns: list[str] = Field(min_length=1)
    seeds: list[int] = Field(min_length=1)
    arms: list[ArmDefinition] = Field(min_length=1)
    oracle_revision: str = Field(pattern=SHA256_PATTERN)
    action_catalog_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_unique_dimensions(self) -> "ControlledComparisonManifest":
        if len(self.campaigns) != len(set(self.campaigns)):
            raise ValueError("campaigns must be unique")
        if len(self.seeds) != len(set(self.seeds)):
            raise ValueError("seeds must be unique")
        arm_ids = [arm.arm_id for arm in self.arms]
        if len(arm_ids) != len(set(arm_ids)):
            raise ValueError("arm identifiers must be unique")
        return self

    def validate_collection_ready(self, *, minimum_seeds: int = 5) -> None:
        arm_index = {arm.arm_id.value: arm for arm in self.arms}
        missing_arms = sorted(REQUIRED_ARMS - arm_index.keys())
        if missing_arms:
            raise ValueError(f"missing required arms: {', '.join(missing_arms)}")
        if len(self.seeds) < minimum_seeds:
            raise ValueError(f"at least {minimum_seeds} unique seeds are required")
        budget_hashes = {
            arm_index[arm_id].proposal_budget.comparison_sha256()  # type: ignore[union-attr]
            for arm_id in COMPARABLE_ARMS
        }
        if len(budget_hashes) != 1:
            raise ValueError("comparable arms must use identical proposal budgets")

    def planned_run_keys(self) -> set[tuple[str, str, int]]:
        return {
            (campaign_id, arm.arm_id.value, seed)
            for campaign_id, arm, seed in product(self.campaigns, self.arms, self.seeds)
        }


class RunRecord(StrictModel):
    campaign_id: str = Field(min_length=1)
    arm_id: ArmId
    seed: int
    status: RunStatus
    started_at: str | None = None
    finished_at: str | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)
    failure_code: str | None = None
    failure_detail: str | None = None
    unsupported_reason: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> "RunRecord":
        if self.status == RunStatus.succeeded:
            if not self.evidence:
                raise ValueError("successful run requires evidence references")
            if self.failure_code or self.failure_detail or self.unsupported_reason:
                raise ValueError("successful run cannot contain failure metadata")
            roles = [reference.role for reference in self.evidence]
            execution_roles = {
                EvidenceRole.admitted_plan,
                EvidenceRole.execution_semantic_bridge,
                EvidenceRole.execution_handoff,
                EvidenceRole.consumer_receipt,
                EvidenceRole.independent_observation,
            }
            if self.arm_id == ArmId.sticks_autosut_executed:
                if len(roles) != len(execution_roles) or set(roles) != execution_roles:
                    raise ValueError(
                        "successful execution arm requires exactly one admitted plan, "
                        "semantic bridge, handoff, consumer receipt, and independent observation"
                    )
            elif any(role != EvidenceRole.generic for role in roles):
                raise ValueError("proposal-arm evidence cannot use execution evidence roles")
        elif self.status == RunStatus.failed:
            if not self.failure_code or not self.failure_detail:
                raise ValueError("failed run requires failure_code and failure_detail")
            if self.unsupported_reason:
                raise ValueError("failed run cannot contain unsupported_reason")
        elif self.status == RunStatus.unsupported:
            if not self.unsupported_reason:
                raise ValueError("unsupported run requires unsupported_reason")
            if self.failure_code or self.failure_detail:
                raise ValueError("unsupported run cannot contain failure metadata")
        elif self.evidence or self.failure_code or self.failure_detail or self.unsupported_reason:
            raise ValueError(f"{self.status.value} run cannot contain terminal metadata")
        return self

    def key(self) -> tuple[str, str, int]:
        return self.campaign_id, self.arm_id.value, self.seed


class RunLedger(StrictModel):
    schema_version: str = "1"
    experiment_id: str = Field(min_length=1)
    records: list[RunRecord]

    def validate_against(self, manifest: ControlledComparisonManifest) -> None:
        if self.experiment_id != manifest.experiment_id:
            raise ValueError("ledger experiment_id does not match manifest")
        observed = [record.key() for record in self.records]
        if len(observed) != len(set(observed)):
            raise ValueError("ledger contains duplicate run keys")
        expected = manifest.planned_run_keys()
        missing = sorted(expected - set(observed))
        unexpected = sorted(set(observed) - expected)
        if missing or unexpected:
            raise ValueError(f"run accounting mismatch: missing={missing}, unexpected={unexpected}")

    def validate_evidence(self, root: Path) -> None:
        for record in self.records:
            for reference in record.evidence:
                reference.validate_file(root)

    def validate_execution_evidence(self, root: Path) -> None:
        for record in self.records:
            if (
                record.arm_id != ArmId.sticks_autosut_executed
                or record.status != RunStatus.succeeded
            ):
                continue
            references = {reference.role: reference for reference in record.evidence}
            plan = AdmittedCampaignPlan.model_validate_json(
                (root / references[EvidenceRole.admitted_plan].path).read_text(
                    encoding="utf-8"
                )
            )
            bridge = ExecutionSemanticBridge.model_validate_json(
                (root / references[EvidenceRole.execution_semantic_bridge].path).read_text(
                    encoding="utf-8"
                )
            )
            handoff = ExecutionHandoff.model_validate_json(
                (root / references[EvidenceRole.execution_handoff].path).read_text(
                    encoding="utf-8"
                )
            )
            receipt = ConsumerExecutionReceipt.model_validate_json(
                (root / references[EvidenceRole.consumer_receipt].path).read_text(
                    encoding="utf-8"
                )
            )
            observation = IndependentEffectObservation.model_validate_json(
                (root / references[EvidenceRole.independent_observation].path).read_text(
                    encoding="utf-8"
                )
            )
            if not plan.validate_hash():
                raise ValueError("admitted plan content hash mismatch")
            if not bridge.validate_hash():
                raise ValueError("execution semantic bridge content hash mismatch")
            if not handoff.validate_hash():
                raise ValueError("execution handoff content hash mismatch")
            if not receipt.validate_hash():
                raise ValueError("consumer receipt content hash mismatch")
            if not observation.validate_hash():
                raise ValueError("independent observation content hash mismatch")
            expected_key = (record.campaign_id, record.seed)
            for evidence_name, evidence_key in (
                ("admitted plan", (plan.campaign_id, plan.seed)),
                ("execution semantic bridge", (bridge.campaign_id, bridge.seed)),
                ("execution handoff", (handoff.campaign_id, handoff.seed)),
                ("consumer receipt", (receipt.campaign_id, receipt.seed)),
                (
                    "independent observation",
                    (observation.campaign_id, observation.seed),
                ),
            ):
                if evidence_key != expected_key:
                    raise ValueError(f"{evidence_name} does not match its run record")
            if any(
                experiment_id != self.experiment_id
                for experiment_id in (
                    plan.experiment_id,
                    bridge.experiment_id,
                    handoff.experiment_id,
                    receipt.experiment_id,
                    observation.experiment_id,
                )
            ):
                raise ValueError("execution evidence experiment_id does not match ledger")
            if handoff.admitted_plan_sha256 != plan.content_sha256:
                raise ValueError("execution handoff is not bound to the admitted plan")
            if bridge.admitted_plan_sha256 != plan.content_sha256:
                raise ValueError("execution semantic bridge is not bound to the admitted plan")
            if handoff.execution_semantic_sha256 != bridge.content_sha256:
                raise ValueError("execution handoff is not bound to the semantic bridge")
            if receipt.handoff_sha256 != handoff.content_sha256:
                raise ValueError("consumer receipt is not bound to the execution handoff")
            if observation.handoff_sha256 != handoff.content_sha256:
                raise ValueError("independent observation is not bound to the execution handoff")
            if receipt.consumer_revision != handoff.consumer_revision:
                raise ValueError("consumer receipt revision does not match handoff")


class BlindOracleInput(StrictModel):
    schema_version: str = "1"
    blind_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    technique_id: str = Field(min_length=1)
    execution_domain: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    bindings: dict[str, str] = Field(default_factory=dict)
    known_facts: list[str] = Field(default_factory=list)
    source_record_sha256: str = Field(pattern=SHA256_PATTERN)

    def content_sha256(self) -> str:
        return canonical_sha256(self.model_dump(mode="json"))


class BlindAssignment(StrictModel):
    blind_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    arm_id: ArmId
    seed: int
    proposal_record_sha256: str = Field(pattern=SHA256_PATTERN)


class NeutralProposalRecord(StrictModel):
    """Common adapter output retained outside the arm-blind oracle boundary."""

    schema_version: str = "1"
    proposal_id: str = Field(min_length=1)
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    arm_id: ArmId
    seed: int
    technique_id: str = Field(min_length=1)
    execution_domain: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    bindings: dict[str, str] = Field(default_factory=dict)
    known_facts: list[str] = Field(default_factory=list)
    proposal_budget_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_output_sha256: str = Field(pattern=SHA256_PATTERN)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        self.content_sha256 = canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        expected = self.content_sha256
        self.finalize_hash()
        return bool(expected) and self.content_sha256 == expected

    def blind(self, blind_id: str) -> tuple[BlindOracleInput, BlindAssignment]:
        if not self.validate_hash():
            raise ValueError("proposal record hash mismatch")
        oracle_input = BlindOracleInput(
            blind_id=blind_id,
            campaign_id=self.campaign_id,
            step_id=self.step_id,
            technique_id=self.technique_id,
            execution_domain=self.execution_domain,
            template_id=self.template_id,
            bindings=self.bindings,
            known_facts=self.known_facts,
            source_record_sha256=self.content_sha256,
        )
        assignment = BlindAssignment(
            blind_id=blind_id,
            experiment_id=self.experiment_id,
            campaign_id=self.campaign_id,
            step_id=self.step_id,
            arm_id=self.arm_id,
            seed=self.seed,
            proposal_record_sha256=self.content_sha256,
        )
        return oracle_input, assignment


def validate_proposal_record(
    record: NeutralProposalRecord,
    manifest: ControlledComparisonManifest,
) -> None:
    if not record.validate_hash():
        raise ValueError("proposal record hash mismatch")
    if record.experiment_id != manifest.experiment_id:
        raise ValueError("proposal experiment_id does not match manifest")
    if record.campaign_id not in manifest.campaigns:
        raise ValueError("proposal campaign is outside the manifest")
    if record.seed not in manifest.seeds:
        raise ValueError("proposal seed is outside the manifest")
    arm_index = {arm.arm_id: arm for arm in manifest.arms}
    arm = arm_index.get(record.arm_id)
    if arm is None or arm.proposal_budget is None:
        raise ValueError("proposal arm does not generate proposals")
    if record.proposal_budget_sha256 != arm.proposal_budget.comparison_sha256():
        raise ValueError("proposal budget hash does not match the frozen arm budget")


class AdmittedCampaignPlan(StrictModel):
    """Exact admitted proposal sequence consumed by the execution arm."""

    schema_version: str = "1"
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    seed: int
    collection_lock_sha256: str = Field(pattern=SHA256_PATTERN)
    proposals: list[NeutralProposalRecord] = Field(min_length=1)
    content_sha256: str = ""

    @model_validator(mode="after")
    def validate_admitted_sequence(self) -> "AdmittedCampaignPlan":
        step_ids = []
        for proposal in self.proposals:
            if not proposal.validate_hash():
                raise ValueError("admitted proposal record hash mismatch")
            if proposal.arm_id != ArmId.sticks_admitted:
                raise ValueError("execution plan can contain only admitted-arm proposals")
            if (
                proposal.experiment_id != self.experiment_id
                or proposal.campaign_id != self.campaign_id
                or proposal.seed != self.seed
            ):
                raise ValueError("admitted proposal identity differs from execution plan")
            step_ids.append(proposal.step_id)
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("execution plan contains duplicate step identifiers")
        return self

    def finalize_hash(self) -> None:
        self.content_sha256 = canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        expected = self.content_sha256
        self.finalize_hash()
        return bool(expected) and self.content_sha256 == expected


class ExecutionBridgeStep(StrictModel):
    step_id: str = Field(min_length=1)
    occurrence: int = Field(gt=0)
    proposal_sha256: str = Field(pattern=SHA256_PATTERN)
    technique_id: str = Field(min_length=1)
    template_id: str = Field(min_length=1)
    bindings_sha256: str = Field(pattern=SHA256_PATTERN)
    executor_id: str = Field(min_length=1)
    executor_sha256: str = Field(pattern=SHA256_PATTERN)


class ExecutionSemanticBridge(StrictModel):
    """Exact equality proof from an admitted plan to reviewed runtime bindings."""

    schema_version: str = "1"
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    runtime_campaign_id: str = Field(min_length=1)
    seed: int
    admitted_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    concretized_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    runtime_contract_sha256: str = Field(pattern=SHA256_PATTERN)
    steps: list[ExecutionBridgeStep] = Field(min_length=1)
    content_sha256: str = ""

    @model_validator(mode="after")
    def validate_unique_steps(self) -> "ExecutionSemanticBridge":
        step_ids = [step.step_id for step in self.steps]
        occurrences = [step.occurrence for step in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("semantic bridge contains duplicate step identifiers")
        if len(occurrences) != len(set(occurrences)):
            raise ValueError("semantic bridge contains duplicate occurrences")
        return self

    def finalize_hash(self) -> None:
        self.content_sha256 = canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        expected = self.content_sha256
        self.finalize_hash()
        return bool(expected) and self.content_sha256 == expected


class OracleDecision(StrictModel):
    schema_version: str = "1"
    blind_id: str
    accepted: bool
    issue_codes: list[str]
    assumption_count: int = Field(ge=0)
    oracle_revision: str = Field(pattern=SHA256_PATTERN)
    oracle_input_sha256: str = Field(pattern=SHA256_PATTERN)
    binding_catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    action_catalog_sha256: str = Field(pattern=SHA256_PATTERN)


def evaluate_blind_proposal(
    oracle_input: BlindOracleInput,
    *,
    templates: list[ActionTemplate],
    catalog: BindingCatalog,
    oracle_revision: str,
) -> OracleDecision:
    if not catalog.validate_hash():
        raise ValueError("binding catalog hash mismatch")
    proposal = ProcedureProposal(
        technique_id=oracle_input.technique_id,
        template_id=oracle_input.template_id,
        bindings=oracle_input.bindings,
        source="blinded_comparison",
    )
    assessment = assess_candidate(
        proposal,
        technique_id=oracle_input.technique_id,
        execution_domain=oracle_input.execution_domain,
        templates={template.template_id: template for template in templates},
        catalog=catalog,
        known_facts=set(oracle_input.known_facts),
    )
    return OracleDecision(
        blind_id=oracle_input.blind_id,
        accepted=assessment.accepted,
        issue_codes=[issue.code for issue in assessment.issues],
        assumption_count=assessment.assumption_count,
        oracle_revision=oracle_revision,
        oracle_input_sha256=oracle_input.content_sha256(),
        binding_catalog_sha256=catalog.content_sha256,
        action_catalog_sha256=action_catalog_hash(templates),
    )


class ExecutionHandoff(StrictModel):
    schema_version: str = "1"
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    seed: int
    producer: str = "sticks"
    producer_revision: str = Field(pattern=GIT_REVISION_PATTERN)
    consumer: str = Field(min_length=1)
    consumer_revision: str = Field(pattern=GIT_REVISION_PATTERN)
    contract: str = "execution_handoff.v1"
    admitted_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    procedural_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    binding_catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    action_catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    execution_semantic_sha256: str = Field(pattern=SHA256_PATTERN)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        self.content_sha256 = canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        expected = self.content_sha256
        self.finalize_hash()
        return bool(expected) and self.content_sha256 == expected


class EffectClass(str, Enum):
    target_observed = "target_observed"
    controller_observed = "controller_observed"
    simulated = "simulated"
    failed = "failed"


class StepEffectObservation(StrictModel):
    step_id: str = Field(min_length=1)
    effect_class: EffectClass
    predicate_id: str = Field(min_length=1)
    raw_evidence_sha256: str = Field(pattern=SHA256_PATTERN)


class IndependentEffectObservation(StrictModel):
    schema_version: str = "1"
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    seed: int
    handoff_sha256: str = Field(pattern=SHA256_PATTERN)
    admission_oracle_revision: str = Field(pattern=SHA256_PATTERN)
    observer_revision: str = Field(pattern=SHA256_PATTERN)
    effects: list[StepEffectObservation] = Field(min_length=1)
    content_sha256: str = ""

    @model_validator(mode="after")
    def validate_independent_authority(self) -> "IndependentEffectObservation":
        if self.observer_revision == self.admission_oracle_revision:
            raise ValueError("effect observer must be independent of the admission oracle")
        step_ids = [effect.step_id for effect in self.effects]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError("effect observations must have unique step identifiers")
        return self

    def finalize_hash(self) -> None:
        self.content_sha256 = canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        expected = self.content_sha256
        self.finalize_hash()
        return bool(expected) and self.content_sha256 == expected


class ConsumerExecutionReceipt(StrictModel):
    schema_version: str = "1"
    experiment_id: str = Field(min_length=1)
    campaign_id: str = Field(min_length=1)
    seed: int
    handoff_sha256: str = Field(pattern=SHA256_PATTERN)
    consumer_revision: str = Field(pattern=GIT_REVISION_PATTERN)
    raw_execution_sha256: str = Field(pattern=SHA256_PATTERN)
    status: RunStatus
    content_sha256: str = ""

    @model_validator(mode="after")
    def validate_success(self) -> "ConsumerExecutionReceipt":
        if self.status != RunStatus.succeeded:
            raise ValueError("successful execution run requires a successful consumer receipt")
        return self

    def finalize_hash(self) -> None:
        self.content_sha256 = canonical_sha256(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        expected = self.content_sha256
        self.finalize_hash()
        return bool(expected) and self.content_sha256 == expected
