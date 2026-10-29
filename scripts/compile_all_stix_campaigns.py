#!/usr/bin/env python3
"""Compile every active ATT&CK campaign in a pinned STIX bundle."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from compilers.stix_campaign_compiler import compile_campaign


def _external_id(stix_object: dict) -> str:
    for reference in stix_object.get("external_references", []):
        if reference.get("source_name") == "mitre-attack":
            return str(reference.get("external_id", ""))
    return ""


def active_campaign_ids(bundle_path: Path) -> list[str]:
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    return sorted(
        {
            _external_id(stix_object)
            for stix_object in bundle.get("objects", [])
            if stix_object.get("type") == "campaign"
            and not stix_object.get("revoked", False)
            and not stix_object.get("x_mitre_deprecated", False)
            and _external_id(stix_object).startswith("C")
        }
    )


def compile_all(bundle_path: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    for campaign_id in active_campaign_ids(bundle_path):
        try:
            plan = compile_campaign(bundle_path, campaign_id)
        except ValueError as exc:
            rows.append(
                {
                    "campaign_id": campaign_id,
                    "status": "not_compiled",
                    "reason": str(exc),
                }
            )
            continue
        output_path = output_dir / f"{campaign_id}.procedural-plan.json"
        output_path.write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")
        rows.append(
            {
                "campaign_id": campaign_id,
                "campaign_name": plan.campaign_name,
                "status": "compiled",
                "step_count": len(plan.steps),
                "content_sha256": plan.content_sha256,
                "path": output_path.name,
            }
        )
    return {
        "schema_version": "1",
        "bundle_sha256": hashlib.sha256(bundle_path.read_bytes()).hexdigest(),
        "campaign_count": len(rows),
        "compiled_count": sum(row["status"] == "compiled" for row in rows),
        "not_compiled_count": sum(row["status"] != "compiled" for row in rows),
        "campaigns": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bundle",
        type=Path,
        default=PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "release" / "plans" / "enterprise",
    )
    args = parser.parse_args()
    index = compile_all(args.bundle, args.output_dir)
    index_path = args.output_dir / "index.json"
    index_path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    print(f"[compile-all] campaigns: {index['campaign_count']}")
    print(f"[compile-all] compiled: {index['compiled_count']}")
    print(f"[compile-all] unresolved: {index['not_compiled_count']}")
    print(f"[compile-all] index: {index_path}")
    return 0 if index["not_compiled_count"] == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
