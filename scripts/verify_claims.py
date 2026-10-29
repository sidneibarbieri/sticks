#!/usr/bin/env python3
"""Verify that every claim in the ledger has a complete chain to frozen evidence.

Reads release/claims/ledger.json and checks, for each claim the artifact asserts, that its
declared evidence records and tests exist. Exits non-zero when any chain is incomplete, so a
claim cannot reach the manuscript on a broken or missing chain. Blocked claims are reported
so the manuscript can be checked against them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from evaluation.claim_ledger import (  # noqa: E402
    Claim,
    ClaimStatus,
    audit_ledger_numerals,
    audit_manuscript,
    verify_ledger,
)

DEFAULT_LEDGER = PROJECT_ROOT / "release" / "claims" / "ledger.json"
DEFAULT_REPORT = PROJECT_ROOT / "release" / "claims" / "verification.json"
DEFAULT_INTEGRITY_MANIFEST = PROJECT_ROOT / "release" / "claims" / "evidence_sha256.json"
DERIVED_REPORT_PATHS = frozenset({DEFAULT_REPORT.resolve()})


def load_claims(ledger_path: Path) -> list[Claim]:
    payload = json.loads(ledger_path.read_text(encoding="utf-8"))
    return [Claim.model_validate(item) for item in payload["claims"]]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _integrity_paths(claims: list[Claim], manifest_path: Path) -> list[str]:
    excluded_paths = {manifest_path.resolve(), *DERIVED_REPORT_PATHS}
    paths = {
        relative_path
        for claim in claims
        if claim.status is not ClaimStatus.blocked
        for relative_path in claim.evidence_paths + claim.test_paths
        if (PROJECT_ROOT / relative_path).resolve() not in excluded_paths
    }
    return sorted(paths)


def _write_integrity_manifest(path: Path, claims: list[Claim]) -> None:
    files = {
        relative_path: _sha256(PROJECT_ROOT / relative_path)
        for relative_path in _integrity_paths(claims, path)
    }
    payload = {
        "schema_version": "1",
        "algorithm": "sha256",
        "files": files,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _verify_integrity_manifest(path: Path, claims: list[Claim]) -> int:
    if not path.is_file():
        raise SystemExit(f"[claims] missing integrity manifest: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1" or payload.get("algorithm") != "sha256":
        raise SystemExit("[claims] unsupported integrity-manifest schema")
    expected_files = payload.get("files")
    if not isinstance(expected_files, dict):
        raise SystemExit("[claims] integrity manifest has no file map")

    required_paths = _integrity_paths(claims, path)
    omitted = sorted(set(required_paths) - set(expected_files))
    unregistered = sorted(set(expected_files) - set(required_paths))
    mismatches: list[str] = []
    for relative_path in required_paths:
        artifact_path = PROJECT_ROOT / relative_path
        if not artifact_path.is_file():
            mismatches.append(f"missing:{relative_path}")
            continue
        if expected_files.get(relative_path) != _sha256(artifact_path):
            mismatches.append(f"sha256:{relative_path}")

    problems = [
        *(f"omitted:{relative_path}" for relative_path in omitted),
        *(f"unregistered:{relative_path}" for relative_path in unregistered),
        *mismatches,
    ]
    if problems:
        for problem in problems:
            print(f"      integrity: {problem}")
        raise SystemExit("[claims] frozen evidence integrity check failed")
    return len(required_paths)


def _audit_ledger_numerals(claims: list[Claim]) -> int:
    """Fail when a property states a number its own evidence no longer produces."""
    audits = audit_ledger_numerals(PROJECT_ROOT, claims)
    failed = [audit for audit in audits if not audit.clean]
    for audit in failed:
        for literal in audit.unbound_literals:
            print(f"      numeral {audit.claim_id}: {literal} is not produced by its evidence")
        for mismatch in audit.quantity_mismatches:
            print(f"      numeral {audit.claim_id}: declared {mismatch}")
        for literal in audit.unused_declarations:
            print(f"      numeral {audit.claim_id}: declared {literal} appears in no prose field")
    if failed:
        raise SystemExit("[claims] ledger numeral audit failed")
    return len(audits)


def _audit_manuscript_file(
    manuscript: Path,
    claims: list[Claim],
    paper_ready_claim_ids: set[str],
) -> None:
    audit = audit_manuscript(
        manuscript.read_text(encoding="utf-8"),
        claims,
        require_all_paper_ready=True,
        paper_ready_claim_ids=paper_ready_claim_ids,
    )
    print(
        f"[claims] manuscript {manuscript.name}: "
        f"{len(audit.referenced_claim_ids)} referenced properties"
    )
    for unregistered in audit.unregistered_references:
        print(f"      unregistered reference: {unregistered}")
    for blocked in audit.blocked_references:
        print(f"      blocked property cited: {blocked}")
    for unready in audit.unready_references:
        print(f"      unready property cited: {unready}")
    for missing in audit.unreferenced_paper_ready_claim_ids:
        print(f"      registered property not referenced: {missing}")
    for phrase in audit.forbidden_phrases_used:
        print(f"      forbidden wording: {phrase}")
    for violation in audit.semantic_policy_violations:
        print(f"      semantic policy violation: {violation}")
    if not audit.clean:
        raise SystemExit("[claims] manuscript audit failed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--integrity-manifest",
        type=Path,
        default=DEFAULT_INTEGRITY_MANIFEST,
    )
    parser.add_argument(
        "--write-integrity-manifest",
        action="store_true",
        help="maintainer action: replace the frozen SHA-256 manifest with current files",
    )
    parser.add_argument(
        "--manuscript",
        type=Path,
        help="LaTeX source to audit against the ledger (claimref usage and wording).",
    )
    args = parser.parse_args()

    claims = load_claims(args.ledger)
    report = verify_ledger(PROJECT_ROOT, claims)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    if args.write_integrity_manifest:
        _write_integrity_manifest(args.integrity_manifest, claims)
        print(f"[claims] wrote integrity manifest: {args.integrity_manifest}")

    for verification in report.verifications:
        if verification.status is ClaimStatus.blocked:
            marker = "BLOCKED  "
        elif verification.paper_ready:
            marker = "ok       "
        elif verification.status is ClaimStatus.limited:
            marker = "LIMITED  "
        elif verification.chain_complete:
            marker = "GATED    "
        else:
            marker = "INCOMPLETE"
        print(f"  {marker} {verification.claim_id} ({verification.status.value})")
        for missing in verification.missing_evidence + verification.missing_tests:
            print(f"      missing: {missing}")
        for blocker in verification.readiness_blockers:
            print(f"      readiness: {blocker}")

    print(
        f"[claims] {report.total_claims} claims: {report.supported} supported, "
        f"{report.limited} limited, {report.blocked} blocked"
    )
    if report.incomplete_chains:
        raise SystemExit(
            f"[claims] incomplete evidence chains: {', '.join(report.incomplete_chains)}"
        )
    print("[claims] every registered property has a complete evidence chain")

    integrity_count = _verify_integrity_manifest(args.integrity_manifest, claims)
    print(f"[claims] verified SHA-256 for {integrity_count} evidence and test files")

    numeral_count = _audit_ledger_numerals(claims)
    print(f"[claims] every number stated by {numeral_count} properties is bound to its evidence")

    if args.manuscript:
        _audit_manuscript_file(
            args.manuscript,
            claims,
            {
                verification.claim_id
                for verification in report.verifications
                if verification.paper_ready
            },
        )
        print("[claims] manuscript cites only registered properties and permitted wording")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
