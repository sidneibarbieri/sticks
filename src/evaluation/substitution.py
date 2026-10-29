"""Substitution analysis: can the proposer's template choice change what is certified?

For each plan step the finite catalog admits the templates whose declared technique
set and execution domain match the step. This is an UPPER BOUND on the proposer's
discretion: it applies only technique and execution-domain applicability, and does NOT
apply the verifier's remaining admissibility checks -- binding availability and
preconditions (``requires`` subset of the accumulated ``known_facts``) -- which can only
narrow the applicable set further (see ``concretization.verifier.assess_candidate``).

The behavioral signature compared here is the declared evidence predicates plus the
fidelity ceiling -- the proxy for the certified observable effect. Differences in the
``produces`` set are deliberately excluded: those are internal fact-plumbing that the
planner resolves deterministically through the produces->requires chain, not a choice
the proposer makes over what is observed. A step is:

  determined          exactly one applicable template.
  evidence_equivalent >1 applicable, all sharing one evidence signature -- the proposer
                      may pick among them but cannot change what is certified.
  evidence_divergent  >1 applicable with distinct evidence signatures -- the only case
                      where an untrusted proposer's choice could change the certified
                      observable effect without a verifier evidence check catching it.
  unsupported         no applicable template in the catalog.

Honest limits. This measures a property of the finite catalog (whether co-applicable
templates share evidence signatures), not a property of the CTI, and N is small. The
trustworthy end-to-end version requires each campaign's enriched binding catalog -- which
does not yet exist in the artifact -- to apply the full verifier admissibility and to
confirm that downstream fact-chaining resolves the ``produces`` differences uniquely.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StepClass(str, Enum):
    determined = "determined"
    evidence_equivalent = "evidence_equivalent"
    evidence_divergent = "evidence_divergent"
    unsupported = "unsupported"


def evidence_signature(template: dict[str, Any]) -> tuple:
    """The certified observable effect: declared evidence predicates and fidelity.

    The ``produces`` set is intentionally excluded -- it is downstream fact-plumbing the
    planner resolves deterministically, not a proposer choice over what is observed.
    """
    return (
        tuple(sorted(template.get("evidence_predicates", []))),
        template.get("fidelity_ceiling"),
    )


def applicable_templates(
    technique_id: str,
    execution_domain: str,
    templates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Templates matching technique and execution domain (an upper bound on admissibility).

    The full verifier additionally requires available bindings and satisfied
    preconditions; those checks only remove candidates, never add them.
    """
    return [
        template
        for template in templates
        if technique_id in template.get("technique_ids", [])
        and template.get("execution_domain") == execution_domain
    ]


def classify_step(
    technique_id: str,
    execution_domain: str,
    templates: list[dict[str, Any]],
) -> StepClass:
    applicable = applicable_templates(technique_id, execution_domain, templates)
    if not applicable:
        return StepClass.unsupported
    if len(applicable) == 1:
        return StepClass.determined
    signatures = {evidence_signature(template) for template in applicable}
    if len(signatures) > 1:
        return StepClass.evidence_divergent
    return StepClass.evidence_equivalent


class CampaignSubstitution(StrictModel):
    campaign_id: str
    total_steps: int
    determined: int
    evidence_equivalent: int
    evidence_divergent: int
    unsupported: int
    # Steps admitting more than one applicable template (the proposer has a menu).
    multiplicity_rate: float
    # Steps where that menu offers distinct certified effects (upper bound; see module doc).
    evidence_divergence_rate: float


def analyze_campaign(
    campaign_id: str,
    steps: list[dict[str, Any]],
    templates: list[dict[str, Any]],
) -> CampaignSubstitution:
    counts = {member: 0 for member in StepClass}
    for step in steps:
        outcome = classify_step(step["technique_id"], step["execution_domain"], templates)
        counts[outcome] += 1
    total = len(steps)
    multiplicity = counts[StepClass.evidence_equivalent] + counts[StepClass.evidence_divergent]
    return CampaignSubstitution(
        campaign_id=campaign_id,
        total_steps=total,
        determined=counts[StepClass.determined],
        evidence_equivalent=counts[StepClass.evidence_equivalent],
        evidence_divergent=counts[StepClass.evidence_divergent],
        unsupported=counts[StepClass.unsupported],
        multiplicity_rate=(multiplicity / total) if total else 0.0,
        evidence_divergence_rate=(
            counts[StepClass.evidence_divergent] / total
        ) if total else 0.0,
    )


class CorpusSubstitution(StrictModel):
    total_campaigns: int
    total_steps: int
    determined: int
    evidence_equivalent: int
    evidence_divergent: int
    unsupported: int
    # Steps the finite catalog covers (technique + domain applicable).
    catalog_supported_steps: int
    catalog_coverage_rate: float
    # Evidence-divergent steps as a fraction of the catalog-supported steps.
    evidence_divergence_rate_over_supported: float
    campaigns: list[CampaignSubstitution]


def analyze_corpus(
    campaigns: dict[str, list[dict[str, Any]]],
    templates: list[dict[str, Any]],
) -> CorpusSubstitution:
    """Aggregate the substitution classification across campaigns.

    This is a catalog-level result over declared evidence signatures, reported for the
    catalog-supported steps (coverage is typically well below one). It does not establish
    behavioral equivalence, which requires executing the admissible alternatives.
    """
    per_campaign = [
        analyze_campaign(campaign_id, steps, templates)
        for campaign_id, steps in sorted(campaigns.items())
    ]
    determined = sum(c.determined for c in per_campaign)
    equivalent = sum(c.evidence_equivalent for c in per_campaign)
    divergent = sum(c.evidence_divergent for c in per_campaign)
    unsupported = sum(c.unsupported for c in per_campaign)
    total_steps = sum(c.total_steps for c in per_campaign)
    supported = determined + equivalent + divergent
    return CorpusSubstitution(
        total_campaigns=len(per_campaign),
        total_steps=total_steps,
        determined=determined,
        evidence_equivalent=equivalent,
        evidence_divergent=divergent,
        unsupported=unsupported,
        catalog_supported_steps=supported,
        catalog_coverage_rate=(supported / total_steps) if total_steps else 0.0,
        evidence_divergence_rate_over_supported=(
            divergent / supported
        ) if supported else 0.0,
        campaigns=per_campaign,
    )
