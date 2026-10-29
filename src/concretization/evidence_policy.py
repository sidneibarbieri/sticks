"""Say what a template's evidence policy actually certifies.

The verifier requires at least one evidence predicate per template. That bound is too weak
to carry an execution claim: a policy made only of safety assertions shows the harness
stayed inside its boundary, and a policy resting on process exit shows only that a command
ran. Neither observes the state the template declares it produces.

Roles are declared once per predicate name for the whole catalog rather than inferred from
the name at run time. Inference would reintroduce exactly the hidden judgement this work
removes elsewhere, and it would let one name certify an effect in one template and a
boundary in another.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class PredicateRole(str, Enum):
    """What observing a predicate establishes."""

    effect = "effect"
    safety = "safety"
    liveness = "liveness"


class EvidencePolicyAudit(BaseModel):
    """How one template's declared evidence divides across the roles."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_id: str
    effect_predicates: list[str]
    safety_predicates: list[str]
    liveness_predicates: list[str]
    unregistered_predicates: list[str]

    @property
    def certifies_declared_effect(self) -> bool:
        return bool(self.effect_predicates) and not self.unregistered_predicates


class CatalogEvidenceReport(BaseModel):
    """The catalog-wide result the manuscript is allowed to state."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_count: int
    effect_certified_count: int
    safety_only_templates: list[str]
    liveness_only_templates: list[str]
    unregistered_predicates: list[str]

    @property
    def clean(self) -> bool:
        return not (
            self.safety_only_templates
            or self.liveness_only_templates
            or self.unregistered_predicates
        )


def load_roles(path: Path) -> dict[str, PredicateRole]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {name: PredicateRole(role) for name, role in payload["roles"].items()}


def audit_template(
    template_id: str,
    predicates: Sequence[str],
    roles: Mapping[str, PredicateRole],
) -> EvidencePolicyAudit:
    grouped: dict[PredicateRole, list[str]] = {role: [] for role in PredicateRole}
    unregistered: list[str] = []
    for predicate in predicates:
        role = roles.get(predicate)
        if role is None:
            unregistered.append(predicate)
        else:
            grouped[role].append(predicate)
    return EvidencePolicyAudit(
        template_id=template_id,
        effect_predicates=sorted(grouped[PredicateRole.effect]),
        safety_predicates=sorted(grouped[PredicateRole.safety]),
        liveness_predicates=sorted(grouped[PredicateRole.liveness]),
        unregistered_predicates=sorted(unregistered),
    )


def audit_catalog(
    templates: Iterable[Mapping[str, object]],
    roles: Mapping[str, PredicateRole],
) -> CatalogEvidenceReport:
    audits = [
        audit_template(
            str(template["template_id"]),
            list(template["evidence_predicates"]),
            roles,
        )
        for template in templates
    ]
    return CatalogEvidenceReport(
        template_count=len(audits),
        effect_certified_count=sum(1 for audit in audits if audit.certifies_declared_effect),
        safety_only_templates=sorted(
            audit.template_id
            for audit in audits
            if not audit.effect_predicates and not audit.liveness_predicates
        ),
        liveness_only_templates=sorted(
            audit.template_id
            for audit in audits
            if not audit.effect_predicates and audit.liveness_predicates
        ),
        unregistered_predicates=sorted(
            {
                predicate
                for audit in audits
                for predicate in audit.unregistered_predicates
            }
        ),
    )
