from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from verify_claims import (  # noqa: E402
    DEFAULT_INTEGRITY_MANIFEST,
    DEFAULT_LEDGER,
    DEFAULT_REPORT,
    _integrity_paths,
    _verify_integrity_manifest,
    load_claims,
)


def test_frozen_claim_evidence_matches_sha256_manifest() -> None:
    claims = load_claims(DEFAULT_LEDGER)
    checked = _verify_integrity_manifest(DEFAULT_INTEGRITY_MANIFEST, claims)

    assert checked == len(_integrity_paths(claims, DEFAULT_INTEGRITY_MANIFEST))
    assert checked > 0


def test_integrity_manifest_excludes_regenerated_verification_report() -> None:
    claims = load_claims(DEFAULT_LEDGER)

    assert "release/claims/verification.json" not in _integrity_paths(
        claims, DEFAULT_INTEGRITY_MANIFEST
    )
    assert DEFAULT_REPORT.is_file()
