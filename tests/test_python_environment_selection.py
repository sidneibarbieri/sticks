"""Check explicit reviewer interpreter selection without installing dependencies."""

import os
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/python_env.sh"


def resolve_python(root: Path, requested: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ, STICKS_PYTHON=requested)
    return subprocess.run(
        ["bash", "-c", 'source "$1"; sticks_resolve_python "$2"',
         "selection-test", str(SCRIPT), str(root)],
        env=environment, capture_output=True, text=True, check=False,
    )


def test_explicit_interpreter_wins_over_repository_environment(tmp_path: Path) -> None:
    repository_python = tmp_path / ".venv/bin/python3"
    repository_python.parent.mkdir(parents=True)
    repository_python.symlink_to(sys.executable)
    environment_alias = tmp_path / "selected environment"
    environment_alias.symlink_to(Path(sys.executable).parent.parent, target_is_directory=True)
    requested = environment_alias / "bin" / Path(sys.executable).name
    result = resolve_python(tmp_path, str(requested))
    assert result.returncode == 0
    assert result.stdout.strip() == str(requested)
    assert result.stderr == ""


def test_missing_override_fails_without_fallback_or_install(tmp_path: Path) -> None:
    requested = tmp_path / "missing-python"
    result = resolve_python(tmp_path, str(requested))
    assert result.returncode != 0
    assert result.stdout == ""
    assert "STICKS_PYTHON" in result.stderr
    assert not (tmp_path / ".venv").exists()


def test_incomplete_override_preserves_import_error(tmp_path: Path) -> None:
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(tmp_path / "bare")],
                   check=True, capture_output=True, text=True)
    result = resolve_python(tmp_path, str(tmp_path / "bare/bin/python3"))
    assert result.returncode != 0
    assert "ModuleNotFoundError" in result.stderr
    assert "pydantic" in result.stderr
    assert result.stdout == ""
    assert not (tmp_path / ".venv").exists()


def test_default_repository_environment_selection_is_preserved(tmp_path: Path) -> None:
    (tmp_path / ".venv").symlink_to(Path(sys.executable).parent.parent, target_is_directory=True)
    result = resolve_python(tmp_path, "")
    assert result.returncode == 0
    assert result.stdout.strip() == str(tmp_path / ".venv/bin/python3")
    assert result.stderr == ""
