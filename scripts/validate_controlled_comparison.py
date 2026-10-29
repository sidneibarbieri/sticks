#!/usr/bin/env python3
"""Validate a frozen comparison manifest and its complete run ledger."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.controlled_comparison import (  # noqa: E402
    ControlledComparisonManifest,
    RunLedger,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument(
        "--evidence-root",
        type=Path,
        help="root for verifying every successful run's evidence references",
    )
    parser.add_argument("--minimum-seeds", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = ControlledComparisonManifest.model_validate_json(
        args.manifest.read_text(encoding="utf-8")
    )
    ledger = RunLedger.model_validate_json(args.ledger.read_text(encoding="utf-8"))
    manifest.validate_collection_ready(minimum_seeds=args.minimum_seeds)
    ledger.validate_against(manifest)
    successful = [record for record in ledger.records if record.status.value == "succeeded"]
    if successful and args.evidence_root is None:
        raise ValueError("--evidence-root is required when the ledger contains successful runs")
    if args.evidence_root is not None:
        evidence_root = args.evidence_root.resolve()
        ledger.validate_evidence(evidence_root)
        ledger.validate_execution_evidence(evidence_root)
    print(
        f"[controlled-comparison] {len(ledger.records)} runs accounted for "
        f"experiment {manifest.experiment_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
