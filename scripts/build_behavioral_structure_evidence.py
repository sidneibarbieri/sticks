#!/usr/bin/env python3
"""Emit the campaign behavioral-structure evidence from the pinned Enterprise bundle.

Tests whether campaign technique sets form families beyond what their sizes and technique
frequencies imply. Deterministic (seeded) and offline. The paper consumes the frozen record.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from evaluation.behavioral_structure import campaign_technique_sets, measure  # noqa: E402

ENTERPRISE_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
OUTPUT = PROJECT_ROOT / "release" / "experiments" / "behavioral_structure" / "corpus.json"


def main() -> int:
    bundle = json.loads(ENTERPRISE_BUNDLE.read_text(encoding="utf-8"))
    structure = measure(campaign_technique_sets(bundle))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(structure.model_dump_json(indent=2) + "\n", encoding="utf-8")
    nearest = structure.nearest_neighbor_null
    print(
        f"[behavioral-structure] {structure.campaigns} campaigns; nearest-neighbor Jaccard "
        f"{structure.observed.mean_nearest_neighbor_jaccard:.2f} vs null {nearest.null_mean:.2f} "
        f"({nearest.draws_at_least_observed}/{nearest.draws} draws at least as high); "
        f"{structure.families} families at {structure.family_similarity}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
