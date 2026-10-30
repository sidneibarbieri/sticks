#!/usr/bin/env python3
"""Create a deterministic typed-evidence archive without macOS metadata forks."""

from __future__ import annotations

import argparse
import gzip
import sys
import tarfile
from pathlib import Path, PurePosixPath

ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(ARTIFACT_ROOT / "src"), str(ARTIFACT_ROOT))

from scripts.verify_typed_evidence_archive import (
    CAMPAIGN_DIRECTORIES,
    SERIES,
    validate_members,
)


def archive_name(
    path: Path,
    stage_root: Path,
    campaign_directories: tuple[str, ...] = CAMPAIGN_DIRECTORIES,
) -> str:
    """Return a portable member name rooted at one declared campaign."""
    relative = path.relative_to(stage_root)
    name = PurePosixPath(*relative.parts).as_posix()
    if not name or name.split("/", 1)[0] not in campaign_directories:
        raise ValueError("Staged path is outside a declared campaign")
    if any(part.startswith("._") or part == "__MACOSX" for part in name.split("/")):
        raise ValueError("Staged evidence contains Apple metadata")
    return name


def regular_files(
    stage_root: Path, campaign_directories: tuple[str, ...] = CAMPAIGN_DIRECTORIES
) -> list[Path]:
    """Collect only ordinary staged files; reject links and special files."""
    files: list[Path] = []
    for campaign in campaign_directories:
        campaign_root = stage_root / campaign
        if campaign_root.is_symlink() or not campaign_root.is_dir():
            raise ValueError(f"Staged campaign is missing or linked: {campaign}")
        for path in sorted(campaign_root.rglob("*")):
            if path.is_symlink():
                raise ValueError(f"Staged evidence contains a symbolic link: {path}")
            if path.is_dir():
                continue
            if not path.is_file():
                raise ValueError(f"Staged evidence contains a special file: {path}")
            archive_name(path, stage_root, campaign_directories)
            files.append(path)
    return files


def tar_info(name: str, size: int, *, directory: bool = False) -> tarfile.TarInfo:
    """Build deterministic tar metadata independent of the local account."""
    info = tarfile.TarInfo(name)
    info.uid = 0
    info.gid = 0
    info.uname = "root"
    info.gname = "root"
    info.mtime = 0
    if directory:
        info.type = tarfile.DIRTYPE
        info.mode = 0o755
    else:
        info.size = size
        info.mode = 0o644
    return info


def create_archive(
    stage_root: Path,
    output_path: Path,
    campaign_directories: tuple[str, ...] = CAMPAIGN_DIRECTORIES,
) -> None:
    """Archive a validated staging tree with only portable regular-file members."""
    if stage_root.is_symlink() or not stage_root.is_dir():
        raise ValueError("Staging root is missing or linked")
    if output_path.exists():
        raise FileExistsError(output_path)
    files = regular_files(stage_root, campaign_directories)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("xb") as output, gzip.GzipFile(
        filename="", fileobj=output, mode="wb", mtime=0
    ) as compressed, tarfile.open(fileobj=compressed, mode="w") as archive:
        for campaign in campaign_directories:
            archive.addfile(tar_info(campaign, 0, directory=True))
        for path in files:
            name = archive_name(path, stage_root, campaign_directories)
            with path.open("rb") as source:
                archive.addfile(tar_info(name, path.stat().st_size), source)
    with tarfile.open(output_path, mode="r:gz") as archive:
        validate_members(archive.getmembers(), campaign_directories)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--series", choices=sorted(SERIES), default="qemu")
    args = parser.parse_args()
    create_archive(args.stage, args.output, SERIES[args.series])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
