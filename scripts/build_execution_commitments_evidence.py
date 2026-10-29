#!/usr/bin/env python3
"""Emit the execution-commitments evidence for the frozen campaigns.

For each campaign this concretizes the plan deterministically and counts the execution
commitments the contract makes concrete. The paper consumes the frozen records; this
script does not regenerate them into prose.
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
from evaluation.execution_commitments import (  # noqa: E402
    CampaignCommitments,
    measure_commitments,
)

DEFAULT_CAMPAIGNS = ("C0010", "C0026", "C0045")
PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "execution_commitments"


def _templates() -> list[ActionTemplate]:
    raw = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return [ActionTemplate.model_validate(item) for item in raw]


def build_campaign_commitments(campaign_id: str) -> CampaignCommitments:
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    declared = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    return measure_commitments(campaign_id, plan, declared, _templates())


def _print_row(commitments: CampaignCommitments) -> None:
    print(
        f"{commitments.campaign_id:7s} steps={commitments.steps:2d} | "
        f"mechanism={commitments.mechanism_commitments:2d} "
        f"binding={commitments.binding_commitments:2d} "
        f"total={commitments.total_execution_commitments:2d} | "
        f"pruned={commitments.candidates_pruned_by_verifier:2d} | "
        f"determined={commitments.fully_determined}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaigns", nargs="+", default=list(DEFAULT_CAMPAIGNS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    for campaign_id in args.campaigns:
        commitments = build_campaign_commitments(campaign_id)
        _print_row(commitments)
        total += commitments.total_execution_commitments
        (args.output_dir / f"{campaign_id}.commitments.json").write_text(
            commitments.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
    print(f"[commitments] {total} execution commitments across "
          f"{len(args.campaigns)} campaign(s); wrote records to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
