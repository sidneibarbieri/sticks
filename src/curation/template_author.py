"""Screen model-proposed template drafts against a schema and declared vocabularies.

Categorical fields have finite allowed sets; free-text facts and descriptions do
not. Passing this gate establishes structural validity, not semantic correctness,
executable implementation, or independently observed effects. Drafts are never
promoted to trusted templates by this module.
"""

from __future__ import annotations

import json
from enum import Enum

from pydantic import BaseModel, ConfigDict, ValidationError

from concretization.evidence_policy import PredicateRole
from concretization.models import ActionTemplate

ADMISSIBLE_DOMAINS = ("attacker", "boundary", "target")
# The catalog tops out at adapted; a proposer may never label a surrogate faithful.
ADMISSIBLE_FIDELITY = ("adapted", "inspired")


class TemplateLifecycle(str, Enum):
    """A proposed template is a draft until a human review promotes it."""

    draft = "draft"
    trusted = "trusted"


class RejectionCode(str, Enum):
    """Why the deterministic gate refused a proposed template."""

    malformed_schema = "malformed_schema"
    technique_drift = "technique_drift"
    unknown_predicate = "unknown_predicate"
    no_effect_predicate = "no_effect_predicate"
    unbindable_parameter = "unbindable_parameter"
    overclaimed_fidelity = "overclaimed_fidelity"
    invalid_domain = "invalid_domain"


class AdmissionVocabulary(BaseModel):
    """The declared sets a proposed template must draw from to be admissible."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    predicate_roles: dict[str, PredicateRole]
    bindable_kinds: frozenset[str]

    @property
    def effect_predicates(self) -> frozenset[str]:
        return frozenset(
            name for name, role in self.predicate_roles.items() if role is PredicateRole.effect
        )


class TemplateProposalOutcome(BaseModel):
    """The gate's verdict on one proposed template."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    technique_id: str
    admitted: bool
    template: ActionTemplate | None = None
    rejection_code: RejectionCode | None = None
    rejection_detail: str = ""


def _reject(technique_id: str, code: RejectionCode, detail: str) -> TemplateProposalOutcome:
    return TemplateProposalOutcome(
        technique_id=technique_id, admitted=False, rejection_code=code, rejection_detail=detail
    )


def admit_proposal(
    technique_id: str,
    proposal: dict[str, object],
    vocabulary: AdmissionVocabulary,
) -> TemplateProposalOutcome:
    """Decide whether one proposed template is admissible, deterministically.

    Every check is a membership test against a declared set, so the same proposal yields the
    same verdict on every run and no check depends on the proposer's identity.
    """
    try:
        template = ActionTemplate.model_validate(proposal)
    except ValidationError as error:
        return _reject(technique_id, RejectionCode.malformed_schema, str(error))

    if template.technique_ids != [technique_id]:
        return _reject(
            technique_id,
            RejectionCode.technique_drift,
            f"proposal named {template.technique_ids}, not [{technique_id}]",
        )

    if template.execution_domain not in ADMISSIBLE_DOMAINS:
        return _reject(
            technique_id, RejectionCode.invalid_domain, template.execution_domain
        )

    if template.fidelity_ceiling not in ADMISSIBLE_FIDELITY:
        return _reject(
            technique_id, RejectionCode.overclaimed_fidelity, template.fidelity_ceiling
        )

    unknown = sorted(set(template.evidence_predicates) - set(vocabulary.predicate_roles))
    if unknown:
        return _reject(
            technique_id, RejectionCode.unknown_predicate, ", ".join(unknown)
        )

    if not set(template.evidence_predicates) & vocabulary.effect_predicates:
        return _reject(
            technique_id,
            RejectionCode.no_effect_predicate,
            "policy observes no produced state",
        )

    unbindable = sorted(set(template.parameter_kinds.values()) - vocabulary.bindable_kinds)
    if unbindable:
        return _reject(
            technique_id, RejectionCode.unbindable_parameter, ", ".join(unbindable)
        )

    return TemplateProposalOutcome(technique_id=technique_id, admitted=True, template=template)


def extract_proposal(content: str) -> dict[str, object] | None:
    """Return the outermost JSON object in a provider response, or None when there is none."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        candidate = json.loads(content[start : end + 1])
    except json.JSONDecodeError:
        return None
    return candidate if isinstance(candidate, dict) else None


def admit_response(
    technique_id: str, content: str, vocabulary: AdmissionVocabulary
) -> TemplateProposalOutcome:
    """Admit a raw provider response; a response without a JSON object is malformed."""
    proposal = extract_proposal(content)
    if proposal is None:
        return _reject(
            technique_id,
            RejectionCode.malformed_schema,
            "provider response contained no JSON object",
        )
    return admit_proposal(technique_id, proposal, vocabulary)
