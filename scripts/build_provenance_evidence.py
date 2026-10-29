#!/usr/bin/env python3
"""Emit per-decision provenance evidence for the frozen campaign contracts.

For each campaign this concretizes the procedural plan deterministically (no LLM) against
its declared environment, attributes every mechanism and binding decision, and writes the
frozen provenance record. The paper consumes these records; it does not regenerate them.
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
from concretization.pipeline import concretize_plan  # noqa: E402
from contracts.procedural_ir import ProceduralPlan  # noqa: E402
from evaluation.provenance import CampaignProvenance, analyze_plan  # noqa: E402
from evaluation.provenance_conformance import audit_source_coverage  # noqa: E402

DEFAULT_CAMPAIGNS = ("C0010", "C0026", "C0045")
PLANS_DIR = PROJECT_ROOT / "release" / "plans"
TEMPLATES_PATH = PROJECT_ROOT / "data" / "concretization" / "action_templates.json"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "release" / "experiments" / "provenance"


def _load_templates() -> tuple[list[ActionTemplate], list[dict]]:
    raw = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))["templates"]
    return [ActionTemplate.model_validate(item) for item in raw], raw


def build_campaign_provenance(campaign_id: str) -> CampaignProvenance:
    plan = ProceduralPlan.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.procedural-plan.json").read_text(encoding="utf-8")
    )
    catalog = BindingCatalog.model_validate_json(
        (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
    )
    templates, raw_templates = _load_templates()
    concretized = concretize_plan(plan, catalog, templates, llm_proposals=[])
    if concretized.unresolved_technique_ids:
        raise RuntimeError(
            f"{campaign_id} did not fully resolve: {concretized.unresolved_technique_ids}"
        )
    return analyze_plan(
        campaign_id,
        concretized.model_dump(mode="json")["steps"],
        catalog.model_dump(mode="json")["bindings"],
        raw_templates,
    )


def _print_row(provenance: CampaignProvenance) -> None:
    print(
        f"{provenance.campaign_id:7s} "
        f"steps={provenance.total_steps:2d} "
        f"bindings={provenance.total_binding_occurrences:2d} | "
        f"cti={provenance.cti_binding_rate:5.0%} "
        f"env={provenance.environment_binding_rate:5.0%} "
        f"system_introduced={provenance.system_introduced_rate:5.0%} | "
        f"proposer_chosen_mechanism={provenance.proposer_chosen_mechanism_rate:5.0%}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaigns", nargs="+", default=list(DEFAULT_CAMPAIGNS))
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    all_bindings: list[dict] = []
    for campaign_id in args.campaigns:
        provenance = build_campaign_provenance(campaign_id)
        _print_row(provenance)
        output_path = args.output_dir / f"{campaign_id}.provenance.json"
        output_path.write_text(
            provenance.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        catalog = BindingCatalog.model_validate_json(
            (PLANS_DIR / f"{campaign_id}.binding-catalog.json").read_text(encoding="utf-8")
        )
        all_bindings.extend(catalog.model_dump(mode="json")["bindings"])

    coverage = audit_source_coverage(all_bindings)
    (args.output_dir / "source_coverage.json").write_text(
        coverage.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[provenance] source coverage: conformant={coverage.conformant} "
        f"observed={ {s: c.value for s, c in coverage.observed_sources.items()} }"
    )
    print(f"[provenance] wrote {len(args.campaigns)} record(s) to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
