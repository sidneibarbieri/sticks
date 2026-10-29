"""Admit proposed templates without silently promoting unimplemented semantics."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from enum import Enum
from pathlib import Path

from pydantic import Field

from .models import ActionTemplate, StrictModel, VerificationIssue
from .pipeline import action_catalog_hash
from .template_generation import CandidateContextBinding
from .template_admission import (
    TemplateAdmission,
    admit_template,
    build_admission_vocabulary,
)
from .template_proposer import context_admission_issues, trusted_behavior_contract


class PromotionStatus(str, Enum):
    rejected = "rejected"
    planning_only = "planning_only"
    implementation_bound = "implementation_bound"


class TemplateImplementationWitness(StrictModel):
    template_id: str
    executor_id: str
    implementation_path: str
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    supported_parameter_kinds: list[str] = Field(default_factory=list)
    evidence_predicates: list[str] = Field(min_length=1)
    lab_only: bool = True


class TemplateOverlayDecision(StrictModel):
    candidate_index: int = Field(ge=0)
    template: ActionTemplate
    schema_admission: TemplateAdmission
    promotion_status: PromotionStatus
    promotion_issues: list[VerificationIssue] = Field(default_factory=list)
    candidate_context_binding: CandidateContextBinding | None = None
    implementation_witness: TemplateImplementationWitness | None = None


class TemplateOverlay(StrictModel):
    schema_version: str = "1"
    base_action_catalog_sha256: str
    candidate_source_sha256: str
    context_binding_source_sha256: str
    witness_source_sha256: str
    witness_guarantee: str = "file_integrity_and_declared_interface_only"
    decisions: list[TemplateOverlayDecision] = Field(default_factory=list)
    implementation_bound_templates: list[ActionTemplate] = Field(default_factory=list)
    rejected_count: int = Field(ge=0)
    planning_only_count: int = Field(ge=0)
    implementation_bound_count: int = Field(ge=0)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        self.content_sha256 = _canonical_hash(payload)


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _catalog_hash(templates: list[ActionTemplate]) -> str:
    return action_catalog_hash(sorted(templates, key=lambda item: item.template_id))


def _source_hash(models: Sequence[StrictModel]) -> str:
    return _canonical_hash([model.model_dump(mode="json") for model in models])


def _collision_issues(
    candidate: ActionTemplate,
    *,
    base_template_ids: set[str],
    duplicate_candidate_ids: set[str],
) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    if candidate.template_id in base_template_ids:
        issues.append(
            VerificationIssue(
                code="base_template_id_collision",
                message=f"template id {candidate.template_id!r} already exists in the base catalog",
            )
        )
    if candidate.template_id in duplicate_candidate_ids:
        issues.append(
            VerificationIssue(
                code="duplicate_candidate_template_id",
                message=f"template id {candidate.template_id!r} occurs more than once",
            )
        )
    return issues


def _contract_signature(template: ActionTemplate) -> str:
    return json.dumps(
        trusted_behavior_contract(template).model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


def _context_binding_issues(
    candidate: ActionTemplate,
    binding: CandidateContextBinding | None,
    base_templates: list[ActionTemplate],
) -> list[VerificationIssue]:
    if binding is None:
        return [
            VerificationIssue(
                code="missing_candidate_context_binding",
                message="candidate has no hash-pinned proposal context",
            )
        ]
    if not binding.context.validate_hash():
        return [
            VerificationIssue(
                code="candidate_context_hash_mismatch",
                message="candidate proposal context hash does not validate",
            )
        ]
    issues = context_admission_issues(candidate, binding.context)
    if candidate.technique_ids != [binding.technique_id]:
        issues.append(
            VerificationIssue(
                code="candidate_context_technique_mismatch",
                message="candidate technique does not match its proposal context binding",
            )
        )
    trusted_contracts = {
        _contract_signature(template)
        for template in base_templates
        if binding.technique_id in template.technique_ids
        and template.execution_domain == binding.context.execution_domain
    }
    if not trusted_contracts:
        issues.append(
            VerificationIssue(
                code="base_contract_missing",
                message="base catalog has no trusted behavior contract for the bound source step",
            )
        )
        return issues
    context_contracts = {
        json.dumps(
            contract.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        )
        for contract in binding.context.admissible_behavior_contracts
    }
    if not context_contracts.issubset(trusted_contracts):
        issues.append(
            VerificationIssue(
                code="context_contract_not_in_base_catalog",
                message=(
                    "proposal context contains a behavior contract absent from the "
                    "base catalog"
                ),
            )
        )
    if _contract_signature(candidate) not in trusted_contracts:
        issues.append(
            VerificationIssue(
                code="candidate_contract_not_in_base_catalog",
                message="candidate behavior contract is absent from the base catalog",
            )
        )
    return issues


def _witness_issues(
    template: ActionTemplate,
    witness: TemplateImplementationWitness,
    artifact_root: Path,
) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    relative_path = Path(witness.implementation_path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return [
            VerificationIssue(
                code="implementation_path_outside_artifact",
                message=(
                    "implementation witness path must be relative and remain inside " "the artifact"
                ),
            )
        ]
    resolved_root = artifact_root.resolve()
    implementation_path = (resolved_root / relative_path).resolve()
    if not implementation_path.is_relative_to(resolved_root):
        return [
            VerificationIssue(
                code="implementation_path_outside_artifact",
                message="implementation witness resolves outside the artifact",
            )
        ]
    if not implementation_path.is_file():
        issues.append(
            VerificationIssue(
                code="implementation_file_missing",
                message=f"implementation witness file is absent: {relative_path.as_posix()}",
            )
        )
    elif (
        hashlib.sha256(implementation_path.read_bytes()).hexdigest()
        != witness.implementation_sha256
    ):
        issues.append(
            VerificationIssue(
                code="implementation_hash_mismatch",
                message=f"implementation witness hash does not match {relative_path.as_posix()}",
            )
        )
    if not witness.lab_only:
        issues.append(
            VerificationIssue(
                code="implementation_not_lab_only",
                message="implementation witness is not restricted to the laboratory",
            )
        )
    missing_kinds = sorted(
        set(template.parameter_kinds.values()) - set(witness.supported_parameter_kinds)
    )
    if missing_kinds:
        issues.append(
            VerificationIssue(
                code="unsupported_witness_parameter_kind",
                message="implementation witness lacks parameter kinds: " + ", ".join(missing_kinds),
            )
        )
    missing_predicates = sorted(
        set(template.evidence_predicates) - set(witness.evidence_predicates)
    )
    if missing_predicates:
        issues.append(
            VerificationIssue(
                code="unsupported_witness_evidence_predicate",
                message="implementation witness lacks evidence predicates: "
                + ", ".join(missing_predicates),
            )
        )
    return issues


def build_template_overlay(
    base_templates: list[ActionTemplate],
    candidate_templates: list[ActionTemplate],
    candidate_context_bindings: list[CandidateContextBinding],
    implementation_witnesses: list[TemplateImplementationWitness],
    *,
    artifact_root: Path,
) -> TemplateOverlay:
    """Classify candidate templates and promote only integrity-bound implementations."""

    base_ids = [template.template_id for template in base_templates]
    if len(base_ids) != len(set(base_ids)):
        raise ValueError("base action template identifiers must be unique")
    witness_ids = [witness.template_id for witness in implementation_witnesses]
    duplicate_witnesses = sorted(
        template_id for template_id, count in Counter(witness_ids).items() if count > 1
    )
    if duplicate_witnesses:
        raise ValueError("duplicate implementation witnesses: " + ", ".join(duplicate_witnesses))
    witness_index = {witness.template_id: witness for witness in implementation_witnesses}
    context_ids = [binding.candidate_template_id for binding in candidate_context_bindings]
    duplicate_context_ids = sorted(
        template_id for template_id, count in Counter(context_ids).items() if count > 1
    )
    if duplicate_context_ids:
        raise ValueError(
            "duplicate candidate context bindings: " + ", ".join(duplicate_context_ids)
        )
    candidate_ids = [template.template_id for template in candidate_templates]
    unknown_context_ids = sorted(set(context_ids) - set(candidate_ids))
    if unknown_context_ids:
        raise ValueError(
            "candidate context bindings target unknown templates: "
            + ", ".join(unknown_context_ids)
        )
    context_index = {
        binding.candidate_template_id: binding for binding in candidate_context_bindings
    }
    duplicate_candidate_ids = {
        template_id
        for template_id, count in Counter(
            template.template_id for template in candidate_templates
        ).items()
        if count > 1
    }
    vocabulary = build_admission_vocabulary(base_templates)
    decisions: list[TemplateOverlayDecision] = []
    for candidate_index, candidate in enumerate(candidate_templates):
        schema_admission = admit_template(candidate, vocabulary)
        promotion_issues = _collision_issues(
            candidate,
            base_template_ids=set(base_ids),
            duplicate_candidate_ids=duplicate_candidate_ids,
        )
        context_binding = context_index.get(candidate.template_id)
        promotion_issues.extend(
            _context_binding_issues(candidate, context_binding, base_templates)
        )
        witness = witness_index.get(candidate.template_id)
        if not schema_admission.admitted or promotion_issues:
            status = PromotionStatus.rejected
        elif witness is None:
            status = PromotionStatus.planning_only
            promotion_issues.append(
                VerificationIssue(
                    code="missing_implementation_witness",
                    message="schema-admitted template has no implementation witness",
                )
            )
        else:
            promotion_issues.extend(_witness_issues(candidate, witness, artifact_root))
            status = (
                PromotionStatus.planning_only
                if promotion_issues
                else PromotionStatus.implementation_bound
            )
        decisions.append(
            TemplateOverlayDecision(
                candidate_index=candidate_index,
                template=candidate,
                schema_admission=schema_admission,
                promotion_status=status,
                promotion_issues=promotion_issues,
                candidate_context_binding=context_binding,
                implementation_witness=witness,
            )
        )
    eligible = sorted(
        (
            decision.template
            for decision in decisions
            if decision.promotion_status is PromotionStatus.implementation_bound
        ),
        key=lambda template: template.template_id,
    )
    counts = Counter(decision.promotion_status for decision in decisions)
    result = TemplateOverlay(
        base_action_catalog_sha256=_catalog_hash(base_templates),
        candidate_source_sha256=_source_hash(candidate_templates),
        context_binding_source_sha256=_source_hash(candidate_context_bindings),
        witness_source_sha256=_source_hash(implementation_witnesses),
        decisions=decisions,
        implementation_bound_templates=eligible,
        rejected_count=counts[PromotionStatus.rejected],
        planning_only_count=counts[PromotionStatus.planning_only],
        implementation_bound_count=counts[PromotionStatus.implementation_bound],
    )
    result.finalize_hash()
    return result


def load_template_overlay(
    path: Path,
    base_templates: list[ActionTemplate],
) -> TemplateOverlay:
    payload = json.loads(path.read_text(encoding="utf-8"))
    expected = str(payload.get("content_sha256", ""))
    actual = _canonical_hash(
        {key: value for key, value in payload.items() if key != "content_sha256"}
    )
    if not expected or actual != expected:
        raise ValueError("template overlay hash mismatch")
    overlay = TemplateOverlay.model_validate(payload)
    if overlay.base_action_catalog_sha256 != _catalog_hash(base_templates):
        raise ValueError("template overlay targets another base action catalog")
    candidate_templates = [decision.template for decision in overlay.decisions]
    if overlay.candidate_source_sha256 != _source_hash(candidate_templates):
        raise ValueError("template overlay candidates do not match its decisions")
    context_bindings: list[CandidateContextBinding] = []
    for decision in overlay.decisions:
        if decision.candidate_context_binding is None:
            raise ValueError("template overlay decision lacks a candidate context binding")
        context_bindings.append(decision.candidate_context_binding)
    if overlay.context_binding_source_sha256 != _source_hash(context_bindings):
        raise ValueError("template overlay context bindings do not match its decisions")
    base_ids = {template.template_id for template in base_templates}
    duplicate_candidate_ids = {
        template_id
        for template_id, count in Counter(
            template.template_id for template in candidate_templates
        ).items()
        if count > 1
    }
    vocabulary = build_admission_vocabulary(base_templates)
    for candidate_index, decision in enumerate(overlay.decisions):
        if decision.candidate_index != candidate_index:
            raise ValueError("template overlay candidate indexes are not contiguous")
        expected_admission = admit_template(decision.template, vocabulary)
        if decision.schema_admission != expected_admission:
            raise ValueError("template overlay schema admission does not match its candidate")
        required_issues = [
            *_collision_issues(
                decision.template,
                base_template_ids=base_ids,
                duplicate_candidate_ids=duplicate_candidate_ids,
            ),
            *_context_binding_issues(
                decision.template,
                decision.candidate_context_binding,
                base_templates,
            ),
        ]
        if required_issues and decision.promotion_status is not PromotionStatus.rejected:
            raise ValueError("template overlay promotes a candidate with invalid provenance")
    bound_from_decisions = sorted(
        (
            decision.template
            for decision in overlay.decisions
            if decision.promotion_status is PromotionStatus.implementation_bound
        ),
        key=lambda template: template.template_id,
    )
    if overlay.implementation_bound_templates != bound_from_decisions:
        raise ValueError("template overlay bound set does not match its decisions")
    if overlay.implementation_bound_count != len(bound_from_decisions):
        raise ValueError("template overlay bound count does not match its decisions")
    status_counts = Counter(decision.promotion_status for decision in overlay.decisions)
    expected_counts = {
        PromotionStatus.rejected: overlay.rejected_count,
        PromotionStatus.planning_only: overlay.planning_only_count,
        PromotionStatus.implementation_bound: overlay.implementation_bound_count,
    }
    if any(status_counts[status] != count for status, count in expected_counts.items()):
        raise ValueError("template overlay status counts do not match its decisions")
    return overlay
