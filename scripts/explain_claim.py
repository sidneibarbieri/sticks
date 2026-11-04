#!/usr/bin/env python3
"""Show one ledger claim with its scope, evidence integrity, and test command.

The paper's claim map (Appendix) lists each property by its short ID. This command
answers the reviewer's next question for one of them: what exactly is asserted, over
which population, which frozen records support it, whether those records still match
the pinned SHA-256 manifest, and which tests check it.

Usage:
    python3 scripts/explain_claim.py P31
    python3 scripts/explain_claim.py STICKS-P31 --run-tests
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import textwrap
from pathlib import Path

from verify_claims import DEFAULT_INTEGRITY_MANIFEST, DEFAULT_LEDGER, PROJECT_ROOT, _sha256, load_claims

CLAIM_PREFIX = "STICKS-"
WRAP_WIDTH = 78


def canonical_claim_id(requested: str) -> str:
    claim_id = requested.strip().upper()
    return claim_id if claim_id.startswith(CLAIM_PREFIX) else CLAIM_PREFIX + claim_id


def integrity_status(relative_path: str, pinned_digests: dict[str, str]) -> str:
    path = PROJECT_ROOT / relative_path
    if not path.is_file():
        return "MISSING"
    if relative_path not in pinned_digests:
        return "not pinned"
    return "sha256 ok" if _sha256(path) == pinned_digests[relative_path] else "SHA256 MISMATCH"


def wrapped(label: str, text: str) -> str:
    return textwrap.fill(text, WRAP_WIDTH, initial_indent=f"{label:<11}", subsequent_indent=" " * 11)


def render(claim, pinned_digests: dict[str, str]) -> tuple[str, bool]:
    lines = [f"{claim.claim_id}   status: {claim.status.value}   support: {claim.support_type.value}", ""]
    lines.append(wrapped("Statement", claim.statement))
    if claim.scope_restriction:
        lines.append(wrapped("Scope", claim.scope_restriction))
    if claim.population:
        lines.append(wrapped("Population", claim.population))
    lines += ["", "Evidence"]
    intact = True
    for relative_path in claim.evidence_paths:
        status = integrity_status(relative_path, pinned_digests)
        intact &= status in {"sha256 ok", "not pinned"}
        lines.append(f"  [{status}] {relative_path}")
    lines += ["", "Tests"]
    lines += [f"  {relative_path}" for relative_path in claim.test_paths] or ["  none registered"]
    if claim.test_paths:
        lines += ["", "Run them with:", f"  python3 -m pytest -q {' '.join(claim.test_paths)}"]
    return "\n".join(lines), intact


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("claim", help="claim ID as printed in the claim map, e.g. P31")
    parser.add_argument("--run-tests", action="store_true", help="also run the claim's registered tests")
    args = parser.parse_args()

    claims = {claim.claim_id: claim for claim in load_claims(DEFAULT_LEDGER)}
    claim_id = canonical_claim_id(args.claim)
    if claim_id not in claims:
        known = ", ".join(sorted(identifier.removeprefix(CLAIM_PREFIX) for identifier in claims))
        print(f"unknown claim {args.claim!r}; the ledger registers: {known}", file=sys.stderr)
        return 2
    pinned_digests = json.loads(DEFAULT_INTEGRITY_MANIFEST.read_text(encoding="utf-8"))["files"]
    report, intact = render(claims[claim_id], pinned_digests)
    print(report, flush=True)
    if not intact:
        return 1
    if args.run_tests and claims[claim_id].test_paths:
        return subprocess.run([sys.executable, "-m", "pytest", "-q", *claims[claim_id].test_paths],
                              cwd=PROJECT_ROOT, check=False).returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
