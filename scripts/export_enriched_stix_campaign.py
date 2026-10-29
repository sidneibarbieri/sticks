#!/usr/bin/env python3
"""Export a compact STIX campaign bundle with verified procedure semantics."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.models import ActionTemplate, ConcretizedPlan  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from contracts.stix_campaign_export import export_campaign_bundle  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--concretized-plan", type=Path, required=True)
    parser.add_argument(
        "--templates",
        type=Path,
        default=PROJECT_ROOT / "data" / "concretization" / "action_templates.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = ProceduralPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    concretized = ConcretizedPlan.model_validate_json(
        args.concretized_plan.read_text(encoding="utf-8")
    )
    template_payload = json.loads(args.templates.read_text(encoding="utf-8"))
    templates = [
        ActionTemplate.model_validate(item)
        for item in template_payload.get("templates", [])
    ]
    output = export_campaign_bundle(
        source_bundle_path=args.bundle,
        plan=plan,
        concretized_plan=concretized,
        templates=templates,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"[stix-extension] campaign: {plan.campaign_id}")
    print(f"[stix-extension] objects: {len(output['objects'])}")
    print(f"[stix-extension] output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

