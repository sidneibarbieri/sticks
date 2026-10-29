#!/usr/bin/env python3
"""Regenerate the deep-campaign concretized plans, repetitions, and explanation.

These frozen outputs illustrate the deterministic concretization the deep evaluation rests
on. They are produced solver-only from committed inputs, so a reviewer regenerates them
offline. The two solver repetitions of the same campaign make determinism visible: identical
inputs yield byte-identical committed plans.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
for import_root in (PROJECT_ROOT, SRC_ROOT, SCRIPTS_DIR):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.models import ActionTemplate, BindingCatalog, ConcretizedPlan  # noqa: E402
from concretization.pipeline import concretize_plan  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from explain_concretized_plan import render_explanation  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEEP_CAMPAIGNS = ("C0010", "C0026", "C0045")
REPETITION_CAMPAIGN = "C0045"
REPETITION_COUNT = 2


def _load_templates() -> list[ActionTemplate]:
    payload = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload["templates"]]


def _concretize(plan_path: Path, catalog_path: Path, templates: list[ActionTemplate]) -> ConcretizedPlan:
    plan = ProceduralPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    catalog = BindingCatalog.model_validate_json(catalog_path.read_text(encoding="utf-8"))
    return concretize_plan(plan, catalog, templates, llm_proposals=[])


def _write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    print(f"[deep-concretization] wrote {path.relative_to(PROJECT_ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    templates = _load_templates()

    for campaign_id in DEEP_CAMPAIGNS:
        concretized = _concretize(
            PLANS_DIR / f"{campaign_id}.procedural-plan.json",
            PLANS_DIR / f"{campaign_id}.binding-catalog.json",
            templates,
        )
        _write(
            PLANS_DIR / f"{campaign_id}.concretized-plan.json",
            concretized.model_dump_json(indent=2) + "\n",
        )

    raw = _concretize(
        PLANS_DIR / "C0045.procedural-plan.json",
        PLANS_DIR / "C0045.raw.binding-catalog.json",
        templates,
    )
    _write(PLANS_DIR / "C0045.raw.concretized-plan.json", raw.model_dump_json(indent=2) + "\n")

    for repetition in range(1, REPETITION_COUNT + 1):
        run = _concretize(
            PLANS_DIR / f"{REPETITION_CAMPAIGN}.procedural-plan.json",
            PLANS_DIR / f"{REPETITION_CAMPAIGN}.binding-catalog.json",
            templates,
        )
        _write(
            PLANS_DIR / "repetitions" / f"{REPETITION_CAMPAIGN}.solver.{repetition}.json",
            run.model_dump_json(indent=2) + "\n",
        )

    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / "C0045.binding-catalog.json").read_text(encoding="utf-8")
    )
    concretized = ConcretizedPlan.model_validate_json(
        (PLANS_DIR / "C0045.concretized-plan.json").read_text(encoding="utf-8")
    )
    explanation = render_explanation(concretized, catalog)
    _write(PLANS_DIR / "C0045.explanation.json", json.dumps(explanation, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
