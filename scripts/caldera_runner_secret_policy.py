"""Reject embedded credentials in the legacy Caldera campaign runners."""

from __future__ import annotations

import ast
from pathlib import Path

LEGACY_CALDERA_RUNNERS = (
    "measurement/sut/scripts/run_campaign.py",
    "measurement/sut/scripts/run_finite.py",
)
CALDERA_TOOL_SOURCES = (
    "caldera_manager.py",
    "scripts/tools/load_ability.py",
    "scripts/tools/load_adversary.py",
    "scripts/tools/restore_ability_from_backup.py",
    "scripts/tools/restore_adversary_from_backup.py",
    "scripts/tools/restore_operation_from_backup.py",
    "scripts/tools/restore_planner_from_backup.py",
)
CREDENTIAL_SOURCE_FILES = (*LEGACY_CALDERA_RUNNERS, *CALDERA_TOOL_SOURCES)
SECRET_NAME_PARTS = ("password", "passphrase", "secret", "api_key", "token")


def literal_credential_assignment_count(data: bytes) -> int:
    syntax = ast.parse(data)
    count = 0
    for node in ast.walk(syntax):
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        else:
            continue
        if not isinstance(node.value, ast.Constant) or not isinstance(
            node.value.value, str
        ):
            continue
        if not node.value.value:
            continue
        if any(
            isinstance(name, ast.Name)
            and any(part in name.id.lower() for part in SECRET_NAME_PARTS)
            for target in targets
            for name in ast.walk(target)
        ):
            count += 1
    return count


def require_safe_caldera_sources(source_root: Path) -> None:
    for relative_path in CREDENTIAL_SOURCE_FILES:
        script_path = source_root / relative_path
        if not script_path.is_file():
            continue
        if literal_credential_assignment_count(script_path.read_bytes()):
            raise ValueError(
                f"Caldera source embeds a literal credential: {relative_path}"
            )
