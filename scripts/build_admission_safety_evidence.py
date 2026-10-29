#!/usr/bin/env python3
"""Emit the admission-safety evidence: what a proposer can and cannot change.

Submits inadmissible proposals alongside the solver's candidates and records whether the
committed plan changes. The paper consumes the frozen record.
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
from evaluation.admission_safety import evaluate_admission_safety  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "admission_safety"
CAMPAIGN_ID = "C0045"
TECHNIQUE_ID = "T1105"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    templates = [
        ActionTemplate.model_validate(item)
        for item in json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    ]
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{CAMPAIGN_ID}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{CAMPAIGN_ID}.binding-catalog.json").read_text(encoding="utf-8")
    )
    result = evaluate_admission_safety(
        CAMPAIGN_ID, plan, catalog, templates, TECHNIQUE_ID
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"{CAMPAIGN_ID}.admission_safety.json").write_text(
        result.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    for outcome in result.outcomes:
        print(f"  {outcome.kind.value:22s} unchanged={outcome.matches_unproposed_plan}")
    print(f"[admission-safety] inadmissible proposals rejected: "
          f"{result.inadmissible_proposals_rejected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
