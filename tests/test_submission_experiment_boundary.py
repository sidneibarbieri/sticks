"""Submission exports must exclude unclaimed conditional-execution research."""

import ast
from pathlib import Path

from scripts.package_complete_public_repo import EXPERIMENTAL_ONLY_PATHS, STICKS_ROOT, ignore_for_directory


def test_all_experimental_entrypoints_are_excluded_by_export_policy() -> None:
    for relative in EXPERIMENTAL_ONLY_PATHS:
        path = Path(relative)
        directory = path.parts[0]
        source = STICKS_ROOT / path.parent
        assert path.name in ignore_for_directory(directory)(str(source), [path.name])


def test_stable_flow_adapter_has_no_execution_experiment_import() -> None:
    source = STICKS_ROOT / "src/adapters/attack_flow.py"
    modules = {
        node.module for node in ast.walk(ast.parse(source.read_text()))
        if isinstance(node, ast.ImportFrom)
    }
    assert "contracts.flow_structure" in modules
    assert "contracts.branch_decision" not in modules
    assert "adapters.caldera_operations" not in modules
