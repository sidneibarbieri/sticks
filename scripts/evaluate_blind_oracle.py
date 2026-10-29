#!/usr/bin/env python3
"""Evaluate one arm-blind proposal with the deterministic admission oracle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from concretization.models import ActionTemplate, BindingCatalog  # noqa: E402
from evaluation.controlled_comparison import (  # noqa: E402
    BlindOracleInput,
    evaluate_blind_proposal,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--binding-catalog", type=Path, required=True)
    parser.add_argument("--action-catalog", type=Path, required=True)
    parser.add_argument("--oracle-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def load_templates(path: Path) -> list[ActionTemplate]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload["templates"] if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("action catalog must be a list or contain a templates list")
    return [ActionTemplate.model_validate(record) for record in records]


def main() -> int:
    args = parse_args()
    oracle_input = BlindOracleInput.model_validate_json(args.input.read_text(encoding="utf-8"))
    catalog = BindingCatalog.model_validate_json(args.binding_catalog.read_text(encoding="utf-8"))
    decision = evaluate_blind_proposal(
        oracle_input,
        templates=load_templates(args.action_catalog),
        catalog=catalog,
        oracle_revision=args.oracle_revision,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as output_file:
        output_file.write(decision.model_dump_json(indent=2) + "\n")
    print(f"[blind-oracle] {decision.blind_id}: accepted={decision.accepted}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
