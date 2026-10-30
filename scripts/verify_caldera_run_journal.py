"""Verify retained dispatch consistency and campaign observation boot binding."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from runners.caldera_journal import verify_journal as verify_retained_journal


def verify_journal(evidence: Path) -> dict[str, object]:
    """Preserve the CLI's versioned JSON contract for existing callers."""
    return verify_retained_journal(evidence).model_dump(by_alias=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    print(json.dumps(verify_journal(parser.parse_args().evidence), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
