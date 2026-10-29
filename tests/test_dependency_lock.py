from __future__ import annotations

import re
import tomllib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXACT_REQUIREMENT = re.compile(r"^[A-Za-z0-9_.-]+==[^=<>!~\s]+$")


def _locked_versions() -> dict[str, str]:
    versions: dict[str, str] = {}
    for raw_line in (PROJECT_ROOT / "requirements.lock").read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        assert EXACT_REQUIREMENT.fullmatch(line), f"dependency is not exact: {line}"
        name, version = line.split("==", 1)
        versions[name.lower().replace("_", "-")] = version
    return versions


def test_requirements_delegates_to_exact_lock() -> None:
    requirements = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert requirements.splitlines()[-1] == "-r requirements.lock"
    assert _locked_versions()


def test_pyproject_direct_dependencies_match_lock() -> None:
    pyproject = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    locked = _locked_versions()
    dependencies = [
        *pyproject["project"]["dependencies"],
        *pyproject["project"]["optional-dependencies"]["dev"],
    ]
    for dependency in dependencies:
        assert EXACT_REQUIREMENT.fullmatch(dependency)
        name, version = dependency.split("==", 1)
        assert locked[name.lower().replace("_", "-")] == version
