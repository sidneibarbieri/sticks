#!/usr/bin/env python3
"""Run one selected C0045 control in an existing isolated QEMU guest."""

import argparse
from pathlib import Path

from runners.c0045_control_run import run_c0045_control


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    options = parser.parse_args()
    record, run_root = run_c0045_control(options.cell_id, options.output_dir)
    print(f"C0045 control {record.cell_id}: {record.status}; retained at {run_root}")


if __name__ == "__main__":
    main()
