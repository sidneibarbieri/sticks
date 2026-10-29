#!/usr/bin/env python3
"""Emit the catalog authoring-cost evidence: surface, amortization and proposer yield.

Reads the trusted catalog, the compiled corpus plans and the frozen Stage-2 record.
It writes one JSON record and never calls a model.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.models import ActionTemplate  # noqa: E402
from evaluation.authoring_cost import (  # noqa: E402
    AutomationYield,
    measure_authoring_cost,
    template_surface,
)

CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
PLANS = PROJECT_ROOT / "release" / "plans" / "enterprise"
STAGE2_RECORD = PROJECT_ROOT / "release" / "experiments" / "stage2_authoring" / "corpus.json"
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "authoring_cost" / "corpus.json"


def load_templates() -> list[ActionTemplate]:
    entries = json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
    return [ActionTemplate.model_validate(entry) for entry in entries]


def corpus_step_counts() -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in PLANS.glob("*.procedural-plan.json"):
        for step in json.loads(path.read_text(encoding="utf-8"))["steps"]:
            counts[step["technique_id"]] += 1
    return counts


def frozen_automation_yield() -> AutomationYield:
    record = json.loads(STAGE2_RECORD.read_text(encoding="utf-8"))
    return AutomationYield(
        proposals=record["proposals"],
        admitted=record["admitted_templates"],
        rejected=record["rejected_templates"],
        rejected_by_code=record["rejected_by_code"],
    )


def build_record() -> dict:
    templates = load_templates()
    cost = measure_authoring_cost(templates, corpus_step_counts(), frozen_automation_yield())
    return {
        "question": (
            "How much catalog authoring does admission require, how far does each authored "
            "template reach, and how much of the authoring can a proposer take over?"
        ),
        "scope": (
            "Structural and automation quantities only; not analyst time or expertise. "
            "Admitted drafts are contract-valid, not executed."
        ),
        "summary": cost.model_dump(),
        "templates": [
            {**template_surface(template).model_dump(), "fields": template_surface(template).fields}
            for template in templates
        ],
    }


def main() -> int:
    record = build_record()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = record["summary"]
    print(f"[authoring-cost] {summary['templates']} templates, {summary['total_fields']} fields "
          f"(median {summary['median_fields']}); {summary['covered_steps']} steps, "
          f"{summary['steps_per_template']} per template; proposer admitted "
          f"{summary['automation']['admitted']}/{summary['automation']['proposals']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
