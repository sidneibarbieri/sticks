#!/usr/bin/env python3
"""Render verifier-grounded explanations for a concretized plan."""

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

from concretization.models import BindingCatalog, ConcretizedPlan  # noqa: E402


def render_explanation(plan: ConcretizedPlan, catalog: BindingCatalog) -> dict:
    """Explain each committed step from the verifier's own retrieval and causal record."""
    binding_index = {binding.binding_id: binding for binding in catalog.bindings}
    causal_by_consumer: dict[int, list[dict]] = {}
    if plan.planning_certificate is not None:
        for link in plan.planning_certificate.causal_links:
            causal_by_consumer.setdefault(link.consumer_sequence, []).append(
                link.model_dump(mode="json")
            )
    trace_index = {trace.technique_id: trace for trace in plan.retrieval_traces}
    explanations = []
    for step in plan.steps:
        explanations.append(
            {
                "sequence": step.sequence,
                "technique_id": step.technique_id,
                "selected_template": step.template_id,
                "selection_source": step.proposal_source,
                "retrieval": trace_index[step.technique_id].model_dump(mode="json"),
                "bindings": {
                    parameter: {
                        "binding_id": binding_id,
                        "kind": binding_index[binding_id].kind,
                        "source": binding_index[binding_id].source,
                        "scope": binding_index[binding_id].scope.value,
                        "secret_reference": binding_index[binding_id].secret_reference,
                    }
                    for parameter, binding_id in sorted(step.bindings.items())
                },
                "preconditions": step.requires,
                "effects": step.produces,
                "causal_links": causal_by_consumer.get(step.sequence, []),
                "evidence_predicates": step.evidence_predicates,
                "fidelity_ceiling": step.fidelity_ceiling,
                "assumption_count": step.assumption_count,
            }
        )
    return {
        "schema_version": "1",
        "campaign_id": plan.campaign_id,
        "source_plan_sha256": plan.source_plan_sha256,
        "execution_semantic_sha256": plan.execution_semantic_sha256,
        "planning_certificate_sha256": (
            plan.planning_certificate.content_sha256
            if plan.planning_certificate is not None
            else None
        ),
        "steps": explanations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--bindings", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    plan = ConcretizedPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    catalog = BindingCatalog.model_validate_json(args.bindings.read_text(encoding="utf-8"))
    report = render_explanation(plan, catalog)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"[explain] steps: {len(report['steps'])}")
    print(f"[explain] output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
