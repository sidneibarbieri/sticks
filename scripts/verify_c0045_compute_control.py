#!/usr/bin/env python3
"""Verify one C0045 control receipt offline, after its guest has been destroyed."""

import argparse
from pathlib import Path

from runners.c0045_control_replay import verify_c0045_control


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_root", type=Path)
    options = parser.parse_args()
    record = verify_c0045_control(options.run_root)
    print(
        f"C0045 control {record.cell_id}: {record.status}; "
        f"target CPU ticks={record.cpu_ticks_delta}; threshold passed={record.threshold_passed}"
    )


if __name__ == "__main__":
    main()
