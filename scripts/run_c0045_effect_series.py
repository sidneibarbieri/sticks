#!/usr/bin/env python3
"""Resume the frozen C0045 series serially without skipping a retained cell."""

import argparse
from collections.abc import Mapping
from pathlib import Path

from runners.c0045_effect_series import SERIES_PATH, load_c0045_effect_series
from runners.c0045_series_run import C0045SeriesOutcome, verify_c0045_series_cell
from scripts.run_c0045_effect_series_cell import cleanup_on_termination, run_fresh_cell


COMPLETE_STATUSES = frozenset({"observed", "measured"})


def retained_outcome(
    output_dir: Path, cell_id: str, series_path: Path = SERIES_PATH
) -> C0045SeriesOutcome | None:
    """Return a verified completed cell, rejecting partial or failed retention."""
    cell_root = output_dir / load_c0045_effect_series(series_path).receipt_root_name / cell_id
    if not cell_root.exists():
        return None
    outcome = verify_c0045_series_cell(output_dir, cell_id, series_path)
    if outcome.status not in COMPLETE_STATUSES:
        raise ValueError(f"C0045 cell is not a completed result: {cell_id}")
    return outcome


def run_pending_cells(
    output_dir: Path,
    provider: str,
    environment: Mapping[str, str] | None = None,
    series_path: Path = SERIES_PATH,
) -> list[C0045SeriesOutcome]:
    """Run only absent cells, in frozen order, stopping at the first anomaly."""
    outcomes: list[C0045SeriesOutcome] = []
    for cell_id in load_c0045_effect_series(series_path).selected_cells:
        outcome = retained_outcome(output_dir, cell_id, series_path)
        if outcome is None:
            if environment is None:
                outcome, _ = run_fresh_cell(
                    cell_id, output_dir, provider, series_path=series_path
                )
            else:
                outcome, _ = run_fresh_cell(
                    cell_id, output_dir, provider, environment, series_path
                )
        outcomes.append(outcome)
    return outcomes


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--series-path", type=Path, default=SERIES_PATH)
    parser.add_argument(
        "--provider", choices=("qemu", "libvirt", "virtualbox"), default="qemu"
    )
    options = parser.parse_args()
    with cleanup_on_termination():
        for outcome in run_pending_cells(
            options.output_dir, options.provider, series_path=options.series_path
        ):
            print(f"C0045 series {outcome.cell_id}: {outcome.status}")


if __name__ == "__main__":
    main()
