#!/usr/bin/env python3
"""Replay every selected C0045 cell from one retained evidence archive."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tarfile
import tempfile
from collections import Counter
from pathlib import Path

from pydantic import Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from runners.c0045_effect_series import SERIES_PATHS, load_c0045_effect_series  # noqa: E402
from runners.c0045_series_run import verify_c0045_series_cell  # noqa: E402
from runners.capability_facts import Digest, ImmutableRecord  # noqa: E402


STATIC_AUXILIARY_ROOTS = frozenset({"c0045-control-series", "c0045-prospective"})
MAX_ARCHIVE_MEMBERS = 10_000
MAX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024


class C0045ArchiveAudit(ImmutableRecord):
    schema_version: str = "c0045-series-archive-audit/v1"
    archive_sha256: Digest
    selected_cells: int = Field(strict=True, ge=1)
    unique_boots: int = Field(strict=True, ge=0)
    observed: int = Field(strict=True, ge=0)
    measured: int = Field(strict=True, ge=0)
    failed: int = Field(strict=True, ge=0)
    runner_errors: int = Field(strict=True, ge=0)
    boot_reused: int = Field(strict=True, ge=0)


def _member_path(member: tarfile.TarInfo, allowed_roots: frozenset[str]) -> Path | None:
    if member.pax_headers:
        raise ValueError("C0045 archive contains extended metadata")
    name = member.name.removeprefix("./")
    if name in {"", "."} and member.isdir():
        return None
    if name.startswith("/") or "\\" in name:
        raise ValueError("C0045 archive contains an absolute or ambiguous path")
    parts = name.rstrip("/").split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ValueError("C0045 archive contains a traversal or empty path segment")
    if any(part.startswith("._") or part == ".DS_Store" for part in parts):
        raise ValueError("C0045 archive contains macOS metadata")
    if parts[0] not in allowed_roots:
        raise ValueError("C0045 archive contains an undeclared top-level path")
    if not (member.isdir() or member.isfile()):
        raise ValueError("C0045 archive contains a link or special file")
    return Path(*parts)


def _extract_checked(
    archive: tarfile.TarFile, destination: Path, allowed_roots: frozenset[str]
) -> None:
    if archive.pax_headers:
        raise ValueError("C0045 archive contains global extended metadata")
    seen: set[Path] = set()
    total_size = 0
    for member_count, member in enumerate(archive, start=1):
        if member_count > MAX_ARCHIVE_MEMBERS:
            raise ValueError("C0045 archive has too many members")
        relative_path = _member_path(member, allowed_roots)
        if relative_path is None:
            continue
        if relative_path in seen:
            raise ValueError("C0045 archive contains a duplicate path")
        seen.add(relative_path)
        total_size += member.size
        if total_size > MAX_UNCOMPRESSED_BYTES:
            raise ValueError("C0045 archive exceeds the uncompressed size limit")
        target = destination / relative_path
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        content = archive.extractfile(member)
        if content is None:
            raise ValueError("C0045 archive regular file has no content")
        with content, target.open("xb") as output:
            shutil.copyfileobj(content, output)


def series_path_for_archive(archive_path: Path) -> Path:
    """Select the one frozen schedule whose result root the archive carries."""
    by_root = {
        load_c0045_effect_series(path).receipt_root_name: path
        for path in sorted(SERIES_PATHS)
    }
    with tarfile.open(archive_path, "r:gz") as archive:
        roots = {Path(name).parts[0] for name in archive.getnames() if Path(name).parts}
    matches = sorted(roots & by_root.keys())
    if len(matches) != 1:
        raise ValueError("C0045 archive contains no single declared series root")
    return by_root[matches[0]]


def verify_archive(
    archive_path: Path, series_path: Path | None = None
) -> C0045ArchiveAudit:
    """Check archive structure, then replay all frozen cells without a live VM."""
    if series_path is None:
        series_path = series_path_for_archive(archive_path)
    with archive_path.open("rb") as source:
        archive_sha256 = hashlib.file_digest(source, "sha256").hexdigest()
    with tempfile.TemporaryDirectory(prefix="sticks-c0045-replay-") as temporary:
        root = Path(temporary)
        series = load_c0045_effect_series(series_path)
        allowed_roots = STATIC_AUXILIARY_ROOTS | {series.receipt_root_name}
        with tarfile.open(archive_path, "r:gz") as archive:
            _extract_checked(archive, root, allowed_roots)
        outcomes = [
            verify_c0045_series_cell(root, cell, series_path)
            for cell in series.selected_cells
        ]
    boot_ids = [outcome.boot_id for outcome in outcomes if outcome.boot_id is not None]
    if len(boot_ids) != len(set(boot_ids)):
        raise ValueError("C0045 archive reuses a guest boot across selected cells")
    statuses = Counter(outcome.status for outcome in outcomes)
    return C0045ArchiveAudit(
        archive_sha256=archive_sha256,
        selected_cells=len(series.selected_cells),
        unique_boots=len(boot_ids),
        observed=statuses["observed"],
        measured=statuses["measured"],
        failed=statuses["failed"],
        runner_errors=statuses["runner_error"],
        boot_reused=statuses["boot_reused"],
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--series-path", type=Path, default=None)
    options = parser.parse_args()
    audit = verify_archive(options.archive, options.series_path)
    print(json.dumps(audit.model_dump(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
