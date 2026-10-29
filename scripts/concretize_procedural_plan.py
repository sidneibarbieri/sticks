#!/usr/bin/env python3
"""Concretize a STICKS plan using finite search and optional LLM proposals."""

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
)
from concretization.pipeline import concretize_plan  # noqa: E402
from concretization.prompt import SYSTEM_PROMPT, build_prompt  # noqa: E402
from concretization.provider import (  # noqa: E402
    BudgetLedger,
    load_config,
    propose,
)
from contracts.procedural_ir import ProceduralPlan  # noqa: E402


def load_templates(path: Path) -> list[ActionTemplate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [
        ActionTemplate.model_validate(item)
        for item in payload.get("templates", [])
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument(
        "--templates",
        type=Path,
        default=PROJECT_ROOT / "data" / "concretization" / "action_templates.json",
    )
    parser.add_argument("--config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unresolved", action="store_true")
    args = parser.parse_args()

    plan = ProceduralPlan.model_validate_json(
        args.plan.read_text(encoding="utf-8")
    )
    bindings = BindingCatalog.model_validate_json(
        args.bindings.read_text(encoding="utf-8")
    )
    templates = load_templates(args.templates)
    llm_proposals = []
    llm_record = None
    if args.config:
        config = load_config(args.config)
        record_dir = args.output.parent / f"{args.output.stem}.llm"
        llm_record = propose(
            config,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=build_prompt(plan, bindings, templates),
            output_dir=record_dir,
            budget=BudgetLedger(config.budget),
        )
        llm_proposals = llm_record.proposals
        (record_dir / "call_record.json").write_text(
            llm_record.model_dump_json(indent=2) + "\n",
            encoding="utf-8",
        )

    result = concretize_plan(
        plan,
        bindings,
        templates,
        llm_proposals=llm_proposals,
    )
    if llm_record is not None:
        result.llm_call_sha256 = llm_record.content_sha256
        result.finalize_hash()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        result.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"[concretize] campaign: {result.campaign_id}")
    print(f"[concretize] resolved: {len(result.steps)}")
    print(f"[concretize] unresolved: {len(result.unresolved_technique_ids)}")
    print(
        "[concretize] execution semantic hash: "
        f"{result.execution_semantic_sha256}"
    )
    print(f"[concretize] semantic hash: {result.content_sha256}")
    print(f"[concretize] output: {args.output}")
    if result.unresolved_technique_ids and not args.allow_unresolved:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
