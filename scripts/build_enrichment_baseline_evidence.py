#!/usr/bin/env python3
"""Emit the raw-STIX-versus-enriched baseline evidence for the frozen campaigns.

For each campaign this concretizes the plan twice through the same pipeline -- against an
emptied (raw-STIX) environment and against the declared environment -- and writes the
frozen baseline record. The paper consumes these records; it does not regenerate them.
"""

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

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from evaluation.enrichment_baseline import EnrichmentBaseline, run_baseline  # noqa: E402

DEFAULT_CAMPAIGNS = ("C0010", "C0026", "C0045")
PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "enrichment_baseline"


def _templates() -> list[ActionTemplate]:
    raw = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return [ActionTemplate.model_validate(item) for item in raw]


def build_campaign_baseline(campaign_id: str) -> EnrichmentBaseline:
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    declared = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    return run_baseline(campaign_id, plan, declared, _templates())


def _print_row(baseline: EnrichmentBaseline) -> None:
    print(
        f"{baseline.campaign_id:7s} steps={baseline.total_steps:2d} | "
        f"raw_stix={baseline.raw_stix_executable_steps:2d} "
        f"({baseline.raw_stix_executable_rate:4.0%}) | "
        f"enriched={baseline.enriched_executable_steps:2d} "
        f"({baseline.enriched_executable_rate:4.0%}) | "
        f"delta=+{baseline.enrichment_delta}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaigns", nargs="+", default=list(DEFAULT_CAMPAIGNS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for campaign_id in args.campaigns:
        baseline = build_campaign_baseline(campaign_id)
        _print_row(baseline)
        output_path = args.output_dir / f"{campaign_id}.baseline.json"
        output_path.write_text(baseline.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"[baseline] wrote {len(args.campaigns)} record(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
