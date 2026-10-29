"""Versioned semantic identities for finite-domain planning facts.

The causal planner intentionally treats facts as exact identifiers. That keeps the
search deterministic, but it does not by itself prevent two identifiers from
silently denoting the same state or a fact from appearing in an impermissible
role. This module provides a small, versioned registry and a static audit for
that boundary.

The audit proves only registry coverage, identity uniqueness, and permitted
origins within a declared catalog. It does not prove a fact held in a live SUT
or that an execution produced an effect. Those require separate receipts and
an independent observer.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Literal

from pydantic import Field, model_validator

from .models import ActionTemplate, BindingCatalog, StrictModel
from .pipeline import action_catalog_hash


class FactUse(str, Enum):
    """Where a fact is introduced or consumed in a planning contract."""

    catalog_initial = "catalog_initial"
    template_requirement = "template_requirement"
    template_effect = "template_effect"
    catalog_goal = "catalog_goal"


class FactAssertion(str, Enum):
    """The kind of state assertion represented by a fact identifier."""

    access = "access"
    artifact = "artifact"
    assessment = "assessment"
    availability = "availability"
    capability = "capability"
    channel = "channel"
    cleanup = "cleanup"
    collection = "collection"
    configuration = "configuration"
    discovery = "discovery"
    exfiltration = "exfiltration"
    impact = "impact"
    infrastructure = "infrastructure"
    observation = "observation"
    persistence = "persistence"
    transfer = "transfer"


class EvidenceRequirement(str, Enum):
    """Evidence class needed before a semantic fact can support a stronger claim."""

    declared_contract = "declared_contract"
    transition_receipt = "transition_receipt"
    independent_effect_observation = "independent_effect_observation"


class FactSemanticDescriptor(StrictModel):
    """One non-overlapping semantic identity in the trusted fact vocabulary."""

    fact_id: str = Field(pattern=r"^[a-z0-9._:-]+$")
    subject: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    predicate: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    assertion: FactAssertion
    allowed_uses: list[FactUse] = Field(min_length=1)
    evidence_requirement: EvidenceRequirement

    @model_validator(mode="after")
    def validate_allowed_uses(self) -> "FactSemanticDescriptor":
        if len(self.allowed_uses) != len(set(self.allowed_uses)):
            raise ValueError("fact semantic descriptor repeats an allowed use")
        return self

    @property
    def semantic_identity(self) -> tuple[str, str, FactAssertion]:
        """Return the identity that must remain unique across fact identifiers."""
        return self.subject, self.predicate, self.assertion


class FactSemanticsRegistry(StrictModel):
    """Hash-bound fact vocabulary used by the planning and curation boundaries."""

    schema_version: Literal["1"] = "1"
    facts: list[FactSemanticDescriptor] = Field(min_length=1)
    content_sha256: str = ""

    @model_validator(mode="after")
    def validate_identities(self) -> "FactSemanticsRegistry":
        fact_ids = [descriptor.fact_id for descriptor in self.facts]
        if len(fact_ids) != len(set(fact_ids)):
            raise ValueError("fact semantic registry contains duplicate fact identifiers")
        identities = [descriptor.semantic_identity for descriptor in self.facts]
        if len(identities) != len(set(identities)):
            raise ValueError("fact semantic registry contains duplicate semantic identities")
        return self

    def finalize_hash(self) -> None:
        self.content_sha256 = _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def descriptors_by_fact_id(self) -> dict[str, FactSemanticDescriptor]:
        return {descriptor.fact_id: descriptor for descriptor in self.facts}


class FactUseViolation(StrictModel):
    """A known fact used in a role its registry descriptor forbids."""

    fact_id: str
    use: FactUse
    source_reference: str
    allowed_uses: list[FactUse]


class FactSemanticAudit(StrictModel):
    """Static compatibility result for one SUT binding catalog and template catalog."""

    schema_version: Literal["1"] = "1"
    audit_scope: Literal["static_semantic_identity_and_origin"] = (
        "static_semantic_identity_and_origin"
    )
    claim_boundary: str = "does_not_establish_live_state_or_operational_effect_evidence"
    sut_id: str
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    binding_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    fact_use_count: int = Field(ge=0)
    referenced_fact_ids: list[str] = Field(default_factory=list)
    unregistered_fact_ids: list[str] = Field(default_factory=list)
    use_violations: list[FactUseViolation] = Field(default_factory=list)
    conformant: bool
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        self.content_sha256 = _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )


class FactSemanticsCoverageReport(StrictModel):
    """Aggregate static semantic coverage over explicitly selected SUT catalogs."""

    schema_version: Literal["1"] = "1"
    audit_scope: Literal["static_semantic_identity_and_origin"] = (
        "static_semantic_identity_and_origin"
    )
    claim_boundary: str = "does_not_establish_live_state_or_operational_effect_evidence"
    registry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    action_catalog_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    audited_sut_count: int = Field(ge=0)
    conformant_sut_count: int = Field(ge=0)
    conformant: bool
    audits: list[FactSemanticAudit] = Field(default_factory=list)
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        self.content_sha256 = _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == _canonical_hash(
            self.model_dump(mode="json", exclude={"content_sha256"})
        )


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _fact_uses(
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
) -> list[tuple[str, FactUse, str]]:
    uses: list[tuple[str, FactUse, str]] = []
    uses.extend(
        (fact_id, FactUse.catalog_initial, f"catalog:{catalog.sut_id}")
        for fact_id in catalog.initial_facts
    )
    uses.extend(
        (fact_id, FactUse.catalog_goal, f"catalog:{catalog.sut_id}")
        for fact_id in catalog.goal_facts
    )
    for template in templates:
        uses.extend(
            (fact_id, FactUse.template_requirement, f"template:{template.template_id}")
            for fact_id in template.requires
        )
        uses.extend(
            (fact_id, FactUse.template_effect, f"template:{template.template_id}")
            for fact_id in template.produces
        )
    return uses


def audit_fact_semantics(
    registry: FactSemanticsRegistry,
    catalog: BindingCatalog,
    templates: list[ActionTemplate],
) -> FactSemanticAudit:
    """Audit fact identities and permitted origins without interpreting execution state."""

    if not registry.validate_hash():
        raise ValueError("fact semantic registry hash mismatch")
    if not catalog.validate_hash():
        raise ValueError("binding catalog hash mismatch")
    template_ids = [template.template_id for template in templates]
    if len(template_ids) != len(set(template_ids)):
        raise ValueError("action template identifiers must be unique")

    descriptors = registry.descriptors_by_fact_id()
    unregistered: set[str] = set()
    violations: list[FactUseViolation] = []
    uses = _fact_uses(catalog, templates)
    for fact_id, use, source_reference in uses:
        descriptor = descriptors.get(fact_id)
        if descriptor is None:
            unregistered.add(fact_id)
            continue
        if use not in descriptor.allowed_uses:
            violations.append(
                FactUseViolation(
                    fact_id=fact_id,
                    use=use,
                    source_reference=source_reference,
                    allowed_uses=sorted(
                        descriptor.allowed_uses,
                        key=lambda allowed_use: allowed_use.value,
                    ),
                )
            )

    result = FactSemanticAudit(
        sut_id=catalog.sut_id,
        registry_sha256=registry.content_sha256,
        binding_catalog_sha256=catalog.content_sha256,
        action_catalog_sha256=action_catalog_hash(templates),
        fact_use_count=len(uses),
        referenced_fact_ids=sorted({fact_id for fact_id, _, _ in uses}),
        unregistered_fact_ids=sorted(unregistered),
        use_violations=sorted(
            violations,
            key=lambda violation: (
                violation.fact_id,
                violation.use.value,
                violation.source_reference,
            ),
        ),
        conformant=not unregistered and not violations,
    )
    result.finalize_hash()
    return result


def build_fact_semantics_coverage_report(
    registry: FactSemanticsRegistry,
    catalogs: list[BindingCatalog],
    templates: list[ActionTemplate],
) -> FactSemanticsCoverageReport:
    """Audit each selected SUT catalog against one versioned fact registry."""

    sut_ids = [catalog.sut_id for catalog in catalogs]
    if len(sut_ids) != len(set(sut_ids)):
        raise ValueError("semantic coverage report contains duplicate SUT identifiers")
    audits = sorted(
        (audit_fact_semantics(registry, catalog, templates) for catalog in catalogs),
        key=lambda audit: audit.sut_id,
    )
    result = FactSemanticsCoverageReport(
        registry_sha256=registry.content_sha256,
        action_catalog_sha256=action_catalog_hash(templates),
        audited_sut_count=len(audits),
        conformant_sut_count=sum(audit.conformant for audit in audits),
        conformant=all(audit.conformant for audit in audits),
        audits=audits,
    )
    result.finalize_hash()
    return result
