#!/usr/bin/env python3
"""Run one frozen C0045 cell from an absent lab to a destroyed lab."""

import argparse
import os
import signal
import subprocess
from collections.abc import Mapping
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from runners.c0045_lifecycle import (
    lifecycle_events,
    retain_lifecycle_event,
    unfinished_attempts,
)
from runners.c0045_series_run import C0045SeriesOutcome, run_c0045_series_cell
from runners.c0045_series_run import retain_c0045_series_runner_error
from runners.c0045_series_run import require_next_c0045_series_cell
from runners.c0045_effect_series import SERIES_PATH


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_ID = "0.shadowray"
MANAGED_VMS = ("caldera", "attacker", "target-linux-1")


def _raise_interruption(signal_number: int, _frame: object) -> None:
    """Turn a catchable termination signal into finally-safe control flow."""
    raise KeyboardInterrupt(f"C0045 cell interrupted by signal {signal_number}")


@contextmanager
def cleanup_on_termination() -> Iterator[None]:
    """Ensure catchable termination signals execute the lab teardown path."""
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    previous_handlers = {
        signal_number: signal.getsignal(signal_number) for signal_number in signals
    }
    for signal_number in signals:
        signal.signal(signal_number, _raise_interruption)
    try:
        yield
    finally:
        for signal_number, previous_handler in previous_handlers.items():
            signal.signal(signal_number, previous_handler)


def vm_state(vm_name: str) -> str:
    """Return the unique Vagrant state for a managed laboratory VM."""
    completed = subprocess.run(
        ["vagrant", "status", "--machine-readable"],
        cwd=PROJECT_ROOT / "lab" / "vagrant" / vm_name,
        capture_output=True,
        check=True,
        text=True,
    )
    states = [
        line.split(",", 3)[3]
        for line in completed.stdout.splitlines()
        if len(line.split(",", 3)) == 4 and line.split(",", 3)[2] == "state"
    ]
    if len(states) != 1:
        raise ValueError(f"Expected one Vagrant state for {vm_name}")
    return states[0]


def require_absent_lab() -> None:
    """Reject reuse before a cell can acquire an ambiguous guest boot."""
    states = {vm_name: vm_state(vm_name) for vm_name in MANAGED_VMS}
    if any(state != "not_created" for state in states.values()):
        raise RuntimeError(f"C0045 cell requires an absent lab, found {states}")


def run_command(
    command: list[str], environment: Mapping[str, str] | None = None
) -> None:
    invocation_environment = os.environ | dict(environment or {})
    subprocess.run(command, cwd=PROJECT_ROOT, check=True, env=invocation_environment)


def run_with_environment(
    command: list[str], environment: Mapping[str, str] | None
) -> None:
    """Preserve the normal runner path when a strict environment is absent."""
    if environment is None:
        run_command(command)
    else:
        run_command(command, environment)


def recover_interrupted_attempt(
    output_dir: Path, environment: Mapping[str, str] | None = None
) -> None:
    """Tear down one journaled but unclosed attempt before acquiring the lab."""
    unfinished = unfinished_attempts(lifecycle_events(output_dir))
    if len(unfinished) > 1:
        raise ValueError("C0045 lifecycle has multiple unfinished attempts")
    if not unfinished:
        return
    attempt = unfinished[0]
    run_with_environment(
        [
            "bash",
            str(PROJECT_ROOT / "scripts" / "destroy_lab.sh"),
            "--campaign",
            CAMPAIGN_ID,
        ],
        environment,
    )
    retain_lifecycle_event(
        output_dir,
        attempt_id=attempt.attempt_id,
        cell_id=attempt.cell_id,
        event="recovered_after_interruption",
    )


def run_fresh_cell(
    cell_id: str,
    output_dir: Path,
    provider: str,
    environment: Mapping[str, str] | None = None,
    series_path: Path = SERIES_PATH,
) -> tuple[C0045SeriesOutcome, Path]:
    """Bootstrap, measure, and tear down exactly one fresh C0045 series cell."""
    recover_interrupted_attempt(output_dir, environment)
    require_absent_lab()
    require_next_c0045_series_cell(cell_id, output_dir, series_path)
    attempt_id = uuid4().hex
    retain_lifecycle_event(
        output_dir, attempt_id=attempt_id, cell_id=cell_id, event="boot_started"
    )
    try:
        try:
            run_with_environment(
                [
                    "bash",
                    str(PROJECT_ROOT / "scripts" / "up_lab.sh"),
                    "--campaign",
                    CAMPAIGN_ID,
                    "--provider",
                    provider,
                ],
                environment,
            )
        except Exception as error:
            retain_c0045_series_runner_error(cell_id, output_dir, error, series_path)
            raise
        return run_c0045_series_cell(cell_id, output_dir, series_path)
    finally:
        run_with_environment(
            [
                "bash",
                str(PROJECT_ROOT / "scripts" / "destroy_lab.sh"),
                "--campaign",
                CAMPAIGN_ID,
            ],
            environment,
        )
        retain_lifecycle_event(
            output_dir,
            attempt_id=attempt_id,
            cell_id=cell_id,
            event="teardown_completed",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cell-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--series-path", type=Path, default=SERIES_PATH)
    parser.add_argument(
        "--provider", choices=("qemu", "libvirt", "virtualbox"), default="qemu"
    )
    options = parser.parse_args()
    with cleanup_on_termination():
        outcome, cell_root = run_fresh_cell(
            options.cell_id, options.output_dir, options.provider,
            series_path=options.series_path,
        )
    print(f"C0045 series {outcome.cell_id}: {outcome.status}; retained at {cell_root}")


if __name__ == "__main__":
    main()
