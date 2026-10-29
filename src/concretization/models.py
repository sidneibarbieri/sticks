"""Typed contracts for finite-domain procedural concretization."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BindingScope(str, Enum):
    lab = "lab"
    external = "external"


class BindingValue(StrictModel):
    binding_id: str
    kind: str
    value: str
    source: str
    scope: BindingScope = BindingScope.lab
    secret_reference: bool = False

    @model_validator(mode="after")
    def validate_secret_reference(self) -> "BindingValue":
        if self.secret_reference and not self.value.startswith("secret://"):
            raise ValueError("secret bindings must contain a secret:// reference")
        return self


class BindingCatalog(StrictModel):
    schema_version: str = "1"
    sut_id: str
    source_sha256: str
    initial_facts: List[str] = Field(default_factory=list)
    goal_facts: List[str] = Field(default_factory=list)
    bindings: List[BindingValue] = Field(default_factory=list)
    content_sha256: str = ""

    def _computed_hash(self) -> str:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()

    def finalize_hash(self) -> None:
        self.content_sha256 = self._computed_hash()

    def validate_hash(self) -> bool:
        return bool(self.content_sha256) and self.content_sha256 == self._computed_hash()


class FidelityTier(str, Enum):
    """How closely a realization reproduces the documented behavior.

    faithful reproduces the documented product, version, and mechanism; adapted reproduces an
    equivalent mechanism inside the controlled laboratory; inspired only resembles the behavior
    conceptually and does not demonstrate reproduction of the original technique. The catalog
    deliberately tops out at adapted: a laboratory surrogate is never claimed as faithful.
    """

    faithful = "faithful"
    adapted = "adapted"
    inspired = "inspired"


class ActionTemplate(StrictModel):
    template_id: str
    technique_ids: List[str] = Field(min_length=1)
    execution_domain: str
    parameter_kinds: Dict[str, str] = Field(default_factory=dict)
    requires: List[str] = Field(default_factory=list)
    produces: List[str] = Field(min_length=1)
    evidence_predicates: List[str] = Field(min_length=1)
    # Kept as a plain string on purpose: the proposer is untrusted, so an out-of-bounds tier
    # must reach the verifier and be reported as a named violation rather than disappearing
    # into a parse error. FidelityTier is the canonical taxonomy the verifier enforces.
    fidelity_ceiling: str
    description: str


class ProcedureProposal(StrictModel):
    technique_id: str
    template_id: str
    bindings: Dict[str, str] = Field(default_factory=dict)
    rationale: str = ""
    source: str = "finite_domain_solver"


class VerificationIssue(StrictModel):
    code: str
    message: str


class CandidateAssessment(StrictModel):
    proposal: ProcedureProposal
    accepted: bool
    issues: List[VerificationIssue] = Field(default_factory=list)
    assumption_count: int = 0


class RetrievedTemplate(StrictModel):
    template_id: str
    score: int
    exact_technique_match: bool
    domain_match: bool
    shared_terms: List[str] = Field(default_factory=list)


class RetrievalTrace(StrictModel):
    technique_id: str
    query_sha256: str
    index_sha256: str
    candidates: List[RetrievedTemplate]


class ConcretizedStep(StrictModel):
    sequence: int
    technique_id: str
    template_id: str
    bindings: Dict[str, str]
    requires: List[str]
    produces: List[str]
    evidence_predicates: List[str]
    fidelity_ceiling: str
    proposal_source: str
    assumption_count: int


class CausalLink(StrictModel):
    fact_id: str
    producer_sequence: int
    consumer_sequence: int


class PlanningTransition(StrictModel):
    sequence: int
    technique_id: str
    state_before_sha256: str
    state_after_sha256: str
    added_facts: List[str]


class PlanningCertificate(StrictModel):
    initial_facts: List[str]
    goal_facts: List[str]
    transitions: List[PlanningTransition]
    causal_links: List[CausalLink]
    final_facts: List[str]
    unresolved_goals: List[str]
    valid: bool
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()


class ConcretizedPlan(StrictModel):
    schema_version: str = "1"
    ordering_policy: str = "causal_topological_then_source_order"
    campaign_id: str
    source_plan_sha256: str
    binding_catalog_sha256: str
    action_catalog_sha256: str
    steps: List[ConcretizedStep] = Field(default_factory=list)
    unresolved_technique_ids: List[str] = Field(default_factory=list)
    rejected_candidates: List[CandidateAssessment] = Field(default_factory=list)
    retrieval_traces: List[RetrievalTrace] = Field(default_factory=list)
    planning_certificate: Optional[PlanningCertificate] = None
    llm_call_sha256: Optional[str] = None
    execution_semantic_sha256: str = ""
    content_sha256: str = ""

    def finalize_hash(self) -> None:
        # The execution-semantic hash summarizes what is certified to run, so it covers only
        # the realized steps -- each step already inlines its template's requires, produces,
        # evidence predicates, and fidelity ceiling. The whole-catalog digest stays on
        # action_catalog_sha256 and inside content_sha256, which pin provenance; folding it in
        # here would couple a plan's semantics to templates it never retrieves.
        semantic_payload = {
            "campaign_id": self.campaign_id,
            "ordering_policy": self.ordering_policy,
            "source_plan_sha256": self.source_plan_sha256,
            "binding_catalog_sha256": self.binding_catalog_sha256,
            "steps": [
                {
                    "sequence": step.sequence,
                    "technique_id": step.technique_id,
                    "template_id": step.template_id,
                    "bindings": step.bindings,
                    "requires": step.requires,
                    "produces": step.produces,
                    "evidence_predicates": step.evidence_predicates,
                    "fidelity_ceiling": step.fidelity_ceiling,
                }
                for step in self.steps
            ],
            "unresolved_technique_ids": self.unresolved_technique_ids,
        }
        self.execution_semantic_sha256 = hashlib.sha256(
            json.dumps(semantic_payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        payload = self.model_dump(mode="json", exclude={"content_sha256"})
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        self.content_sha256 = hashlib.sha256(encoded).hexdigest()
