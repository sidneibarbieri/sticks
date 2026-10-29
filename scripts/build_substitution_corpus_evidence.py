#!/usr/bin/env python3
"""Emit the corpus-wide substitution evidence over every compiled campaign plan.

Runs the substitution classification across all campaign procedural plans -- which needs
only the plans and the action catalog, not a declared environment -- and writes the frozen
corpus record. This scales the Gate-1 result beyond the three deeply concretized campaigns.
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

from evaluation.substitution import CorpusSubstitution, analyze_corpus  # noqa: E402

DEFAULT_PLANS_DIR = PROJECT_ROOT / "release" / "plans" / "enterprise"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "substitution"


def load_campaigns(plans_dir: Path) -> dict[str, list[dict]]:
    campaigns: dict[str, list[dict]] = {}
    for path in sorted(plans_dir.glob("*.procedural-plan.json")):
        plan = json.loads(path.read_text(encoding="utf-8"))
        campaigns[plan["campaign_id"]] = plan["steps"]
    return campaigns


def build_corpus(plans_dir: Path) -> CorpusSubstitution:
    templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return analyze_corpus(load_campaigns(plans_dir), templates)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plans-dir", type=Path, default=DEFAULT_PLANS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    corpus = build_corpus(args.plans_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "corpus.json").write_text(
        corpus.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"campaigns={corpus.total_campaigns} steps={corpus.total_steps} | "
        f"determined={corpus.determined} equivalent={corpus.evidence_equivalent} "
        f"divergent={corpus.evidence_divergent} unsupported={corpus.unsupported}"
    )
    print(
        f"catalog coverage = {corpus.catalog_supported_steps}/{corpus.total_steps} "
        f"({corpus.catalog_coverage_rate:.0%}); "
        f"evidence-divergent over supported = "
        f"{corpus.evidence_divergent}/{corpus.catalog_supported_steps} "
        f"({corpus.evidence_divergence_rate_over_supported:.1%})"
    )
    print(f"[substitution] wrote corpus.json to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
