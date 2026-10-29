import subprocess
import sys
from pathlib import Path

from runners.c0045_effect_series import SERIES_PATH

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_strict_runner_cli_bootstraps_from_an_external_directory(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/run_strict_c0045_effect_series.py"),
            "--help",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "strict live-lab preflight" in result.stdout
    assert "--cell-id" in result.stdout


def test_strict_runner_rejects_a_series_not_bound_by_the_profile(
    tmp_path: Path,
) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts/run_strict_c0045_effect_series.py"),
            "--output-dir",
            str(tmp_path / "receipts"),
            "--series-path",
            str(SERIES_PATH),
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "bound to a different frozen C0045 series" in result.stderr
    assert not (tmp_path / "receipts").exists()
