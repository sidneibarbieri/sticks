"""Deterministic admission of proposed action templates.

A proposer (LLM or otherwise) may suggest abstract action-template metadata. This module decides,
deterministically, whether that metadata is structurally compatible with the framework's existing
vocabulary. Contextual admission additionally requires an exact trusted behavior contract before a
candidate may be promoted. The proposer is replaceable; neither admission boundary is.

Admission is grounded in the vocabulary the framework already implements, derived from the
trusted catalog. A proposed template is structurally admissible only when it is expressible with
the same checkable evidence predicates, fact namespaces, execution domains, and fidelity ceilings
already implemented by the framework. This check alone does not establish a behavior contract.
Contextual admission rejects candidates whose complete contract is not already trusted, so new
semantics surface for explicit framework extension rather than entering on the proposer's word.
"""

from __future__ import annotations

import re
from typing import Iterable

from pydantic import Field

from .models import ActionTemplate, StrictModel, VerificationIssue

TECHNIQUE_ID_PATTERN = re.compile(r"^T\d{4}(\.\d{3})?$")

# Producing any of these effects asserts elevated access, credentials, or compromise. Such an
# effect must be enabled by a precondition; a template that grants it from an empty ``requires``
# claims access from nothing. This mirrors the privilege-boundary defect corrected in the catalog.
ELEVATION_MARKERS = ("root", "admin", "credential", "compromis", "elevat", "domain")


class AdmissionVocabulary(StrictModel):
    """The checkable vocabulary the framework implements, derived from the trusted catalog."""

    execution_domains: frozenset[str]
    fidelity_ceilings: frozenset[str]
    fact_namespaces: frozenset[str]
    evidence_predicates: frozenset[str]
    parameter_kinds: frozenset[str]


class TemplateAdmission(StrictModel):
    template_id: str
    admitted: bool
    issues: list[VerificationIssue] = Field(default_factory=list)


def fact_namespace(fact: str) -> str:
    """Return the namespace prefix of a fact string such as ``actor.ready`` or ``artifacts:x``."""
    return fact.split(".", 1)[0].split(":", 1)[0]


def build_admission_vocabulary(templates: Iterable[ActionTemplate]) -> AdmissionVocabulary:
    """Derive the admissible vocabulary from the trusted hand-curated catalog."""
    domains: set[str] = set()
    ceilings: set[str] = set()
    namespaces: set[str] = set()
    predicates: set[str] = set()
    parameter_kinds: set[str] = set()
    for template in templates:
        domains.add(template.execution_domain)
        ceilings.add(template.fidelity_ceiling)
        predicates.update(template.evidence_predicates)
        parameter_kinds.update(template.parameter_kinds.values())
        for fact in list(template.requires) + list(template.produces):
            namespaces.add(fact_namespace(fact))
    return AdmissionVocabulary(
        execution_domains=frozenset(domains),
        fidelity_ceilings=frozenset(ceilings),
        fact_namespaces=frozenset(namespaces),
        evidence_predicates=frozenset(predicates),
        parameter_kinds=frozenset(parameter_kinds),
    )


def _asserts_elevation(fact: str) -> bool:
    lowered = fact.lower()
    return any(marker in lowered for marker in ELEVATION_MARKERS)


def admit_template(candidate: ActionTemplate, vocabulary: AdmissionVocabulary) -> TemplateAdmission:
    """Check structural compatibility with the implemented vocabulary."""
    issues: list[VerificationIssue] = []

    for technique_id in candidate.technique_ids:
        if not TECHNIQUE_ID_PATTERN.match(technique_id):
            issues.append(
                VerificationIssue(
                    code="malformed_technique_id",
                    message=f"technique id {technique_id!r} is not a MITRE ATT&CK identifier",
                )
            )

    if candidate.execution_domain not in vocabulary.execution_domains:
        issues.append(
            VerificationIssue(
                code="unknown_execution_domain",
                message=(
                    f"execution domain {candidate.execution_domain!r} is outside the "
                    "implemented set"
                ),
            )
        )

    if candidate.fidelity_ceiling not in vocabulary.fidelity_ceilings:
        issues.append(
            VerificationIssue(
                code="unbounded_fidelity_ceiling",
                message=(
                    f"fidelity ceiling {candidate.fidelity_ceiling!r} exceeds the honest "
                    "catalog ceiling"
                ),
            )
        )

    for parameter_name, parameter_kind in candidate.parameter_kinds.items():
        if parameter_kind not in vocabulary.parameter_kinds:
            issues.append(
                VerificationIssue(
                    code="unknown_parameter_kind",
                    message=(
                        f"parameter {parameter_name!r} uses unimplemented kind "
                        f"{parameter_kind!r}"
                    ),
                )
            )

    for fact in candidate.requires:
        if fact_namespace(fact) not in vocabulary.fact_namespaces:
            issues.append(
                VerificationIssue(
                    code="unknown_required_namespace",
                    message=f"required fact {fact!r} uses an unmodelled namespace",
                )
            )
    for fact in candidate.produces:
        if fact_namespace(fact) not in vocabulary.fact_namespaces:
            issues.append(
                VerificationIssue(
                    code="unknown_produced_namespace",
                    message=f"produced fact {fact!r} uses an unmodelled namespace",
                )
            )

    for predicate in candidate.evidence_predicates:
        if predicate not in vocabulary.evidence_predicates:
            issues.append(
                VerificationIssue(
                    code="ungrounded_evidence_predicate",
                    message=f"evidence predicate {predicate!r} has no checkable implementation",
                )
            )

    if not set(candidate.produces) - set(candidate.requires):
        issues.append(
            VerificationIssue(
                code="no_state_progress",
                message="template produces no fact beyond what it already requires",
            )
        )

    if not candidate.requires and any(_asserts_elevation(fact) for fact in candidate.produces):
        issues.append(
            VerificationIssue(
                code="privilege_without_precondition",
                message="template asserts elevated access or credentials from no precondition",
            )
        )

    return TemplateAdmission(template_id=candidate.template_id, admitted=not issues, issues=issues)
