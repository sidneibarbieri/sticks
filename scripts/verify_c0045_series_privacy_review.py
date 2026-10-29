#!/usr/bin/env python3
"""Verify a hash-bound semantic privacy review for a C0045 archive."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from runners.c0045_privacy_review import verify_c0045_privacy_review


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    options = parser.parse_args()
    review = verify_c0045_privacy_review(options.archive, options.review)
    print(json.dumps(review.model_dump(mode="json"), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
