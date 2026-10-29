#!/usr/bin/env python3
"""Recompile the pinned Enterprise bundle and verify the released plan tree."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from compile_all_stix_campaigns import compile_all

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUNDLE_PATH = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
RELEASED_DIR = PROJECT_ROOT / "release" / "plans" / "enterprise"
EXPECTED_COMPILED_CAMPAIGNS = 55


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _file_map(root: Path) -> dict[str, Path]:
    return {
        path.relative_to(root).as_posix(): path
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _validate_provenance(directory: Path, bundle_sha256: str) -> None:
    index_path = directory / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    if index.get("bundle_sha256") != bundle_sha256:
        raise RuntimeError("enterprise index is not bound to the pinned bundle")
    if index.get("compiled_count") != EXPECTED_COMPILED_CAMPAIGNS:
        raise RuntimeError(
            "enterprise index does not contain exactly "
            f"{EXPECTED_COMPILED_CAMPAIGNS} compiled campaigns"
        )

    compiled_rows = {
        row["campaign_id"]: row
        for row in index.get("campaigns", [])
        if row.get("status") == "compiled"
    }
    if len(compiled_rows) != EXPECTED_COMPILED_CAMPAIGNS:
        raise RuntimeError("enterprise index compiled rows disagree with compiled_count")

    for campaign_id, row in sorted(compiled_rows.items()):
        plan_path = directory / str(row["path"])
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        source = plan.get("source", {})
        if source.get("bundle_sha256") != bundle_sha256:
            raise RuntimeError(f"{campaign_id}: plan provenance has wrong bundle hash")
        if source.get("campaign_external_id") != campaign_id:
            raise RuntimeError(f"{campaign_id}: plan provenance has wrong campaign id")
        if plan.get("content_sha256") != row.get("content_sha256"):
            raise RuntimeError(f"{campaign_id}: index and plan content hashes disagree")


def verify_release() -> int:
    bundle_sha256 = _sha256(BUNDLE_PATH)
    with tempfile.TemporaryDirectory(prefix="sticks-enterprise-plans-") as temp_dir:
        regenerated_dir = Path(temp_dir)
        regenerated_index = compile_all(BUNDLE_PATH, regenerated_dir)
        (regenerated_dir / "index.json").write_text(
            json.dumps(regenerated_index, indent=2) + "\n",
            encoding="utf-8",
        )

        _validate_provenance(regenerated_dir, bundle_sha256)
        _validate_provenance(RELEASED_DIR, bundle_sha256)

        regenerated_files = _file_map(regenerated_dir)
        released_files = _file_map(RELEASED_DIR)
        if regenerated_files.keys() != released_files.keys():
            missing = sorted(regenerated_files.keys() - released_files.keys())
            extra = sorted(released_files.keys() - regenerated_files.keys())
            raise RuntimeError(
                f"enterprise plan tree differs: missing={missing}, extra={extra}"
            )

        mismatches = [
            relative
            for relative in regenerated_files
            if regenerated_files[relative].read_bytes()
            != released_files[relative].read_bytes()
        ]
        if mismatches:
            details = [
                {
                    "path": relative,
                    "regenerated_sha256": _sha256(regenerated_files[relative]),
                    "released_sha256": _sha256(released_files[relative]),
                }
                for relative in mismatches
            ]
            raise RuntimeError(f"enterprise plan bytes differ: {details}")

    print(
        "[enterprise-plans] 55 campaigns, index, and source provenance "
        "reproduced byte-identically"
    )
    return EXPECTED_COMPILED_CAMPAIGNS


def main() -> int:
    verify_release()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
