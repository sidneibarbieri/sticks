#!/usr/bin/env python3
"""Audit frozen corpus readiness for bounded Stage 2 planning curation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.workbench import (  # noqa: E402
    RealizationWorkbench,
    WorkbenchCurationReadinessRequest,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--maximum-realizations", type=int, default=64)
    parser.add_argument("--maximum-search-states", type=int, default=10000)
    parser.add_argument("--maximum-candidates-per-step", type=int, default=512)
    parser.add_argument("--desired-procedure-assignments-per-step", type=int, default=2)
    parser.add_argument("--desired-behavior-contracts-per-step", type=int, default=2)
    parser.add_argument("--maximum-generation-targets", type=int, default=12)
    args = parser.parse_args()

    report = RealizationWorkbench(args.artifact_root).audit_curation_readiness(
        WorkbenchCurationReadinessRequest(
            maximum_realizations=args.maximum_realizations,
            maximum_search_states=args.maximum_search_states,
            maximum_candidates_per_step=args.maximum_candidates_per_step,
            desired_procedure_assignments_per_step=(
                args.desired_procedure_assignments_per_step
            ),
            desired_behavior_contracts_per_step=(
                args.desired_behavior_contracts_per_step
            ),
            maximum_generation_targets=args.maximum_generation_targets,
        )
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output:
        output.write(report.model_dump_json(indent=2) + "\n")
    print(f"[stage2-readiness] campaigns: {report.campaign_count}")
    print(f"[stage2-readiness] frozen inputs ready: {report.frozen_input_ready_count}")
    print(
        "[stage2-readiness] bounded planning ready: "
        f"{report.bounded_planning_ready_count}"
    )
    print(f"[stage2-readiness] operational status: {report.operational_status}")
    print(f"[stage2-readiness] hash: {report.content_sha256}")
    print(f"[stage2-readiness] output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
