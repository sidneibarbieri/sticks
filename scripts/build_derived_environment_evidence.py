#!/usr/bin/env python3
"""Emit derived-environment evidence over every compiled Enterprise campaign.

For each campaign the environment is derived from the action catalog rather than authored,
and admission is decided by the same offline verifier. The paper consumes the frozen record.
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

from concretization.derived_environment_corpus import (  # noqa: E402
    aggregate,
    measure_campaign,
)
from concretization.models import ActionTemplate  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402

ENTERPRISE_PLANS = PROJECT_ROOT / "release" / "plans" / "enterprise"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "release" / "experiments" / "derived_environment" / "corpus.json"
)


def _load_templates() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    templates = _load_templates()
    per_campaign = [
        measure_campaign(
            ProceduralPlan.model_validate_json(path.read_text(encoding="utf-8")),
            templates,
        )
        for path in sorted(ENTERPRISE_PLANS.glob("*.procedural-plan.json"))
    ]
    corpus = aggregate(per_campaign)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(corpus.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"[derived-environment] {corpus.campaigns} campaigns, "
        f"{corpus.admitted_steps}/{corpus.total_steps} steps admitted "
        f"({corpus.admitted_rate * 100:.1f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
