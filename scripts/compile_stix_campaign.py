#!/usr/bin/env python3
"""Compile one ATT&CK campaign into the versioned STICKS procedural IR."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from compilers.stix_campaign_compiler import compile_campaign


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", help="ATT&CK campaign identifier, for example C0001")
    parser.add_argument(
        "--bundle",
        type=Path,
        default=PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    plan = compile_campaign(args.bundle, args.campaign)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    print(f"[compile-stix] campaign: {plan.campaign_id}")
    print(f"[compile-stix] techniques: {len(plan.steps)}")
    print(f"[compile-stix] output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
