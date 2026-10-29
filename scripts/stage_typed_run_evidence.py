#!/usr/bin/env python3
"""Stage a private, manifest-scoped copy of sealed QEMU run evidence.

This command does not sanitize or authorize publication. It omits unbound
workspace files and verifies each copied run against its original receipt.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field

ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(ARTIFACT_ROOT / "src"), str(ARTIFACT_ROOT))

from scripts.finalize_isolated_lab_run import FINAL_RECEIPT, build_receipt  # noqa: E402

ROOT_FILES = (
    "run_context.json",
    "source_manifest.json",
    "evidence_manifest.json",
    "artifact_manifest.json",
    "execution.log",
    FINAL_RECEIPT,
)
PUBLIC_REFERENCE_MANIFEST = "PUBLIC_TREE_SHA256.json"


class StagedRun(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    campaign_id: str
    receipt_sha256: str
    source_files: int = Field(ge=1)
    artifact_files: int = Field(ge=0)
    evidence_files: int = Field(ge=1)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_reference_manifest(source_manifest: dict) -> dict:
    """Convert a sealed source manifest into the reviewer reference format."""
    entries = source_manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Source manifest file list is missing")
    files: dict[str, dict[str, int | str]] = {}
    for entry in entries:
        relative = safe_relative_path(entry["path"]).as_posix()
        if relative in files:
            raise ValueError("Source manifest repeats a path")
        digest = entry.get("sha256")
        size = entry.get("size")
        if not isinstance(digest, str) or not isinstance(size, int):
            raise TypeError("Source manifest entry is incomplete")
        files[relative] = {"sha256": digest, "size": size}
    tree_digest = hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {
        "schema_version": "1",
        "algorithm": "sha256",
        "file_count": len(files),
        "tree_sha256": tree_digest,
        "files": files,
    }


def write_source_reference_manifest(workspace: Path, source_manifest: dict) -> None:
    """Write derived metadata that binds the staged workspace to its sealed source."""
    path = workspace / PUBLIC_REFERENCE_MANIFEST
    if path.is_symlink():
        raise ValueError("Source reference manifest is linked")
    if path.exists():
        if not path.is_file():
            raise ValueError("Source reference manifest is not a regular file")
        return
    reference = source_reference_manifest(source_manifest)
    path.write_text(
        json.dumps(reference, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def safe_relative_path(value: str) -> Path:
    posix_path = PurePosixPath(value)
    if (
        not value
        or posix_path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError("Manifest contains an unsafe path")
    return Path(*posix_path.parts)


def copy_regular_file(
    source: Path, destination: Path, entry: dict | None = None
) -> None:
    if source.is_symlink() or not source.is_file():
        raise ValueError(f"Expected a regular file: {source}")
    if entry is not None and (
        source.stat().st_size != entry["size"] or sha256_file(source) != entry["sha256"]
    ):
        raise ValueError(f"Manifest digest mismatch: {source}")
    if destination.exists():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def copy_manifest_tree(source_root: Path, target_root: Path, manifest: dict) -> int:
    resolved_root = source_root.resolve(strict=True)
    entries = manifest["files"]
    if not isinstance(entries, list):
        raise TypeError("Manifest file list is missing")
    seen: set[str] = set()
    for entry in entries:
        name = entry["path"]
        relative = safe_relative_path(name)
        if name in seen:
            raise ValueError("Manifest repeats a path")
        seen.add(name)
        source = source_root / relative
        if not source.resolve(strict=True).is_relative_to(resolved_root):
            raise ValueError("Manifest path resolves outside its root")
        copy_regular_file(source, target_root / relative, entry)
    return len(entries)


def copy_evidence_tree(source_root: Path, target_root: Path) -> int:
    if source_root.is_symlink() or not source_root.is_dir():
        raise ValueError("Evidence directory is missing or linked")
    count = 0
    for source in sorted(source_root.rglob("*")):
        if source.is_symlink():
            raise ValueError(f"Evidence contains a symbolic link: {source}")
        if source.is_dir():
            continue
        if not source.is_file():
            raise ValueError(f"Evidence contains a special file: {source}")
        copy_regular_file(source, target_root / source.relative_to(source_root))
        count += 1
    if count == 0:
        raise ValueError("Evidence directory is empty")
    return count


def remove_generated_vagrant_state(workspace: Path) -> None:
    vagrant_root = workspace / "lab/vagrant"
    if not vagrant_root.is_dir():
        return
    for vm_directory in vagrant_root.iterdir():
        runtime_state = vm_directory / ".vagrant"
        if runtime_state.is_symlink() or (
            runtime_state.exists() and not runtime_state.is_dir()
        ):
            raise ValueError("Unexpected Vagrant runtime state")
        if runtime_state.is_dir():
            shutil.rmtree(runtime_state)


def verify_workspace_scope(
    workspace: Path, source_manifest: dict, artifact_manifest: dict
) -> None:
    expected = {entry["path"] for entry in source_manifest["files"]}
    expected.update(
        f"data/artifacts/{entry['path']}" for entry in artifact_manifest["files"]
    )
    expected.add(PUBLIC_REFERENCE_MANIFEST)
    actual: set[str] = set()
    for path in workspace.rglob("*"):
        if path.is_symlink():
            raise ValueError("Staged workspace contains a symbolic link")
        if path.is_file():
            actual.add(path.relative_to(workspace).as_posix())
    if actual != expected:
        raise ValueError("Staged workspace contains unbound or missing files")
    bound_reference = next(
        (
            entry
            for entry in source_manifest["files"]
            if entry["path"] == PUBLIC_REFERENCE_MANIFEST
        ),
        None,
    )
    if bound_reference is None:
        expected_reference = source_reference_manifest(source_manifest)
        actual_reference = read_json(workspace / PUBLIC_REFERENCE_MANIFEST)
        if actual_reference != expected_reference:
            raise ValueError("Staged workspace reference manifest is not source-bound")
    else:
        reference_path = workspace / PUBLIC_REFERENCE_MANIFEST
        if (
            sha256_file(reference_path) != bound_reference["sha256"]
            or reference_path.stat().st_size != bound_reference["size"]
        ):
            raise ValueError("Staged workspace reference differs from sealed source")


def stage_run(run_root: Path, destination: Path) -> StagedRun:
    if run_root.is_symlink():
        raise ValueError("Run root is linked")
    run_root = run_root.resolve(strict=True)
    if not run_root.is_dir():
        raise ValueError("Run root is missing or linked")
    receipt_path = run_root / FINAL_RECEIPT
    receipt = read_json(receipt_path)
    if receipt != build_receipt(run_root) or receipt["cycle_passed"] is not True:
        raise ValueError("Run receipt does not verify")

    destination.mkdir(parents=True, exist_ok=False)
    for name in ROOT_FILES:
        copy_regular_file(run_root / name, destination / name)
    source_manifest = read_json(run_root / "source_manifest.json")
    source_files = copy_manifest_tree(
        run_root / "workspace", destination / "workspace", source_manifest
    )
    write_source_reference_manifest(destination / "workspace", source_manifest)
    artifact_manifest = read_json(run_root / "artifact_manifest.json")
    artifact_files = copy_manifest_tree(
        run_root / "workspace/data/artifacts",
        destination / "workspace/data/artifacts",
        artifact_manifest,
    )
    evidence_files = copy_evidence_tree(run_root / "evidence", destination / "evidence")
    if read_json(destination / FINAL_RECEIPT) != build_receipt(destination):
        raise ValueError("Staged run does not reproduce its final receipt")
    remove_generated_vagrant_state(destination / "workspace")
    verify_workspace_scope(
        destination / "workspace", source_manifest, artifact_manifest
    )
    return StagedRun(
        campaign_id=receipt["campaign_id"],
        receipt_sha256=sha256_file(destination / FINAL_RECEIPT),
        source_files=source_files,
        artifact_files=artifact_files,
        evidence_files=evidence_files,
    )


def stage_runs(run_roots: list[Path], destination: Path) -> list[StagedRun]:
    if not run_roots:
        raise ValueError("At least one run is required")
    destination = destination.resolve()
    if destination.is_relative_to(ARTIFACT_ROOT):
        raise ValueError("Private run evidence must remain outside the repository")
    if destination.exists() or any(
        destination.is_relative_to(run_root.resolve(strict=True))
        for run_root in run_roots
    ):
        raise ValueError("Destination exists or lies inside a source run")
    destination.mkdir(parents=True)
    staged: list[StagedRun] = []
    campaign_ids: set[str] = set()
    for run_root in run_roots:
        campaign_id = read_json(run_root / "run_context.json")["campaign_id"]
        if campaign_id in campaign_ids:
            raise ValueError("Campaign IDs must be unique in one staged bundle")
        campaign_ids.add(campaign_id)
        label = safe_relative_path(campaign_id.removeprefix("0."))
        if len(label.parts) != 1:
            raise ValueError("Campaign label must be one path component")
        staged.append(stage_run(run_root, destination / label))
    return staged


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", action="append", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    rows = stage_runs(args.run_root, args.destination)
    print(json.dumps([row.model_dump() for row in rows], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
