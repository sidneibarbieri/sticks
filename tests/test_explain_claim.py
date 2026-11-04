from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from explain_claim import canonical_claim_id, integrity_status  # noqa: E402

SCRIPT = PROJECT_ROOT / "scripts" / "explain_claim.py"
EVIDENCE = "release/experiments/prior_work_comparison/costaricto_paired.json"


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(SCRIPT), *arguments], capture_output=True, text=True, check=False)


def test_short_and_full_ids_name_the_same_claim() -> None:
    assert canonical_claim_id("p31") == canonical_claim_id("STICKS-P31") == "STICKS-P31"


def test_tampered_digest_is_reported_as_mismatch() -> None:
    assert integrity_status(EVIDENCE, {EVIDENCE: "0" * 64}) == "SHA256 MISMATCH"
    assert integrity_status("release/absent.json", {}) == "MISSING"


def test_known_claim_prints_scope_evidence_and_test_command() -> None:
    result = run("P31")
    assert result.returncode == 0
    assert "Scope" in result.stdout and f"[sha256 ok] {EVIDENCE}" in result.stdout
    assert "python3 -m pytest -q tests/test_prior_work_costaricto.py" in result.stdout


def test_unknown_claim_lists_registered_ids() -> None:
    result = run("P99")
    assert result.returncode == 2 and "P31" in result.stderr
