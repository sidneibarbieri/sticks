#!/usr/bin/env python3
"""Verify a private typed-QEMU evidence archive in a fresh temporary directory."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath

ARTIFACT_ROOT = Path(__file__).resolve().parent.parent
for import_root in (ARTIFACT_ROOT, ARTIFACT_ROOT / "src"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from scripts.audit_typed_campaign_outcomes import CampaignOutcome, audit_runs  # noqa: E402
from scripts.render_typed_campaign_outcomes_tex import render_tex  # noqa: E402


CAMPAIGN_DIRECTORIES = ("c0010", "c0026")
MAX_MEMBERS = 15_000
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024


def validate_members(members: list[tarfile.TarInfo]) -> None:
    if not members or len(members) > MAX_MEMBERS:
        raise ValueError("Archive member count is invalid")
    seen: set[str] = set()
    total_bytes = 0
    for member in members:
        name = member.name.rstrip("/")
        path = PurePosixPath(name)
        parts = name.split("/")
        if (
            not name
            or path.is_absolute()
            or "\\" in name
            or any(part in {"", ".", ".."} for part in parts)
            or parts[0] not in CAMPAIGN_DIRECTORIES
            or any(part.startswith("._") or part == "__MACOSX" for part in parts)
            or name in seen
        ):
            raise ValueError("Archive contains an unsafe or unexpected path")
        seen.add(name)
        if not (member.isdir() or member.isfile()):
            raise ValueError("Archive contains a link or special file")
        if name in CAMPAIGN_DIRECTORIES and not member.isdir():
            raise ValueError("Campaign root must be a directory")
        if member.isfile():
            if member.size < 0 or member.size > MAX_FILE_BYTES:
                raise ValueError("Archive contains an oversized file")
            total_bytes += member.size
            if total_bytes > MAX_TOTAL_BYTES:
                raise ValueError("Archive exceeds the byte limit")
    if not set(CAMPAIGN_DIRECTORIES).issubset(seen):
        raise ValueError("Archive is missing a campaign directory")


def extract_members(archive: tarfile.TarFile, destination: Path) -> None:
    members = archive.getmembers()
    validate_members(members)
    for member in members:
        target = destination.joinpath(*PurePosixPath(member.name).parts)
        if member.isdir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        source = archive.extractfile(member)
        if source is None:
            raise ValueError("Archive member has no data")
        with source, target.open("xb") as output:
            shutil.copyfileobj(source, output)


def verify_archive(path: Path) -> list[CampaignOutcome]:
    with tempfile.TemporaryDirectory(prefix="sticks-typed-evidence-") as temporary:
        destination = Path(temporary)
        with tarfile.open(path, mode="r:gz") as archive:
            extract_members(archive, destination)
        return audit_runs([destination / name for name in CAMPAIGN_DIRECTORIES])


def verify_paper_outcomes(outcomes: list[CampaignOutcome], paper_file: Path) -> None:
    expected = render_tex(outcomes)
    actual = paper_file.read_text(encoding="utf-8")
    if actual != expected:
        raise ValueError(
            f"Paper QEMU outcomes disagree with sealed receipts: {paper_file}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--paper-outcomes", type=Path)
    args = parser.parse_args()
    outcomes = verify_archive(args.archive)
    if args.paper_outcomes is not None:
        verify_paper_outcomes(outcomes, args.paper_outcomes)
    print(
        json.dumps([item.model_dump() for item in outcomes], indent=2, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
