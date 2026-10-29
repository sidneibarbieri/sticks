"""Derive a declared laboratory environment from the action catalog.

A campaign plan admits no step until an environment supplies concrete bindings, which is
why the corpus analysis stops at catalog applicability while the deep evaluation needs a
hand-written binding catalog per campaign. That limit is not fundamental: the templates
already declare which parameter kinds they consume and which facts they require, so the
environment a plan needs can be derived from the catalog rather than authored.

The derivation is deterministic and conservative. One laboratory binding is emitted per
parameter kind the catalog consumes, and the initial facts are exactly the required facts
no template produces, since a fact some template produces is reachable through execution.
Every derived binding is marked as a system choice, so provenance keeps reporting these
values as introduced by the reconstruction rather than evidenced by the report.

Deriving an environment does not make it faithful to any historical victim network. It
supplies a declared laboratory in which the campaign's admitted steps can run and be
certified, which is what the model requires and all it claims.
"""

from __future__ import annotations

import hashlib
import json

from contracts.procedural_ir import ProceduralPlan

from .models import ActionTemplate, BindingCatalog, BindingValue
from .retrieval import retrieve_templates

LAB_SCOPE = "lab"
DERIVED_SOURCE = "system_choice"


def required_parameter_kinds(templates: list[ActionTemplate]) -> set[str]:
    """Parameter kinds any template in the catalog can consume."""
    return {kind for template in templates for kind in template.parameter_kinds.values()}


def reachable_templates(
    plan: ProceduralPlan, templates: list[ActionTemplate]
) -> list[ActionTemplate]:
    """Templates the plan's steps can retrieve, which bound what its execution can produce."""
    usable: set[str] = set()
    for step in plan.steps:
        retrieved, _ = retrieve_templates(step, templates)
        usable.update(template.template_id for template in retrieved)
    return [template for template in templates if template.template_id in usable]


def unproducible_facts(templates: list[ActionTemplate]) -> set[str]:
    """Facts these templates require but none produces, so execution cannot reach them.

    Derived per plan: a fact produced by a template the plan never retrieves is not
    reachable for that plan and must be supplied by the environment.
    """
    required = {fact for template in templates for fact in template.requires}
    produced = {fact for template in templates for fact in template.produces}
    return required - produced


def _binding_for(kind: str) -> BindingValue:
    # One binding per kind keeps the derived environment minimal: the solver needs a value
    # of each consumed kind, and additional values would only enlarge the candidate space.
    return BindingValue(
        binding_id=f"lab.{kind}",
        kind=kind,
        value=f"lab://{kind.replace('_', '-')}",
        source=DERIVED_SOURCE,
        scope=LAB_SCOPE,
        secret_reference=False,
    )


def derive_lab_environment(
    sut_id: str,
    templates: list[ActionTemplate],
    plan: ProceduralPlan | None = None,
) -> BindingCatalog:
    """Build the minimal declared laboratory a plan can bind against.

    Without a plan the environment covers the whole catalog; with one it is derived from
    the templates that plan can reach, which is what its execution can actually produce.
    """
    scoped = reachable_templates(plan, templates) if plan is not None else templates
    catalog_digest = hashlib.sha256(
        json.dumps(
            [template.model_dump(mode="json") for template in templates],
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()

    environment = BindingCatalog(
        sut_id=sut_id,
        source_sha256=catalog_digest,
        initial_facts=sorted(unproducible_facts(scoped)),
        goal_facts=[],
        bindings=[_binding_for(kind) for kind in sorted(required_parameter_kinds(scoped))],
    )
    environment.finalize_hash()
    return environment
