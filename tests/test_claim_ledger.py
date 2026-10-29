from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from evaluation.claim_ledger import (  # noqa: E402
    Claim,
    ClaimStatus,
    PaperReadinessGate,
    PaperReadinessGateKind,
    SupportType,
    audit_manuscript,
    verify_claim,
    verify_ledger,
)
from verify_claims import DEFAULT_LEDGER, load_claims  # noqa: E402

BLOCKED_CLAIM_IDS = ("STICKS-B01", "STICKS-B02", "STICKS-B03", "STICKS-B04")


def test_registered_property_without_evidence_is_not_paper_ready():
    claim = Claim(
        claim_id="STICKS-X01",
        statement="a property with no evidence",
        status=ClaimStatus.supported,
        support_type=SupportType.corpus_measurement,
    )
    verification = verify_claim(PROJECT_ROOT, claim)
    assert verification.chain_complete is False
    assert verification.paper_ready is False


def test_property_with_missing_evidence_file_is_reported():
    claim = Claim(
        claim_id="STICKS-X02",
        statement="a property pointing at a file that does not exist",
        status=ClaimStatus.supported,
        support_type=SupportType.corpus_measurement,
        evidence_paths=["release/experiments/does_not_exist.json"],
        test_paths=["tests/test_claim_ledger.py"],
    )
    verification = verify_claim(PROJECT_ROOT, claim)
    assert verification.missing_evidence == ["release/experiments/does_not_exist.json"]
    assert verification.paper_ready is False


def test_blocked_property_is_never_paper_ready():
    claim = Claim(
        claim_id="STICKS-X03",
        statement="a property the artifact does not support",
        status=ClaimStatus.blocked,
        support_type=SupportType.manual_validation,
    )
    verification = verify_claim(PROJECT_ROOT, claim)
    assert verification.paper_ready is False
    # It still verifies structurally so the manuscript can be audited against it.
    assert verification.chain_complete is True


def test_real_ledger_has_no_incomplete_chains():
    report = verify_ledger(PROJECT_ROOT, load_claims(DEFAULT_LEDGER))
    assert report.incomplete_chains == []
    assert report.total_claims > 0


def test_real_ledger_blocks_the_properties_the_artifact_cannot_support():
    claims = {claim.claim_id: claim for claim in load_claims(DEFAULT_LEDGER)}
    for claim_id in BLOCKED_CLAIM_IDS:
        assert claims[claim_id].status is ClaimStatus.blocked


def test_asserted_properties_declare_wording_and_population():
    for claim in load_claims(DEFAULT_LEDGER):
        if claim.status is ClaimStatus.blocked:
            assert claim.scope_restriction, (
                f"{claim.claim_id} lacks a scope restriction"
            )
            continue
        assert claim.permitted_wording, f"{claim.claim_id} lacks permitted wording"
        assert claim.forbidden_wording, f"{claim.claim_id} lacks forbidden wording"
        assert claim.population, f"{claim.claim_id} lacks a population"


def test_manuscript_audit_rejects_a_blocked_reference():
    claims = load_claims(DEFAULT_LEDGER)
    audit = audit_manuscript(r"We show \claimref{STICKS-B02} holds.", claims)
    assert audit.blocked_references == ["STICKS-B02"]
    assert audit.clean is False


def test_manuscript_audit_rejects_forbidden_wording():
    claims = load_claims(DEFAULT_LEDGER)
    audit = audit_manuscript(
        "Our system achieves deterministic reconstruction of adversary behavior.",
        claims,
    )
    assert audit.forbidden_phrases_used
    assert audit.clean is False


def test_manuscript_audit_rejects_an_unregistered_reference():
    claims = load_claims(DEFAULT_LEDGER)
    audit = audit_manuscript(r"See \claimref{STICKS-P99}.", claims)
    assert audit.unregistered_references == ["STICKS-P99"]
    assert audit.clean is False


def test_manuscript_audit_accepts_a_registered_property_with_permitted_wording():
    claims = load_claims(DEFAULT_LEDGER)
    audit = audit_manuscript(
        r"Admission is deterministic under a fixed catalog \claimref{STICKS-P01}.",
        claims,
    )
    assert audit.clean is True
    assert audit.referenced_claim_ids == ["STICKS-P01"]


def test_manuscript_audit_normalizes_latex_and_hyphenation():
    claims = load_claims(DEFAULT_LEDGER)
    audit = audit_manuscript(
        r"We provide deterministic-reconstruction of \emph{adversary behavior}.",
        claims,
    )
    assert audit.forbidden_phrases_used
    assert audit.clean is False


def test_manuscript_audit_rejects_legacy_execution_result_semantically():
    claims = load_claims(DEFAULT_LEDGER)
    audit = audit_manuscript(
        "The broader audit reports 109 successful links on the shared substrate.",
        claims,
    )
    assert "legacy 109-link execution result" in audit.semantic_policy_violations
    assert audit.clean is False


def test_strict_manuscript_audit_requires_every_paper_ready_property_reference():
    claims = load_claims(DEFAULT_LEDGER)
    audit = audit_manuscript(
        r"Admission is deterministic \claimref{STICKS-P01}.",
        claims,
        require_all_paper_ready=True,
    )
    assert "STICKS-P02" in audit.unreferenced_paper_ready_claim_ids
    assert audit.clean is False


def test_pending_p16_adjudication_is_not_required_in_the_manuscript():
    claims = load_claims(DEFAULT_LEDGER)
    report = verify_ledger(PROJECT_ROOT, claims)
    p16 = next(
        verification
        for verification in report.verifications
        if verification.claim_id == "STICKS-P16"
    )
    assert p16.status is ClaimStatus.limited
    assert p16.paper_ready is False
    audit = audit_manuscript(
        r"Admission is deterministic \claimref{STICKS-P01}.",
        claims,
        require_all_paper_ready=True,
        paper_ready_claim_ids={
            verification.claim_id
            for verification in report.verifications
            if verification.paper_ready
        },
    )
    assert "STICKS-P16" not in audit.unreferenced_paper_ready_claim_ids


def test_blocked_p17_cannot_reach_manuscript_readiness():
    claims = load_claims(DEFAULT_LEDGER)
    report = verify_ledger(PROJECT_ROOT, claims)
    p17 = next(
        verification
        for verification in report.verifications
        if verification.claim_id == "STICKS-P17"
    )
    assert p17.status is ClaimStatus.blocked
    assert p17.readiness_gate_status is None
    assert p17.paper_ready is False
    assert p17.readiness_blockers == []
    audit = audit_manuscript(
        r"Historical proposal rates \claimref{STICKS-P17}.",
        claims,
        paper_ready_claim_ids={
            verification.claim_id
            for verification in report.verifications
            if verification.paper_ready
        },
    )
    assert audit.blocked_references == ["STICKS-P17"]
    assert audit.clean is False


def test_qemu_workflow_outcomes_are_registered_and_paper_bound():
    claims = {claim.claim_id: claim for claim in load_claims(DEFAULT_LEDGER)}
    claim = claims["STICKS-P26"]
    assert claim.evidence_paths == [
        "release/experiments/typed_campaign_outcomes/C0010.final_run_receipt.json",
        "release/experiments/typed_campaign_outcomes/C0026.final_run_receipt.json",
    ]

    verification = verify_claim(PROJECT_ROOT, claim)
    assert verification.paper_ready is True

    manuscript_path = PROJECT_ROOT.parent / "paper" / "main.tex"
    if not manuscript_path.is_file():
        pytest.skip("paper source is intentionally outside the reviewer artifact")
    manuscript = manuscript_path.read_text(encoding="utf-8")
    assert r"\claimref{STICKS-P26}" in manuscript


def test_p17_status_label_cannot_self_qualify(tmp_path: Path):
    protocol = tmp_path / "protocol.md"
    status = tmp_path / "status.json"
    evidence = tmp_path / "evidence.json"
    test_path = tmp_path / "test.txt"
    protocol.write_text("prospective protocol", encoding="utf-8")
    status.write_text(
        json.dumps(
            {"claim_id": "STICKS-X17", "status": "qualified", "paper_eligible": True}
        ),
        encoding="utf-8",
    )
    evidence.write_text("{}", encoding="utf-8")
    test_path.write_text("test placeholder", encoding="utf-8")
    claim = Claim(
        claim_id="STICKS-X17",
        statement="prospective comparison",
        status=ClaimStatus.supported,
        support_type=SupportType.controlled_experiment,
        evidence_paths=["evidence.json"],
        test_paths=["test.txt"],
        paper_readiness_gate=PaperReadinessGate(
            kind=PaperReadinessGateKind.prospective_requalification,
            protocol_path="protocol.md",
            status_path="status.json",
            required_status="qualified",
        ),
    )
    verification = verify_claim(tmp_path, claim)
    assert verification.paper_ready is False
    assert (
        "prospective_qualification_validator_missing" in verification.readiness_blockers
    )


def test_qualified_independent_adjudication_can_promote_a_limited_claim(tmp_path: Path):
    protocol = tmp_path / "protocol.json"
    status = tmp_path / "status.json"
    evidence = tmp_path / "evidence.json"
    test_path = tmp_path / "test.txt"
    protocol.write_text("{}", encoding="utf-8")
    status.write_text(
        json.dumps(
            {
                "claim_id": "STICKS-X04",
                "status": "qualified",
                "paper_eligible": True,
            }
        ),
        encoding="utf-8",
    )
    evidence.write_text("{}", encoding="utf-8")
    test_path.write_text("test placeholder", encoding="utf-8")
    claim = Claim(
        claim_id="STICKS-X04",
        statement="a limited property awaiting independent adjudication",
        status=ClaimStatus.limited,
        support_type=SupportType.corpus_measurement,
        evidence_paths=["evidence.json"],
        test_paths=["test.txt"],
        paper_readiness_gate=PaperReadinessGate(
            kind=PaperReadinessGateKind.independent_adjudication,
            protocol_path="protocol.json",
            status_path="status.json",
            required_status="qualified",
        ),
    )
    verification = verify_claim(tmp_path, claim)
    assert verification.paper_ready is True
    assert verification.readiness_blockers == []
