from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_demo_runs_offline_and_shows_the_contrast():
    # The demo is what a reviewer runs first, so a break here is as serious as a failing claim.
    result = subprocess.run(
        [sys.executable, "scripts/demo.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    output = result.stdout
    assert "REJECTED by the oracle" in output
    assert "abstains rather than emit an unexecutable step" in output
    assert "Admission decides executable validity" in output


def test_demo_reports_the_recorded_totals():
    result = subprocess.run(
        [sys.executable, "scripts/demo.py"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    # The printed rates must be the recorded ones, not numbers written into the script.
    assert "375 observations" in result.stdout
    assert "1.000" in result.stdout
