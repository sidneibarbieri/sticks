#!/usr/bin/env python3
"""Execute the frozen C0045 series only after a strict live-lab preflight."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = (str(PROJECT_ROOT / "src"), str(PROJECT_ROOT))

from runners.strict_execution_profile import (  # noqa: E402
    load_prepared_runtime_manifest,
    load_strict_execution_profile,
    strict_prepared_environment,
)
from runners.c0045_effect_series import SERIES_PATH  # noqa: E402
from scripts.preflight_strict_c0045 import create_receipt  # noqa: E402
from scripts.run_c0045_effect_series import run_pending_cells  # noqa: E402
from scripts.run_c0045_effect_series_cell import (  # noqa: E402
    cleanup_on_termination,
    run_fresh_cell,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--series-path", type=Path, default=SERIES_PATH)
    parser.add_argument(
        "--cell-id",
        help="Run only this next frozen cell instead of the entire remaining series.",
    )
    options = parser.parse_args()
    profile = load_strict_execution_profile()
    expected_series_path = PROJECT_ROOT / profile.series_path
    if options.series_path.resolve() != expected_series_path.resolve():
        raise ValueError("Strict profile is bound to a different frozen C0045 series")
    runtime = load_prepared_runtime_manifest(profile)
    create_receipt(options.output_dir)
    with cleanup_on_termination():
        if options.cell_id is not None:
            outcome, _ = run_fresh_cell(
                options.cell_id,
                options.output_dir,
                "qemu",
                strict_prepared_environment(runtime),
                options.series_path,
            )
            print(f"C0045 strict series {outcome.cell_id}: {outcome.status}")
            return
        for outcome in run_pending_cells(
            options.output_dir,
            "qemu",
            strict_prepared_environment(runtime),
            options.series_path,
        ):
            print(f"C0045 strict series {outcome.cell_id}: {outcome.status}")


if __name__ == "__main__":
    main()
