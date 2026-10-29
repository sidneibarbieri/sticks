"""Deterministic verifier for LLM- or solver-proposed procedures."""

from __future__ import annotations

from typing import Iterable

from .models import (
    ActionTemplate,
    BindingCatalog,
    CandidateAssessment,
    ProcedureProposal,
    VerificationIssue,
)


def assess_candidate(
    proposal: ProcedureProposal,
    *,
    technique_id: str,
    execution_domain: str,
    templates: dict[str, ActionTemplate],
    catalog: BindingCatalog,
    known_facts: set[str],
) -> CandidateAssessment:
    issues: list[VerificationIssue] = []
    template = templates.get(proposal.template_id)
    if proposal.technique_id != technique_id:
        issues.append(
            VerificationIssue(
                code="TECHNIQUE_MISMATCH",
                message="proposal technique does not match the current plan step",
            )
        )
    if template is None:
        issues.append(
            VerificationIssue(
                code="UNKNOWN_TEMPLATE",
                message=f"unknown template {proposal.template_id}",
            )
        )
        return CandidateAssessment(proposal=proposal, accepted=False, issues=issues)
    if technique_id not in template.technique_ids:
        issues.append(
            VerificationIssue(
                code="UNSUPPORTED_TECHNIQUE",
                message=f"{template.template_id} does not support {technique_id}",
            )
        )
    if template.execution_domain != execution_domain:
        issues.append(
            VerificationIssue(
                code="EXECUTION_DOMAIN_MISMATCH",
                message=(
                    f"template domain {template.execution_domain} does not match "
                    f"step domain {execution_domain}"
                ),
            )
        )

    binding_index = {item.binding_id: item for item in catalog.bindings}
    expected_parameters = set(template.parameter_kinds)
    supplied_parameters = set(proposal.bindings)
    if expected_parameters != supplied_parameters:
        issues.append(
            VerificationIssue(
                code="PARAMETER_SET_MISMATCH",
                message=(
                    f"expected parameters {sorted(expected_parameters)}, "
                    f"received {sorted(supplied_parameters)}"
                ),
            )
        )
    assumption_count = 0
    for parameter, binding_id in sorted(proposal.bindings.items()):
        binding = binding_index.get(binding_id)
        if binding is None:
            issues.append(
                VerificationIssue(
                    code="UNKNOWN_BINDING",
                    message=f"{parameter} references unknown binding {binding_id}",
                )
            )
            continue
        expected_kind = template.parameter_kinds.get(parameter)
        if expected_kind != binding.kind:
            issues.append(
                VerificationIssue(
                    code="BINDING_KIND_MISMATCH",
                    message=(
                        f"{parameter} requires {expected_kind}, "
                        f"but {binding_id} is {binding.kind}"
                    ),
                )
            )
        if binding.scope.value != "lab":
            issues.append(
                VerificationIssue(
                    code="EXTERNAL_BINDING_FORBIDDEN",
                    message=f"{binding_id} is outside the declared laboratory",
                )
            )
        if binding.source not in {"stix", "sut", "executor"}:
            assumption_count += 1

    missing_facts = sorted(set(template.requires) - known_facts)
    if missing_facts:
        issues.append(
            VerificationIssue(
                code="UNSATISFIED_PRECONDITIONS",
                message=f"missing facts: {', '.join(missing_facts)}",
            )
        )
    if not template.evidence_predicates:
        issues.append(
            VerificationIssue(
                code="NO_EVIDENCE_POLICY",
                message="template declares no evidence predicate",
            )
        )
    return CandidateAssessment(
        proposal=proposal,
        accepted=not issues,
        issues=issues,
        assumption_count=assumption_count,
    )


def choose_candidate(
    assessments: Iterable[CandidateAssessment],
) -> CandidateAssessment | None:
    accepted = [assessment for assessment in assessments if assessment.accepted]
    if not accepted:
        return None
    return min(
        accepted,
        key=lambda assessment: (
            assessment.assumption_count,
            0 if assessment.proposal.source == "llm" else 1,
            assessment.proposal.template_id,
            tuple(sorted(assessment.proposal.bindings.items())),
        ),
    )
