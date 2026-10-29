#!/usr/bin/env python3
"""Synchronize STICKS manuscript inputs from generated release evidence."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAPER_DIR = PROJECT_ROOT.parent / "paper"
GENERATED_INPUTS = {
    PROJECT_ROOT / "release" / "paper_macros.tex": "paper_macros.tex",
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "enrichment_baseline"
    / "baseline_table.tex": "baseline_table.tex",
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "execution_commitments"
    / "commitments_table.tex": "commitments_table.tex",
    PROJECT_ROOT
    / "release"
    / "experiments"
    / "provenance"
    / "provenance_table.tex": "provenance_table.tex",
    PROJECT_ROOT
    / "release"
    / "claims"
    / "claim_ledger_table.tex": "claim_ledger_table.tex",
}


def synchronize(paper_dir: Path, *, check: bool) -> None:
    results_dir = paper_dir / "results"
    if not check:
        results_dir.mkdir(parents=True, exist_ok=True)

    stale: list[str] = []
    for source, destination_name in GENERATED_INPUTS.items():
        if not source.is_file():
            raise FileNotFoundError(f"missing generated release input: {source}")
        destination = results_dir / destination_name
        if not destination.is_file() or source.read_bytes() != destination.read_bytes():
            stale.append(destination_name)
            if not check:
                shutil.copy2(source, destination)

    if check and stale:
        raise SystemExit(
            "manuscript inputs are stale or missing: " + ", ".join(sorted(stale))
        )
    action = "checked" if check else "synchronized"
    print(f"[manuscript-sync] {action} {len(GENERATED_INPUTS)} generated inputs")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--paper-dir", type=Path, default=DEFAULT_PAPER_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    synchronize(args.paper_dir.resolve(), check=args.check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
