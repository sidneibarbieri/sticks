"""Detect overly-permissive template contracts the evidence-policy role check cannot see.

The evidence-policy audit (``evidence_policy.py``) checks that a template's declared
evidence observes a state it produces. It says nothing about the *shape* of the
contract itself. A template can carry a proper effect predicate and still over-admit:

* it can declare that it produces a state while requiring nothing, so the verifier
  would admit it in almost any state (an unconditioned effect); or
* it can list preconditions that it manufactures itself -- every required fact is
  also one of its own produced facts -- so admission is circular (a self-satisfying
  requirement).

Both are decidable functions of the frozen catalog and need no model. The guard keeps
the catalog honest as templates are added (for example when Atomic Red Team tests are
imported or stage-2 authoring proposes new templates): a weak contract is rejected
before it can widen admission silently. Role inference is deliberately avoided for the
same reason it is avoided in ``evidence_policy``: it would reintroduce hidden judgement.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from enum import Enum

from pydantic import BaseModel


class ContractWeakness(str, Enum):
    """One exact, decidable way a template contract over-admits."""

    unconditioned_effect = "unconditioned_effect"
    self_satisfying_requirement = "self_satisfying_requirement"


class TemplateContractAudit(BaseModel):
    """How one template's declared contract scores against the weakness tests."""

    template_id: str
    requires: list[str]
    produces: list[str]
    weaknesses: list[ContractWeakness]

    @property
    def sound(self) -> bool:
        return not self.weaknesses


class CatalogContractReport(BaseModel):
    """The weak contracts, if any, in a whole catalog."""

    template_count: int
    unconditioned_effect_templates: list[str]
    self_satisfying_templates: list[str]

    @property
    def clean(self) -> bool:
        return not self.unconditioned_effect_templates and not self.self_satisfying_templates


def audit_template_contract(template: Mapping[str, object]) -> TemplateContractAudit:
    """Score one template against the contract-strength weakness tests."""

    requires = [str(fact) for fact in template.get("requires", [])]
    produces = [str(fact) for fact in template.get("produces", [])]
    required = set(requires)
    produced = set(produces)
    weaknesses: list[ContractWeakness] = []
    # Unconditioned effect: the template declares a produced state but no precondition,
    # so the verifier would admit it in any state.
    if produced and not required:
        weaknesses.append(ContractWeakness.unconditioned_effect)
    # Self-satisfying requirement: every required fact is one the template itself
    # produces, so the precondition carries no independent constraint.
    if required and required <= produced:
        weaknesses.append(ContractWeakness.self_satisfying_requirement)
    return TemplateContractAudit(
        template_id=str(template["template_id"]),
        requires=sorted(required),
        produces=sorted(produced),
        weaknesses=weaknesses,
    )


def audit_catalog_contracts(
    templates: Iterable[Mapping[str, object]],
) -> CatalogContractReport:
    """Score every template and collect the weak contracts by category."""

    audits = [audit_template_contract(template) for template in templates]
    return CatalogContractReport(
        template_count=len(audits),
        unconditioned_effect_templates=sorted(
            audit.template_id
            for audit in audits
            if ContractWeakness.unconditioned_effect in audit.weaknesses
        ),
        self_satisfying_templates=sorted(
            audit.template_id
            for audit in audits
            if ContractWeakness.self_satisfying_requirement in audit.weaknesses
        ),
    )
