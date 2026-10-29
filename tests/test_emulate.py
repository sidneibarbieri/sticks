from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _emulate(campaign: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "scripts/emulate.py", campaign],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=600,
    )


def test_emulates_a_fully_supported_campaign_offline():
    result = _emulate("C0045")
    assert result.returncode == 0, result.stderr
    assert "the finite-domain solver, offline" in result.stdout
    assert "admitted 10 of 10 steps" in result.stdout


def test_abstains_rather_than_inventing_on_an_unsupported_campaign():
    # A reviewer will pick a campaign the catalog does not cover. The command must say so
    # per step instead of filling the gap, which is the property the paper claims.
    result = _emulate("C0001")
    assert result.returncode == 0, result.stderr
    assert "no admissible realization in the catalog" in result.stdout
    assert "left unresolved" in result.stdout


def test_rejects_a_missing_provider_configuration():
    result = subprocess.run(
        [sys.executable, "scripts/emulate.py", "C0045", "--config", "does-not-exist.json"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode != 0
    assert "provider configuration not found" in result.stderr
