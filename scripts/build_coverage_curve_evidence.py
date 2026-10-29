#!/usr/bin/env python3
"""Emit the corpus coverage curve over catalogs of growing size.

Reuses the same compiled corpus plans and action catalog as the substitution evidence,
and writes the frozen curve record. The endpoint equals the full-catalog coverage the
substitution evidence reports; a divergence fails the step.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.coverage_curve import CoverageCurve, greedy_coverage_curve  # noqa: E402

DEFAULT_PLANS_DIR = PROJECT_ROOT / "release" / "plans" / "enterprise"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "coverage_curve"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"


def load_campaigns(plans_dir: Path) -> dict[str, list[dict]]:
    campaigns: dict[str, list[dict]] = {}
    for path in sorted(plans_dir.glob("*.procedural-plan.json")):
        plan = json.loads(path.read_text(encoding="utf-8"))
        campaign_id = plan["campaign_id"]
        if campaign_id in campaigns:
            raise ValueError(f"Duplicate campaign ID: {campaign_id}")
        campaigns[campaign_id] = plan["steps"]
    if not campaigns:
        raise ValueError(f"No procedural plans found in {plans_dir}")
    return campaigns


def build_curve(plans_dir: Path) -> CoverageCurve:
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return greedy_coverage_curve(load_campaigns(plans_dir), templates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plans-dir", type=Path, default=DEFAULT_PLANS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    curve = build_curve(args.plans_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "corpus.json").write_text(
        curve.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    final = curve.points[-1]
    print(
        f"catalog curve: {curve.total_templates} templates over {curve.total_steps} steps; "
        f"endpoint {final.supported_steps}/{curve.total_steps} "
        f"({final.coverage_rate:.1%})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
