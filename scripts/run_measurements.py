#!/usr/bin/env python3
"""
Run all measurement pipelines and generate paper-ready artifacts.

Orchestrates:
1. Paper 1 values (analyze_campaigns.py)
2. Paper 1 identifiability (analyze_identifiability.py)
3. Paper 1 robustness (analyze_robustness.py)
4. Paper 1 appendix (analyze_appendix.py)
5. Evidence tables (generate_tables.py)
6. Paper-ready artifacts (generate_paper_ready_artifacts.py)
7. Paper 2 SUT measurement pipeline
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
SUT_PIPELINE = PROJECT_ROOT / "measurement" / "sut" / "scripts" / "sut_measurement_pipeline.py"


STEPS = [
    ("Paper 1 values", [sys.executable, str(SCRIPTS_DIR / "analyze_campaigns.py")]),
    ("Paper 1 identifiability", [sys.executable, str(SCRIPTS_DIR / "analyze_identifiability.py")]),
    ("Paper 1 robustness", [sys.executable, str(SCRIPTS_DIR / "analyze_robustness.py")]),
    ("Paper 1 appendix", [sys.executable, str(SCRIPTS_DIR / "analyze_appendix.py")]),
    ("Evidence tables", [sys.executable, str(SCRIPTS_DIR / "generate_tables.py")]),
    ("Paper-ready artifacts", [sys.executable, str(SCRIPTS_DIR / "generate_paper_ready_artifacts.py")]),
]

if SUT_PIPELINE.exists():
    STEPS.append(("Paper 2 SUT pipeline", [sys.executable, str(SUT_PIPELINE)]))


def main() -> int:
    failed = []
    for label, cmd in STEPS:
        print(f"\n{'=' * 60}")
        print(f"  {label}")
        print(f"{'=' * 60}")
        result = subprocess.run(cmd, cwd=PROJECT_ROOT)
        if result.returncode != 0:
            failed.append(label)
            print(f"  FAILED (exit {result.returncode})")
        else:
            print(f"  OK")

    print(f"\n{'=' * 60}")
    if failed:
        print(f"  {len(failed)} step(s) failed: {', '.join(failed)}")
        return 1

    print(f"  All {len(STEPS)} measurement steps completed successfully.")
    print(f"  Results in: {PROJECT_ROOT / 'results'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
