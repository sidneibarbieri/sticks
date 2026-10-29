#!/usr/bin/env python3
"""Verify a retained C0045 treatment without starting any VM."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runners.c0045_treatment_replay import verify_c0045_treatment  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    options = parser.parse_args()
    report = verify_c0045_treatment(options.run_root)
    print(
        f"C0045 replay: {report.status}; "
        f"uncollected controls: {', '.join(report.uncollected_controls)}"
    )


if __name__ == "__main__":
    main()
