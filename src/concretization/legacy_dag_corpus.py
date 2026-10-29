"""Resolve the retained historical STICKS campaign corpus."""

from __future__ import annotations

from pathlib import Path


def resolve_legacy_dag_dir(project_root: Path) -> Path:
    """Return the historical DAG directory or fail instead of reporting zero coverage."""
    research_root = project_root.parent
    candidates = (
        project_root / "data" / "legacy" / "dag",
        research_root / "sticks-main" / "sticks" / "data" / "dag",
        research_root / "sticks-docker" / "sticks" / "data" / "dag",
    )
    for candidate in candidates:
        if candidate.is_dir() and any(candidate.glob("*_dag.json")):
            return candidate

    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"historical STICKS DAG corpus not found; searched: {searched}")
