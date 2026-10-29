from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize(
    "script_name",
    (
        "screen_typed_evidence_privacy.py",
        "screen_c0045_series_privacy.py",
        "verify_c0045_effect_series_archive.py",
        "stage_typed_run_evidence.py",
        "create_typed_evidence_archive.py",
    ),
)
def test_privacy_screen_cli_help_runs_outside_artifact_root(
    script_name: str, tmp_path: Path
) -> None:
    completed = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / script_name), "--help"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "usage:" in completed.stdout
