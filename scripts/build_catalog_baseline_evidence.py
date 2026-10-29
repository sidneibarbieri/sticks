#!/usr/bin/env python3
"""Compare exact technique-index reach on the same compiled corpus.

Index membership alone does not establish laboratory compatibility, admission,
execution, or evidence certification. No support is inherited across ATT&CK IDs.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from evaluation.technique_coverage import indexed_step_count  # noqa: E402

PLANS = PROJECT_ROOT / "release" / "plans" / "enterprise"
CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
BASELINE = PROJECT_ROOT / "data" / "interop" / "atomic_red_team_techniques.txt"
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "catalog_baseline" / "corpus.json"


def corpus_step_techniques() -> tuple[Counter[str], int]:
    counts: Counter[str] = Counter()
    campaigns = 0
    for plan_path in sorted(PLANS.glob("*.procedural-plan.json")):
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        campaigns += 1
        for step in plan["steps"]:
            counts[step["technique_id"]] += 1
    return counts, campaigns


def reach(step_counts: Counter[str], technique_set: set[str]) -> int:
    """Return exact technique-index reach, not operational coverage."""
    return indexed_step_count(step_counts, technique_set)


def main() -> int:
    step_counts, campaigns = corpus_step_techniques()
    total_steps = sum(step_counts.values())

    templates = json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
    ours = {
        technique_id for template in templates for technique_id in template["technique_ids"]
    }
    baseline = {
        line.strip()
        for line in BASELINE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }

    payload = {
        "matching_policy": "exact_technique_id",
        "question": (
            "How much of the compiled corpus does a large public atomic library reach, "
            "compared with our catalog?"
        ),
        "total_campaigns": campaigns,
        "total_steps": total_steps,
        "distinct_corpus_techniques": len(step_counts),
        "our_techniques": len(ours),
        "our_reach_steps": reach(step_counts, ours),
        "baseline_name": "Atomic Red Team technique index",
        "baseline_techniques": len(baseline),
        "baseline_reach_steps": reach(step_counts, baseline),
        "baseline_uncovered_steps": total_steps - reach(step_counts, baseline),
        "union_uncovered_steps": total_steps - reach(step_counts, ours | baseline),
        "note": (
            "Exact identifier membership only; parent and sibling identifiers do not imply "
            "support. Library metadata and dependencies are not evaluated here. Reach does "
            "not establish binding, admission, execution, or effect certification."
        ),
    }
    payload["baseline_reach_share"] = round(
        payload["baseline_reach_steps"] / total_steps, 4
    )
    payload["our_reach_share"] = round(payload["our_reach_steps"] / total_steps, 4)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[catalog-baseline] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        f"[catalog-baseline] ours reaches {payload['our_reach_steps']}/{total_steps}, "
        f"the public library reaches {payload['baseline_reach_steps']}/{total_steps}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
