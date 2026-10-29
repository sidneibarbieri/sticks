#!/usr/bin/env python3
"""Emit the corpus-characterization evidence from the pinned Enterprise bundle.

Measures what the public corpus documents on its own, independent of the template catalog.
Deterministic and offline. The paper consumes the frozen record.
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

from evaluation.corpus_characterization import characterize  # noqa: E402

ENTERPRISE_BUNDLE = PROJECT_ROOT / "data" / "stix" / "enterprise-attack.json"
DEFAULT_OUTPUT = (
    PROJECT_ROOT / "release" / "experiments" / "corpus_characterization" / "corpus.json"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    bundle = json.loads(ENTERPRISE_BUNDLE.read_text(encoding="utf-8"))
    characterization = characterize(bundle)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        characterization.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"[corpus-characterization] {characterization.active_techniques} active techniques: "
        f"campaigns reference {characterization.campaign_referenced} "
        f"({characterization.campaign_reference_rate * 100:.1f}%), intrusion sets "
        f"{characterization.intrusion_set_referenced} "
        f"({characterization.intrusion_set_reference_rate * 100:.1f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
