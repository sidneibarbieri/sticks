"""Propose abstract procedure variants under trusted behavior contracts.

The proposer is a replaceable source of metadata for a known technique and behavior contract. It
never decides admission or extends the trusted behavior vocabulary itself.

The language model is injected as a ``complete`` callable, so this module has no dependency on
any particular provider and is exercised in tests without a live model. The generation script
supplies a real provider (local or hosted) and owns budget accounting and caching.
"""

from __future__ import annotations

import hashlib
import json
from typing import Callable, Sequence

from pydantic import Field, ValidationError

from .models import ActionTemplate, StrictModel, VerificationIssue
from .template_admission import (
    AdmissionVocabulary,
    TemplateAdmission,
    admit_template,
)

# A completion callable maps (system_prompt, user_prompt) to the model's raw text response.
CompletionFn = Callable[[str, str], str]

SYSTEM_PROMPT = """You extend a finite catalog of safe laboratory action templates.
For one MITRE ATT&CK technique, return one JSON object describing an abstract action template.
The template is metadata only: it never contains shell commands, code, URLs, or concrete
parameters.

Return exactly this shape:
{
  "template_id": string,            // kebab-case, describes the abstract action
  "technique_ids": [string],        // MITRE ids, e.g. "T1021.006"
  "execution_domain": string,       // one of the allowed domains
  "parameter_kinds": {string:string}, // values must be allowed kinds
  "requires": [string],             // precondition facts, each in an allowed namespace
  "produces": [string],             // effect facts, each in an allowed namespace; at least one new
  "evidence_predicates": [string],  // only predicates the framework can already check
  "fidelity_ceiling": string,       // no higher than the allowed ceiling
  "description": string
}

Constraints, enforced by a downstream verifier:
- Use only allowed execution domains, fact namespaces, evidence predicates, and fidelity
  ceilings, all listed below. A template that steps outside them is rejected.
- produce at least one fact not already required.
- never assert elevated access or credentials without a precondition that grants them.
- when a campaign context is present, use only its exact required facts, produced facts,
  execution domain, and binding kinds.
- when a campaign context is present, match one listed trusted behavior contract exactly. A
  proposal may name an alternate laboratory implementation, but it may not invent a new effect,
  precondition, evidence predicate, parameter interface, or fidelity ceiling.
"""


class TemplateProposalContext(StrictModel):
    campaign_id: str = Field(min_length=1)
    source_step_index: int = Field(ge=0)
    source_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    execution_domain: str
    admissible_required_facts: list[str] = Field(default_factory=list)
    admissible_produced_facts: list[str] = Field(min_length=1)
    available_binding_kinds: list[str] = Field(default_factory=list)
    existing_template_ids: list[str] = Field(default_factory=list)
    admissible_behavior_contracts: list["TrustedBehaviorContract"] = Field(min_length=1)
    content_sha256: str = ""

    def _computed_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def finalize_hash(self) -> None:
        self.content_sha256 = self._computed_hash()

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == self._computed_hash()


class TrustedBehaviorContract(StrictModel):
    """One behavior contract whose semantics are already implemented and reviewed."""

    parameter_kinds: dict[str, str] = Field(default_factory=dict)
    requires: list[str] = Field(default_factory=list)
    produces: list[str] = Field(min_length=1)
    evidence_predicates: list[str] = Field(min_length=1)
    fidelity_ceiling: str


def trusted_behavior_contract(template: ActionTemplate) -> TrustedBehaviorContract:
    """Normalize a template's observable contract for exact contextual admission."""

    return TrustedBehaviorContract(
        parameter_kinds=dict(sorted(template.parameter_kinds.items())),
        requires=sorted(template.requires),
        produces=sorted(template.produces),
        evidence_predicates=sorted(template.evidence_predicates),
        fidelity_ceiling=template.fidelity_ceiling,
    )


class TemplateProposalOutcome(StrictModel):
    technique_id: str
    admitted: bool
    template: ActionTemplate | None = None
    admission: TemplateAdmission | None = None
    attempts: int = 0
    parse_errors: list[str] = Field(default_factory=list)


def build_user_prompt(
    technique_id: str,
    technique_summary: str,
    vocabulary: AdmissionVocabulary,
    exemplars: Sequence[ActionTemplate],
    prior_issues: Sequence[VerificationIssue] = (),
    context: TemplateProposalContext | None = None,
) -> str:
    """Compose the technique-specific request, listing the vocabulary the verifier will enforce."""
    payload: dict[str, object] = {
        "technique_id": technique_id,
        "technique_summary": technique_summary,
        "allowed_execution_domains": sorted(vocabulary.execution_domains),
        "allowed_fact_namespaces": sorted(vocabulary.fact_namespaces),
        "allowed_evidence_predicates": sorted(vocabulary.evidence_predicates),
        "allowed_parameter_kinds": sorted(vocabulary.parameter_kinds),
        "allowed_fidelity_ceilings": sorted(vocabulary.fidelity_ceilings),
        "exemplars": [template.model_dump(mode="json") for template in exemplars],
    }
    if context is not None:
        payload["campaign_context"] = context.model_dump(mode="json")
    if prior_issues:
        payload["previous_rejection"] = [issue.model_dump(mode="json") for issue in prior_issues]
    return json.dumps(payload, indent=2, sort_keys=True)


def _parse_template(raw: str) -> ActionTemplate:
    # The model may wrap the object in prose or a code fence; take the outermost JSON object.
    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("response contains no JSON object")
    return ActionTemplate.model_validate_json(raw[start : end + 1])


def context_admission_issues(
    candidate: ActionTemplate,
    context: TemplateProposalContext,
) -> list[VerificationIssue]:
    issues: list[VerificationIssue] = []
    if candidate.execution_domain != context.execution_domain:
        issues.append(
            VerificationIssue(
                code="campaign_domain_mismatch",
                message=(
                    f"candidate domain {candidate.execution_domain!r} does not match "
                    f"campaign domain {context.execution_domain!r}"
                ),
            )
        )
    unavailable_kinds = sorted(
        set(candidate.parameter_kinds.values()) - set(context.available_binding_kinds)
    )
    if unavailable_kinds:
        issues.append(
            VerificationIssue(
                code="sut_binding_kind_unavailable",
                message="SUT catalog lacks binding kinds: " + ", ".join(unavailable_kinds),
            )
        )
    unavailable_requirements = sorted(
        set(candidate.requires) - set(context.admissible_required_facts)
    )
    if unavailable_requirements:
        issues.append(
            VerificationIssue(
                code="campaign_required_fact_unavailable",
                message="campaign fact envelope lacks: " + ", ".join(unavailable_requirements),
            )
        )
    unsupported_effects = sorted(set(candidate.produces) - set(context.admissible_produced_facts))
    if unsupported_effects:
        issues.append(
            VerificationIssue(
                code="campaign_effect_not_requested",
                message="candidate effects are outside the campaign envelope: "
                + ", ".join(unsupported_effects),
            )
        )
    if candidate.template_id in context.existing_template_ids:
        issues.append(
            VerificationIssue(
                code="existing_template_id_reused",
                message=f"template id {candidate.template_id!r} already exists for this context",
            )
        )
    if trusted_behavior_contract(candidate) not in context.admissible_behavior_contracts:
        issues.append(
            VerificationIssue(
                code="untrusted_behavior_contract",
                message=(
                    "candidate behavior contract is not an exact match for a "
                    "predeclared trusted contract"
                ),
            )
        )
    return issues


def _assess_template(
    candidate: ActionTemplate,
    technique_id: str,
    vocabulary: AdmissionVocabulary,
    context: TemplateProposalContext | None,
) -> TemplateAdmission:
    admission = admit_template(candidate, vocabulary)
    issues = list(admission.issues)
    if candidate.technique_ids != [technique_id]:
        issues.insert(
            0,
            VerificationIssue(
                code="technique_scope_mismatch",
                message=f"candidate must target exactly the requested technique {technique_id}",
            ),
        )
    if context is not None:
        issues.extend(context_admission_issues(candidate, context))
    return TemplateAdmission(
        template_id=candidate.template_id,
        admitted=not issues,
        issues=issues,
    )


def propose_template(
    technique_id: str,
    technique_summary: str,
    vocabulary: AdmissionVocabulary,
    exemplars: Sequence[ActionTemplate],
    complete: CompletionFn,
    *,
    max_attempts: int = 3,
    context: TemplateProposalContext | None = None,
) -> TemplateProposalOutcome:
    """Draft and verify a template, feeding rejection issues back for a bounded number of tries."""

    if context is not None and not context.validate_hash():
        raise ValueError("template proposal context hash mismatch")
    parse_errors: list[str] = []
    prior_issues: Sequence[VerificationIssue] = ()
    last_admission: TemplateAdmission | None = None
    for attempt in range(1, max_attempts + 1):
        user_prompt = build_user_prompt(
            technique_id,
            technique_summary,
            vocabulary,
            exemplars,
            prior_issues,
            context,
        )
        raw = complete(SYSTEM_PROMPT, user_prompt)
        try:
            candidate = _parse_template(raw)
        except (ValueError, ValidationError) as error:
            parse_errors.append(f"attempt {attempt}: {error}")
            continue
        admission = _assess_template(candidate, technique_id, vocabulary, context)
        last_admission = admission
        if admission.admitted:
            return TemplateProposalOutcome(
                technique_id=technique_id,
                admitted=True,
                template=candidate,
                admission=admission,
                attempts=attempt,
                parse_errors=parse_errors,
            )
        prior_issues = admission.issues
    return TemplateProposalOutcome(
        technique_id=technique_id,
        admitted=False,
        admission=last_admission,
        attempts=max_attempts,
        parse_errors=parse_errors,
    )
