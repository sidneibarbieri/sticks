#!/usr/bin/env python3
"""Build a bounded campaign-and-SUT-aware template-generation queue."""

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
from concretization.target_queue import build_template_generation_queue  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402


def _load_templates(path: Path) -> list[ActionTemplate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_templates = payload.get("templates")
    if not isinstance(raw_templates, list):
        raise ValueError("action template catalog has no templates list")
    return [ActionTemplate.model_validate(item) for item in raw_templates]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument(
        "--templates",
        type=Path,
        default=PROJECT_ROOT / "data/concretization/action_templates.json",
    )
    parser.add_argument("--desired-procedure-assignments-per-step", type=int, default=2)
    parser.add_argument("--desired-behavior-contracts-per-step", type=int, default=2)
    parser.add_argument("--maximum-targets", type=int, default=12)
    parser.add_argument("--maximum-realizations", type=int, default=64)
    parser.add_argument("--maximum-search-states", type=int, default=10000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    result = build_template_generation_queue(
        ProceduralPlan.model_validate_json(args.plan.read_text(encoding="utf-8")),
        BindingCatalog.model_validate_json(args.bindings.read_text(encoding="utf-8")),
        _load_templates(args.templates),
        desired_procedure_assignments_per_step=(
            args.desired_procedure_assignments_per_step
        ),
        desired_behavior_contracts_per_step=(args.desired_behavior_contracts_per_step),
        maximum_targets=args.maximum_targets,
        maximum_realizations=args.maximum_realizations,
        maximum_search_states=args.maximum_search_states,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"[generation-queue] campaign: {result.campaign_id}")
    print(
        "[generation-queue] procedure-assignment deficit: "
        f"{result.total_procedure_assignment_deficit}"
    )
    print(
        "[generation-queue] behavior-contract deficit: "
        f"{result.total_behavior_contract_deficit}"
    )
    print(f"[generation-queue] selected targets: {result.selected_target_count}")
    print(
        "[generation-queue] deferred procedure assignments: "
        f"{result.unselected_procedure_assignment_deficit}"
    )
    print(f"[generation-queue] operational status: {result.operational_status}")
    print(f"[generation-queue] hash: {result.content_sha256}")
    print(f"[generation-queue] output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
