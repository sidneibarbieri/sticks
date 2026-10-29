#!/usr/bin/env python3
"""Run one bounded, non-interactive Stage 2 planning curation pass."""

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
from concretization.fact_semantics import FactSemanticsRegistry  # noqa: E402
from concretization.provider import load_config  # noqa: E402
from concretization.stage2_curation import (  # noqa: E402
    Stage2CurationLimits,
    run_stage2_curation,
)
from concretization.template_overlay import TemplateImplementationWitness  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402


def _object_list(path: Path, key: str) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    values = payload.get(key, []) if isinstance(payload, dict) else payload
    if not isinstance(values, list) or not all(isinstance(item, dict) for item in values):
        raise ValueError(f"{path} must contain a JSON list or an object with a {key} list")
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument(
        "--templates",
        type=Path,
        default=PROJECT_ROOT / "data/concretization/action_templates.json",
    )
    parser.add_argument(
        "--fact-semantics",
        type=Path,
        default=PROJECT_ROOT / "data/concretization/fact_semantics.json",
    )
    parser.add_argument("--provider-config", type=Path, required=True)
    parser.add_argument("--witnesses", type=Path)
    parser.add_argument("--artifact-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--desired-procedure-assignments-per-step", type=int, default=2)
    parser.add_argument("--desired-behavior-contracts-per-step", type=int, default=2)
    parser.add_argument("--maximum-generation-targets", type=int, default=12)
    parser.add_argument("--maximum-realizations", type=int, default=64)
    parser.add_argument("--maximum-search-states", type=int, default=10000)
    parser.add_argument("--maximum-candidates-per-step", type=int, default=512)
    parser.add_argument("--maximum-attempts-per-target", type=int, default=3)
    args = parser.parse_args()

    witnesses = (
        [
            TemplateImplementationWitness.model_validate(item)
            for item in _object_list(args.witnesses, "witnesses")
        ]
        if args.witnesses is not None
        else []
    )
    result = run_stage2_curation(
        ProceduralPlan.model_validate_json(args.plan.read_text(encoding="utf-8")),
        BindingCatalog.model_validate_json(args.bindings.read_text(encoding="utf-8")),
        FactSemanticsRegistry.model_validate_json(args.fact_semantics.read_text(encoding="utf-8")),
        [ActionTemplate.model_validate(item) for item in _object_list(args.templates, "templates")],
        load_config(args.provider_config),
        implementation_witnesses=witnesses,
        artifact_root=args.artifact_root,
        output_dir=args.output_dir,
        limits=Stage2CurationLimits(
            desired_procedure_assignments_per_step=(args.desired_procedure_assignments_per_step),
            desired_behavior_contracts_per_step=(args.desired_behavior_contracts_per_step),
            maximum_generation_targets=args.maximum_generation_targets,
            maximum_realizations=args.maximum_realizations,
            maximum_search_states=args.maximum_search_states,
            maximum_candidates_per_step=args.maximum_candidates_per_step,
            maximum_attempts_per_target=args.maximum_attempts_per_target,
        ),
    )
    ledger = result.ledger
    print(f"[stage2] campaign: {ledger.campaign_id}")
    print(f"[stage2] proposal targets: {ledger.proposal_target_count}")
    print(f"[stage2] provider requests: {ledger.provider_request_count}")
    print(f"[stage2] planning-only candidates: {ledger.planning_only_candidate_count}")
    print(
        "[stage2] implementation-bound candidates: "
        f"{ledger.implementation_bound_candidate_count}"
    )
    print(f"[stage2] outcomes: {', '.join(outcome.value for outcome in ledger.outcomes)}")
    print(f"[stage2] operational status: {ledger.operational_status}")
    print(f"[stage2] ledger hash: {ledger.content_sha256}")
    print(f"[stage2] output: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
