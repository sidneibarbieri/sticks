"""Corpus coverage as a function of catalog size.

The substitution analysis reports a single coverage number: how many of the corpus
steps the full catalog supports (technique and execution-domain applicable). That number
is exact rather than estimated precisely because admission can refuse: a step with no
applicable template is reported as unsupported instead of being filled in. This module
turns the single number into a trajectory by measuring coverage over catalogs of growing
size, so the frontier reads as a curve with a slope rather than a static ceiling.

Templates are added in greedy marginal-coverage order: at each step the template that
newly matches the most corpus steps is added next, with ties broken by template id.
This is one deterministic catalog ordering, not a globally optimal coverage frontier.
Its endpoint equals the full-catalog match count in the substitution evidence.

This measures technique-and-domain applicability over the public corpus, an upper bound
on admission. It does not establish execution or behavioral equivalence.
"""

from __future__ import annotations

from typing import Any

from evaluation.substitution import StrictModel, analyze_corpus

Campaigns = dict[str, list[dict[str, Any]]]
Template = dict[str, Any]


def supported_steps(campaigns: Campaigns, templates: list[Template]) -> int:
    """Corpus steps a catalog supports: determined, evidence-equivalent, or divergent."""
    corpus = analyze_corpus(campaigns, templates)
    return corpus.determined + corpus.evidence_equivalent + corpus.evidence_divergent


class CoveragePoint(StrictModel):
    """One catalog size on the coverage curve, after adding ``template_id``."""

    catalog_size: int
    template_id: str
    technique_ids: list[str]
    supported_steps: int
    marginal_steps: int
    coverage_rate: float


class CoverageCurve(StrictModel):
    """Corpus coverage over catalogs of growing size, in greedy marginal order."""

    ordering: str = "greedy_marginal_coverage"
    total_steps: int
    total_templates: int
    full_catalog_supported_steps: int
    points: list[CoveragePoint]


def _template_id(template: Template) -> str:
    return template["template_id"]


def _most_covering_template(
    campaigns: Campaigns,
    chosen: list[Template],
    remaining: list[Template],
    covered_now: int,
) -> tuple[Template, int]:
    """Pick the remaining template with the largest marginal coverage gain."""
    best_template = remaining[0]
    best_supported = supported_steps(campaigns, [*chosen, best_template])
    for template in remaining[1:]:
        candidate_supported = supported_steps(campaigns, [*chosen, template])
        if candidate_supported > best_supported:
            best_template, best_supported = template, candidate_supported
    return best_template, best_supported - covered_now


def greedy_coverage_curve(
    campaigns: Campaigns, templates: list[Template]
) -> CoverageCurve:
    """Measure coverage as templates are added in greedy marginal-coverage order."""
    if not templates:
        raise ValueError("Coverage curve requires a nonempty template catalog")
    template_ids = [_template_id(template) for template in templates]
    if len(template_ids) != len(set(template_ids)):
        raise ValueError("Coverage curve requires unique template IDs")

    full_catalog = analyze_corpus(campaigns, templates)
    total_steps = full_catalog.total_steps
    if not total_steps:
        raise ValueError("Coverage curve requires corpus steps")
    remaining = sorted(templates, key=_template_id)
    chosen: list[Template] = []
    covered = 0
    points: list[CoveragePoint] = []
    while remaining:
        template, marginal = _most_covering_template(
            campaigns, chosen, remaining, covered
        )
        chosen.append(template)
        remaining.remove(template)
        covered += marginal
        points.append(
            CoveragePoint(
                catalog_size=len(chosen),
                template_id=_template_id(template),
                technique_ids=template.get("technique_ids", []),
                supported_steps=covered,
                marginal_steps=marginal,
                coverage_rate=covered / total_steps,
            )
        )
    if covered != full_catalog.catalog_supported_steps:
        raise AssertionError("Coverage endpoint disagrees with full-catalog analysis")
    return CoverageCurve(
        total_steps=total_steps,
        total_templates=len(templates),
        full_catalog_supported_steps=full_catalog.catalog_supported_steps,
        points=points,
    )
