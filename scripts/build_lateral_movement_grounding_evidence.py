#!/usr/bin/env python3
"""Emit the lateral-movement grounding evidence from the pinned compiled plans.

Grades every credential-to-lateral-movement chain in the corpus by whether the lateral step's
own procedure description supports a causal ordering. Deterministic and offline. The paper
consumes the frozen record when arguing which backend a grounded multi-host chain requires.
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

from evaluation.lateral_movement_grounding import evaluate  # noqa: E402

PLANS_DIR = PROJECT_ROOT / "release" / "plans" / "enterprise"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "release" / "experiments" / "lateral_movement_grounding" / "grounding.json"
)


def _load_plans() -> list[dict]:
    plans = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(PLANS_DIR.glob("*.procedural-plan.json"))
    ]
    if not plans:
        raise FileNotFoundError(f"no compiled plans under {PLANS_DIR}")
    return plans


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    grounding = evaluate(_load_plans())

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(grounding.model_dump_json(indent=2) + "\n", encoding="utf-8")
    print(
        f"[lateral-movement-grounding] {grounding.lateral_steps_examined} lateral steps across "
        f"{grounding.campaigns_examined} campaigns: {grounding.cti_grounded_steps} CTI-grounded, "
        f"{grounding.independent_mechanism_steps} independent-mechanism, "
        f"{grounding.ungrounded_cooccurrence_steps} co-occurrence-only; "
        f"CTI-grounded and Linux-capable: {grounding.cti_grounded_linux_capable_steps}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
