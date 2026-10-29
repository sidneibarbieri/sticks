"""Complete finite-domain candidate enumeration for safe action templates."""

from __future__ import annotations

import itertools
import math
from collections.abc import Iterable

from contracts.procedural_ir import ProcedureStep

from .models import ActionTemplate, BindingCatalog, ProcedureProposal


def enumerate_candidates(
    step: ProcedureStep,
    templates: list[ActionTemplate],
    catalog: BindingCatalog,
    *,
    maximum_candidates: int = 512,
) -> list[ProcedureProposal]:
    by_kind: dict[str, list[str]] = {}
    for binding in catalog.bindings:
        if binding.scope.value == "lab":
            by_kind.setdefault(binding.kind, []).append(binding.binding_id)
    for binding_ids in by_kind.values():
        binding_ids.sort()

    candidates: list[ProcedureProposal] = []
    for template in sorted(templates, key=lambda item: item.template_id):
        if step.technique_id not in template.technique_ids:
            continue
        parameters = sorted(template.parameter_kinds)
        domains = [by_kind.get(template.parameter_kinds[parameter], []) for parameter in parameters]
        if any(not domain for domain in domains):
            continue
        template_candidate_count = math.prod(len(domain) for domain in domains)
        if len(candidates) + template_candidate_count > maximum_candidates:
            raise ValueError(
                f"candidate enumeration for {step.technique_id} exceeded "
                f"{maximum_candidates}; raise maximum_candidates rather than "
                "reporting a truncated candidate set as complete"
            )
        combinations: Iterable[tuple[str, ...]] = itertools.product(*domains) if domains else [()]
        for combination in combinations:
            candidates.append(
                ProcedureProposal(
                    technique_id=step.technique_id,
                    template_id=template.template_id,
                    bindings=dict(zip(parameters, combination)),
                )
            )
    return candidates
