"""Admissibility scopes: the fact state a template is judged against.

Whether the verifier admits a template depends on which facts are assumed to hold. Three
scopes are meaningful, and conflating them changes what a result means:

  hypothetical  every fact the catalog could ever produce, plus the declared initial facts.
                Over-admits by construction. Answers "could this template ever apply in
                this campaign?" -- a catalog property, not a campaign property.
  initial       only the environment's declared initial facts, before any step runs.
  sequential    the facts holding when the step is actually reached, that is the initial
                facts plus what the preceding committed steps produced. This is the scope
                the pipeline uses when it commits a plan, and the only scope whose
                multiplicity means a real alternative existed at execution time.

Passing the scope explicitly, rather than an anonymous set of fact strings, keeps a result
computed under one scope from being reported as if it held under another.
"""

from __future__ import annotations

from enum import Enum

from contracts.procedural_ir import ProcedureStep

from .models import ActionTemplate, BindingCatalog
from .retrieval import retrieve_templates
from .solver import enumerate_candidates
from .verifier import assess_candidate


class AdmissibilityScope(str, Enum):
    hypothetical = "hypothetical"
    initial = "initial"
    sequential = "sequential"


def hypothetical_facts(
    catalog: BindingCatalog, templates: list[ActionTemplate]
) -> set[str]:
    facts = set(catalog.initial_facts)
    for template in templates:
        facts.update(template.produces)
    return facts


def sequential_facts(
    catalog: BindingCatalog,
    committed_steps: list,
    until_technique_id: str,
) -> set[str]:
    """Facts holding when the step for ``until_technique_id`` is reached."""
    facts = set(catalog.initial_facts)
    for step in committed_steps:
        if step.technique_id == until_technique_id:
            break
        facts.update(step.produces)
    return facts


def admitted_template_ids(
    step: ProcedureStep,
    templates: list[ActionTemplate],
    catalog: BindingCatalog,
    known_facts: set[str],
) -> list[str]:
    """Template ids the deterministic verifier admits for this step under these facts."""
    template_index = {template.template_id: template for template in templates}
    retrieved, _ = retrieve_templates(step, templates)
    admitted = {
        candidate.template_id
        for candidate in enumerate_candidates(step, retrieved, catalog)
        if assess_candidate(
            candidate,
            technique_id=step.technique_id,
            execution_domain=step.execution_domain,
            templates=template_index,
            catalog=catalog,
            known_facts=known_facts,
        ).accepted
    }
    return sorted(admitted)
