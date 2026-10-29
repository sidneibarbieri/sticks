#!/usr/bin/env python3
"""Create or verify the cryptographic manifest of a staged public tree."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

DEFAULT_MANIFEST_NAME = "PUBLIC_TREE_SHA256.json"
RUNTIME_OUTPUTS = {
    "results/enumeration_scaling_timing.json",
    "results/PUBLIC_SURFACE_REPORT.md",
    "results/public_surface_report.json",
}
RUNTIME_PARTS = {".git", ".pytest_cache", ".vagrant", ".venv", "__pycache__"}
RUNTIME_ROOTS = {"runs"}
RUNTIME_PATHS = {("data", "artifacts")}


def _excluded(relative_path: str, manifest_name: str) -> bool:
    path = Path(relative_path)
    return (
        relative_path == manifest_name
        or relative_path in RUNTIME_OUTPUTS
        or path.parts[0] in RUNTIME_ROOTS
        or path.parts[:2] in RUNTIME_PATHS
        or any(part in RUNTIME_PARTS for part in path.parts)
        or any(part.endswith(".egg-info") for part in path.parts)
        # A reviewer's virtual environment may carry any name; match the family.
        or any(part == "venv" or part.startswith(".venv") for part in path.parts)
        or path.suffix in {".pyc", ".pyo"}
    )


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def collect_files(root: Path, manifest_name: str) -> dict[str, dict[str, int | str]]:
    files: dict[str, dict[str, int | str]] = {}
    for path in sorted(root.rglob("*")):
        relative_path = path.relative_to(root).as_posix()
        # Exclusion comes first: a reviewer commonly creates a virtual environment inside
        # the package, and its symlinks must not fail a check about the shipped tree.
        if _excluded(relative_path, manifest_name):
            continue
        if path.is_symlink():
            raise RuntimeError(f"public tree contains a symbolic link: {path}")
        if not path.is_file():
            continue
        content = path.read_bytes()
        files[relative_path] = {
            "sha256": _sha256_bytes(content),
            "size": len(content),
        }
    return files


def tree_sha256(files: dict[str, dict[str, int | str]]) -> str:
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return _sha256_bytes(canonical)


def write_manifest(root: Path, manifest_path: Path) -> dict:
    manifest_name = manifest_path.relative_to(root).as_posix()
    files = collect_files(root, manifest_name)
    payload = {
        "schema_version": "1",
        "algorithm": "sha256",
        "excluded_runtime_outputs": sorted(RUNTIME_OUTPUTS),
        "excluded_runtime_roots": sorted(RUNTIME_ROOTS),
        "excluded_runtime_paths": ["/".join(parts) for parts in sorted(RUNTIME_PATHS)],
        "file_count": len(files),
        "tree_sha256": tree_sha256(files),
        "files": files,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return payload


def verify_manifest(root: Path, manifest_path: Path) -> dict:
    if not manifest_path.is_file():
        raise RuntimeError(f"public tree manifest is absent: {manifest_path}")
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1" or payload.get("algorithm") != "sha256":
        raise RuntimeError("unsupported public tree manifest schema")
    manifest_name = manifest_path.relative_to(root).as_posix()
    observed_files = collect_files(root, manifest_name)
    expected_files = payload.get("files")
    if not isinstance(expected_files, dict):
        raise RuntimeError("public tree manifest has no file map")

    missing = sorted(set(expected_files) - set(observed_files))
    unexpected = sorted(set(observed_files) - set(expected_files))
    modified = sorted(
        relative_path
        for relative_path in set(expected_files) & set(observed_files)
        if expected_files[relative_path] != observed_files[relative_path]
    )
    observed_tree_sha256 = tree_sha256(observed_files)
    if (
        missing
        or unexpected
        or modified
        or payload.get("file_count") != len(observed_files)
        or payload.get("tree_sha256") != observed_tree_sha256
    ):
        raise RuntimeError(
            "public tree integrity failure: "
            f"missing={missing}, unexpected={unexpected}, modified={modified}, "
            f"observed_tree_sha256={observed_tree_sha256}"
        )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("write", "verify"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--manifest", type=Path,
        help="manifest path, relative to --root unless absolute",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    manifest_path = (
        (root / args.manifest).resolve()
        if args.manifest is not None
        else root / DEFAULT_MANIFEST_NAME
    )
    if args.command == "write":
        payload = write_manifest(root, manifest_path)
        action = "wrote"
    else:
        payload = verify_manifest(root, manifest_path)
        action = "verified"
    print(
        f"[public-tree] {action} {payload['file_count']} files; "
        f"tree_sha256={payload['tree_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
