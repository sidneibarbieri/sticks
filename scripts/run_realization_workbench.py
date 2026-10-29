#!/usr/bin/env python3
"""Serve the local STICKS realization workbench."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
for import_root in (PROJECT_ROOT, SRC_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from concretization.workbench import RealizationWorkbench  # noqa: E402
from concretization.workbench_http import serve_workbench  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error("port must be between 0 and 65535")
    workbench = RealizationWorkbench(PROJECT_ROOT)
    try:
        serve_workbench(
            workbench,
            PROJECT_ROOT / "web" / "realization-workbench",
            host=args.host,
            port=args.port,
        )
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
