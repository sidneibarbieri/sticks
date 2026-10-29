#!/usr/bin/env python3
"""Report where each step is allowed to run, and how the catalog covers those places.

A procedure means different things depending on where it runs. Reading a file on a host the
adversary already controls is not the same act as reading it across a network boundary, and a
harness that produces the same terminal effect from the wrong place has not reproduced the
step. The execution domain is therefore part of the contract rather than a deployment
detail, and admission requires the template's domain to equal the step's.

This step measures the domain distribution the compiled corpus declares and the catalog's
coverage of each domain, so the locus is a reported quantity rather than an implicit one.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLANS = PROJECT_ROOT / "release" / "plans" / "enterprise"
CATALOG = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "execution_locus" / "corpus.json"

DOMAINS = ("attacker", "boundary", "target")


def main() -> int:
    step_domains: Counter[str] = Counter()
    campaigns = 0
    for plan_path in sorted(PLANS.glob("*.procedural-plan.json")):
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        campaigns += 1
        for step in plan["steps"]:
            step_domains[step["execution_domain"]] += 1

    templates = json.loads(CATALOG.read_text(encoding="utf-8"))["templates"]
    template_domains = Counter(template["execution_domain"] for template in templates)

    unknown = sorted(set(step_domains) - set(DOMAINS))
    if unknown:
        raise SystemExit(f"[execution-locus] steps declare an unknown domain: {unknown}")

    total = sum(step_domains.values())
    payload = {
        "question": "Where do compiled steps declare they run, and does the catalog cover each place?",
        "total_campaigns": campaigns,
        "total_steps": total,
        "steps_by_domain": {domain: step_domains[domain] for domain in DOMAINS},
        "step_share_by_domain": {
            domain: round(step_domains[domain] / total, 4) for domain in DOMAINS
        },
        "templates_by_domain": {domain: template_domains[domain] for domain in DOMAINS},
        "total_templates": len(templates),
        "note": (
            "The domain is a three-valued locus, not a host-level source and target pair. It "
            "says whether a step runs on the attacker side, across the boundary, or on the "
            "target, and admission refuses a template whose domain differs from the step's."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"[execution-locus] wrote {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(
        "[execution-locus] "
        + ", ".join(f"{domain} {step_domains[domain]}" for domain in DOMAINS)
        + f" over {total} steps"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
