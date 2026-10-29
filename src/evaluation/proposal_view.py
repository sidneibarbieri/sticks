"""Shared, arm-neutral view of the catalog and the declared environment.

Every arm sees exactly the same templates and bindings. Holding this view in one place keeps the
comparison matched: the treatment is the instruction each arm receives and whether admission is
applied, never a difference in the information available to it.
"""

from __future__ import annotations

from concretization.models import ActionTemplate, BindingCatalog


def raw_template_view(templates: list[ActionTemplate]) -> list[dict[str, object]]:
    """Describe each template by technique and interface only.

    This is the unenriched representation: it names the templates and the parameter kinds they take
    but not the precondition and effect facts. It is what a technique label plus a plain action
    catalog offer, and it is the view the prior-work arm receives.
    """
    return [
        {
            "template_id": template.template_id,
            "technique_ids": sorted(template.technique_ids),
            "parameter_kinds": dict(sorted(template.parameter_kinds.items())),
        }
        for template in templates
    ]


def template_view(templates: list[ActionTemplate]) -> list[dict[str, object]]:
    """Describe each template by its interface and its declared precondition and effect facts.

    This is the enriched representation the STICKS arms receive: it adds the required and produced
    facts that make admissibility decidable.
    """
    return [
        {
            **entry,
            "requires": sorted(template.requires),
            "produces": sorted(template.produces),
        }
        for template, entry in zip(templates, raw_template_view(templates))
    ]


def feasible_template_view(
    templates: list[ActionTemplate],
    *,
    technique_id: str,
    execution_domain: str,
    known_facts: list[str],
) -> list[dict[str, object]]:
    """Return templates whose declared prerequisites hold for one step.

    This is retrieval-time filtering, not admission.  The returned records retain
    their complete contracts and every selected response is still independently
    checked by the verifier.
    """
    available_facts = set(known_facts)
    candidates = [
        template
        for template in templates
        if technique_id in template.technique_ids
        and template.execution_domain == execution_domain
        and set(template.requires).issubset(available_facts)
    ]
    return template_view(candidates)


def binding_view(catalog: BindingCatalog) -> list[dict[str, str]]:
    """Describe each declared binding by identifier and kind, so parameters can be bound by kind."""
    return [
        {"binding_id": binding.binding_id, "kind": binding.kind}
        for binding in catalog.bindings
    ]


def feasible_binding_view(
    catalog: BindingCatalog, templates: list[ActionTemplate]
) -> list[dict[str, str]]:
    """Return bindings whose declared kind can satisfy a feasible template."""
    required_kinds = {
        kind for template in templates for kind in template.parameter_kinds.values()
    }
    return [
        {"binding_id": binding.binding_id, "kind": binding.kind}
        for binding in catalog.bindings
        if binding.kind in required_kinds
    ]
