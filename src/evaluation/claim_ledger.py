"""Claim ledger: registered properties, their evidence chain, and the wording they permit.

The model claims properties. Each registered property declares the evidence records that
carry its numbers, the tests that exercise the code producing them, the kind of support it
rests on, and the wording the manuscript may and may not use. Making that a data structure
rather than a convention means an unsupported property fails a check instead of surviving
review by inattention.

Support type matters when reading a property: an implementation invariant and a corpus
measurement are both evidence, but they answer different questions, and the ledger keeps
them distinguishable rather than letting a unit test stand in for an empirical result.

Two checks are separate and both necessary. ``verify_ledger`` confirms each registered
property's evidence and tests exist. ``audit_manuscript`` confirms the manuscript cites only
registered properties, never a blocked one, and never uses wording a property forbids.
Chain integrity is not scientific validity: a property can be well-formed and still be
wrong, which is what the evidence and tests are for.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from evaluation.claim_numerals import (
    ClaimQuantity,
    NumeralAudit,
    NumericExemption,
    audit_numerals,
)


class ClaimStatus(str, Enum):
    supported = "supported"
    limited = "limited"
    blocked = "blocked"


class SupportType(str, Enum):
    implementation_invariant = "implementation_invariant"
    controlled_experiment = "controlled_experiment"
    corpus_measurement = "corpus_measurement"
    manual_validation = "manual_validation"
    formal_argument = "formal_argument"


class PaperReadinessGateKind(str, Enum):
    """Additional evidence required before a structurally complete claim reaches prose."""

    independent_adjudication = "independent_adjudication"
    prospective_requalification = "prospective_requalification"


class PaperReadinessGate(BaseModel):
    """A versioned external qualification boundary for a claim.

    The ledger keeps the generic contract deliberately small.  The experiment-specific
    evaluator validates the contents of the status record; this layer binds the result to a
    claim and refuses to infer paper readiness from file existence alone.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: PaperReadinessGateKind
    protocol_path: str
    status_path: str
    required_status: str


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    claim_id: str
    statement: str
    status: ClaimStatus
    support_type: SupportType
    unit_of_analysis: str | None = None
    population: str | None = None
    table_population: str | None = None
    evidence_paths: list[str] = Field(default_factory=list)
    test_paths: list[str] = Field(default_factory=list)
    permitted_wording: str | None = None
    forbidden_wording: list[str] = Field(default_factory=list)
    scope_restriction: str | None = None
    paper_readiness_gate: PaperReadinessGate | None = None
    quantities: list[ClaimQuantity] = Field(default_factory=list)
    numeric_exemptions: list[NumericExemption] = Field(default_factory=list)


class ClaimVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim_id: str
    status: ClaimStatus
    support_type: SupportType
    missing_evidence: list[str]
    missing_tests: list[str]
    chain_complete: bool
    readiness_gate_status: str | None = None
    readiness_blockers: list[str] = Field(default_factory=list)
    paper_ready: bool


class LedgerReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_claims: int
    supported: int
    limited: int
    blocked: int
    verifications: list[ClaimVerification]
    incomplete_chains: list[str]


class ManuscriptAudit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    referenced_claim_ids: list[str]
    unregistered_references: list[str]
    blocked_references: list[str]
    unready_references: list[str]
    unreferenced_paper_ready_claim_ids: list[str]
    forbidden_phrases_used: list[str]
    semantic_policy_violations: list[str]
    clean: bool


CLAIM_REFERENCE_PATTERN = re.compile(r"\\claimref\{([^}]+)\}")

# These guards cover legacy empirical claims that are not registered in the property
# ledger.  They are deliberately narrow: the audit should reject a concrete unsupported
# result, not ordinary background discussion about replay or human analysis.
SEMANTIC_GUARD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "legacy-eight-workflow completion claim",
        re.compile(
            r"\ball\s+(?:eight|8)\s+(?:curated\s+)?(?:adversaries|workflows)\b"
            r".{0,160}\b(?:reach|reached)\s+(?:an\s+)?explicit\s+end",
        ),
    ),
    (
        "legacy 109-link execution result",
        re.compile(
            r"\b(?:total\s+)?(?:successful\s+link\s+count\s+is\s+109|109\s+successful\s+links)\b"
        ),
    ),
    (
        "legacy eight-workflow replay claim",
        re.compile(r"\breplays?\s+the\s+frozen\s+(?:eight|8)\s+workflow\s+package\b"),
    ),
    (
        "manual Stage 2 is presented as the primary reconstruction method",
        re.compile(r"\bstage\s+2\b.{0,180}\b(?:analyst|manual)\s+validation\b"),
    ),
    (
        "legacy Docker workflow breadth claim",
        re.compile(
            r"\bdocker\s+artifact\b.{0,120}\b(?:eight|8)\s+curated\s+(?:adversary\s+)?workflows\b"
        ),
    ),
)


def _normalize_prose(text: str) -> str:
    """Normalize prose so punctuation and LaTeX spacing cannot bypass wording checks."""
    lowered = text.lower().replace("~", " ")
    lowered = re.sub(r"\\(?:emph|texttt|textbf|textit)\{([^{}]*)\}", r"\1", lowered)
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return " ".join(lowered.split())


def _missing(project_root: Path, relative_paths: list[str]) -> list[str]:
    return [path for path in relative_paths if not (project_root / path).exists()]


def _evaluate_readiness_gate(project_root: Path, claim: Claim) -> tuple[str | None, list[str]]:
    """Read a typed gate result without treating a pending record as claim evidence."""

    gate = claim.paper_readiness_gate
    if gate is None:
        return None, []
    protocol_path = project_root / gate.protocol_path
    status_path = project_root / gate.status_path
    blockers: list[str] = []
    if not protocol_path.is_file():
        blockers.append(f"missing_protocol:{gate.protocol_path}")
    if not status_path.is_file():
        blockers.append(f"missing_status:{gate.status_path}")
        return None, blockers
    try:
        payload = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return None, [*blockers, f"invalid_status:{gate.status_path}:{error.__class__.__name__}"]
    if payload.get("claim_id") != claim.claim_id:
        blockers.append(f"wrong_claim_id:{gate.status_path}")
    status = payload.get("status")
    if not isinstance(status, str):
        blockers.append(f"missing_gate_status:{gate.status_path}")
        return None, blockers
    if status != gate.required_status:
        blockers.append(f"required_{gate.required_status}_got_{status}")
    if payload.get("paper_eligible") is not (status == gate.required_status):
        blockers.append(f"inconsistent_paper_eligibility:{gate.status_path}")
    if gate.kind is PaperReadinessGateKind.prospective_requalification and status == gate.required_status:
        blockers.append("prospective_qualification_validator_missing")
    return status, blockers


def verify_claim(project_root: Path, claim: Claim) -> ClaimVerification:
    # A blocked claim carries no evidence by design; it is registered so the manuscript can
    # be audited against it.
    if claim.status is ClaimStatus.blocked:
        return ClaimVerification(
            claim_id=claim.claim_id,
            status=claim.status,
            support_type=claim.support_type,
            missing_evidence=[],
            missing_tests=[],
            chain_complete=True,
            readiness_gate_status=None,
            readiness_blockers=[],
            paper_ready=False,
        )

    missing_evidence = _missing(project_root, claim.evidence_paths)
    missing_tests = _missing(project_root, claim.test_paths)
    chain_complete = (
        not missing_evidence
        and not missing_tests
        and bool(claim.evidence_paths)
        and bool(claim.test_paths)
    )
    gate_status, gate_blockers = _evaluate_readiness_gate(project_root, claim)
    eligible_without_gate = claim.status is ClaimStatus.supported and claim.paper_readiness_gate is None
    gate_is_qualified = claim.paper_readiness_gate is not None and not gate_blockers
    return ClaimVerification(
        claim_id=claim.claim_id,
        status=claim.status,
        support_type=claim.support_type,
        missing_evidence=missing_evidence,
        missing_tests=missing_tests,
        chain_complete=chain_complete,
        readiness_gate_status=gate_status,
        readiness_blockers=gate_blockers,
        paper_ready=chain_complete and (eligible_without_gate or gate_is_qualified),
    )


def verify_ledger(project_root: Path, claims: list[Claim]) -> LedgerReport:
    verifications = [verify_claim(project_root, claim) for claim in claims]
    by_status = {status: 0 for status in ClaimStatus}
    for claim in claims:
        by_status[claim.status] += 1
    return LedgerReport(
        total_claims=len(claims),
        supported=by_status[ClaimStatus.supported],
        limited=by_status[ClaimStatus.limited],
        blocked=by_status[ClaimStatus.blocked],
        verifications=verifications,
        incomplete_chains=[
            verification.claim_id
            for verification in verifications
            if not verification.chain_complete
        ],
    )


def audit_manuscript(
    manuscript_text: str,
    claims: list[Claim],
    *,
    require_all_paper_ready: bool = False,
    paper_ready_claim_ids: set[str] | None = None,
) -> ManuscriptAudit:
    """Check that the manuscript cites registered properties and respects their wording."""
    registered = {claim.claim_id: claim for claim in claims}
    referenced = sorted(set(CLAIM_REFERENCE_PATTERN.findall(manuscript_text)))

    unregistered = [ref for ref in referenced if ref not in registered]
    blocked = [
        ref
        for ref in referenced
        if ref in registered and registered[ref].status is ClaimStatus.blocked
    ]
    default_paper_ready = {
        claim.claim_id
        for claim in claims
        if claim.status is ClaimStatus.supported and claim.paper_readiness_gate is None
    }
    eligible_claim_ids = paper_ready_claim_ids if paper_ready_claim_ids is not None else default_paper_ready
    unready = [
        ref
        for ref in referenced
        if ref in registered
        and registered[ref].status is not ClaimStatus.blocked
        and ref not in eligible_claim_ids
    ]
    unreferenced = (
        sorted(
            claim_id for claim_id in eligible_claim_ids if claim_id not in referenced
        )
        if require_all_paper_ready
        else []
    )
    normalized_manuscript = _normalize_prose(manuscript_text)
    forbidden_used = [
        phrase
        for claim in claims
        for phrase in claim.forbidden_wording
        if _normalize_prose(phrase) in normalized_manuscript
    ]
    semantic_violations = [
        label for label, pattern in SEMANTIC_GUARD_PATTERNS if pattern.search(normalized_manuscript)
    ]
    return ManuscriptAudit(
        referenced_claim_ids=referenced,
        unregistered_references=unregistered,
        blocked_references=blocked,
        unready_references=unready,
        unreferenced_paper_ready_claim_ids=unreferenced,
        forbidden_phrases_used=sorted(set(forbidden_used)),
        semantic_policy_violations=sorted(set(semantic_violations)),
        clean=not (
            unregistered or blocked or unready or unreferenced or forbidden_used or semantic_violations
        ),
    )


PROSE_FIELDS = ("statement", "population", "table_population", "permitted_wording")


def audit_ledger_numerals(project_root: Path, claims: list[Claim]) -> list[NumeralAudit]:
    """Check every non-blocked property's stated numbers against its own evidence.

    A blocked property is excluded because it asserts nothing the manuscript may use.
    """
    return [
        audit_numerals(
            claim_id=claim.claim_id,
            prose=[getattr(claim, field) for field in PROSE_FIELDS],
            quantities=claim.quantities,
            exemptions=claim.numeric_exemptions,
            evidence_paths=claim.evidence_paths,
            project_root=project_root,
        )
        for claim in claims
        if claim.status is not ClaimStatus.blocked
    ]
