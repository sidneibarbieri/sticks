#!/usr/bin/env python3
"""Validate a completed campaign report against its declared objective.

Exit code 0 when the objective is achieved by observation, 1 otherwise. Refuses an
objective whose terminal facts no registered observer can establish, since such a
goal could never be proven by observation.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from runners.campaign_objective import (  # noqa: E402
    load_objective,
    unobservable_facts,
    verify_objective_receipts,
)
from runners.capability_authority import registered_products  # noqa: E402
from runners.runtime_campaign_report import parse_retained_campaign_report  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--objective", type=Path, required=True)
    arguments = parser.parse_args()

    objective = load_objective(arguments.objective)
    unobservable = unobservable_facts(objective, registered_products())
    if unobservable:
        raise ValueError(f"Objective names unobservable terminal facts: {unobservable}")

    report = parse_retained_campaign_report(
        arguments.report.read_text(encoding="utf-8")
    )
    verdict = verify_objective_receipts(report, objective, arguments.report.parent)
    print(f"campaign {verdict.campaign_id} run {verdict.run_id}")
    print(
        f"achieved={verdict.achieved} "
        f"achieved_via_observation={verdict.achieved_via_observation}"
    )
    for clause in verdict.clauses:
        print(
            f"  {clause.clause.fact}@{clause.clause.locus}: "
            f"satisfied={clause.satisfied} observation_bound={clause.observation_bound} "
            f"origin={clause.origin} producer_occurrence={clause.producer_occurrence}"
        )
    return 0 if verdict.achieved_via_observation else 1


if __name__ == "__main__":
    raise SystemExit(main())
