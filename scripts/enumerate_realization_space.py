#!/usr/bin/env python3
"""Enumerate bounded causal realizations for a verified STICKS plan."""

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

from concretization.models import (  # noqa: E402
    ActionTemplate,
    BindingCatalog,
    ProcedureProposal,
)
from concretization.realization_space import enumerate_realization_space  # noqa: E402
from concretization.template_overlay import load_template_overlay  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402


def _load_templates(path: Path) -> list[ActionTemplate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [ActionTemplate.model_validate(item) for item in payload.get("templates", [])]


def _load_proposals(path: Path | None) -> list[ProcedureProposal]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_proposals = payload.get("proposals", []) if isinstance(payload, dict) else payload
    if not isinstance(raw_proposals, list):
        raise ValueError("proposal input must be a list or an object with a proposals list")
    return [ProcedureProposal.model_validate(item) for item in raw_proposals]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument(
        "--templates",
        type=Path,
        default=PROJECT_ROOT / "data" / "concretization" / "action_templates.json",
    )
    parser.add_argument("--proposals", type=Path)
    parser.add_argument("--template-overlay", type=Path)
    parser.add_argument("--maximum-realizations", type=int, default=64)
    parser.add_argument("--maximum-search-states", type=int, default=10000)
    parser.add_argument("--maximum-candidates-per-step", type=int, default=512)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-realization", action="store_true")
    args = parser.parse_args()

    plan = ProceduralPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    bindings = BindingCatalog.model_validate_json(args.bindings.read_text(encoding="utf-8"))
    templates = _load_templates(args.templates)
    overlay = (
        load_template_overlay(args.template_overlay, templates) if args.template_overlay else None
    )
    if overlay is not None:
        templates = [*templates, *overlay.implementation_bound_templates]
    result = enumerate_realization_space(
        plan,
        bindings,
        templates,
        supplied_proposals=_load_proposals(args.proposals),
        maximum_realizations=args.maximum_realizations,
        maximum_search_states=args.maximum_search_states,
        maximum_candidates_per_step=args.maximum_candidates_per_step,
        template_overlay_sha256=overlay.content_sha256 if overlay else None,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(f"[realizations] campaign: {result.campaign_id}")
    print(f"[realizations] status: {result.enumeration_status.value}")
    print(f"[realizations] realizations: {result.realization_count}")
    print("[realizations] procedure assignments: " f"{result.procedure_assignment_variant_count}")
    print("[realizations] behavior contracts: " f"{result.behavior_contract_variant_count}")
    print("[realizations] causal structures: " f"{result.causal_structure_variant_count}")
    print(f"[realizations] serialized schedule graphs: {result.graph_variant_count}")
    print(f"[realizations] search states: {result.search_states_explored}")
    print(f"[realizations] operational status: {result.operational_status}")
    print(f"[realizations] hash: {result.content_sha256}")
    print(f"[realizations] output: {args.output}")
    if args.require_realization and not result.realizations:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
