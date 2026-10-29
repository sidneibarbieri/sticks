#!/usr/bin/env python3
"""Execute only the reviewed C0045 treatment against an existing isolated VM."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runners.c0045_treatment_run import run_c0045_treatment  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--execute", action="store_true",
        help="Acknowledge that a bounded CPU workload will run in the declared guest",
    )
    options = parser.parse_args()
    if not options.execute:
        parser.error("--execute is required for a live treatment")
    report, run_root = run_c0045_treatment(options.output_dir)
    print(f"C0045 treatment: {report.status}; retained at {run_root}")


if __name__ == "__main__":
    main()
