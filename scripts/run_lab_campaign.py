#!/usr/bin/env python3
"""
Canonical VM-backed campaign orchestration for STICKS.

This script turns the existing lab helpers into one explicit realism path:

    up_lab -> run_campaign -> collect_evidence -> generate_corpus_state -> teardown

The host-only smoke path remains the baseline reviewer contract. This script is
the provider-aware entry point for campaigns that need a concrete VM substrate.
It preserves honest failure semantics: failed campaigns still refresh the
evidence summary and corpus state before teardown.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parent.parent
UP_LAB_SCRIPT = PROJECT_ROOT / "scripts" / "up_lab.sh"
DESTROY_LAB_SCRIPT = PROJECT_ROOT / "scripts" / "destroy_lab.sh"
RUN_CAMPAIGN_SCRIPT = PROJECT_ROOT / "scripts" / "run_campaign.py"
COLLECT_EVIDENCE_SCRIPT = PROJECT_ROOT / "scripts" / "collect_evidence.sh"
GENERATE_CORPUS_STATE_SCRIPT = PROJECT_ROOT / "scripts" / "generate_corpus_state.py"


def _log(message: str) -> None:
    print(f"[RUN-LAB] {message}", flush=True)


def _build_up_command(campaign_id: str, provider: str | None) -> list[str]:
    command = ["bash", str(UP_LAB_SCRIPT), "--campaign", campaign_id]
    if provider:
        command.extend(["--provider", provider])
    return command


def _build_destroy_command(campaign_id: str) -> list[str]:
    return ["bash", str(DESTROY_LAB_SCRIPT), "--campaign", campaign_id]


def _run_command(command: Sequence[str], label: str) -> None:
    _log(f"Starting: {label}")
    subprocess.run(
        list(command),
        cwd=str(PROJECT_ROOT),
        check=True,
        env=os.environ.copy(),
    )
    _log(f"Completed: {label}")


def _raise_errors(errors: list[BaseException]) -> None:
    if not errors:
        return
    if len(errors) == 1:
        raise errors[0]
    raise ExceptionGroup("VM-backed execution encountered multiple failures", errors)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Canonical VM-backed campaign execution for STICKS."
    )
    parser.add_argument("--campaign", required=True, help="Campaign ID to execute.")
    parser.add_argument(
        "--provider",
        choices=["qemu", "libvirt", "virtualbox"],
        help="Explicit Vagrant provider. Omit to use host-aware detection in up_lab.sh.",
    )
    parser.add_argument(
        "--keep-lab",
        action="store_true",
        help="Keep the lab running after execution for manual inspection.",
    )
    parser.add_argument(
        "--skip-collect-evidence",
        action="store_true",
        help="Skip evidence/report refresh after the campaign run.",
    )
    parser.add_argument(
        "--assume-lab-running",
        action="store_true",
        help=(
            "Opt-in development mode: skip infrastructure startup and assume a "
            "compatible lab is already running."
        ),
    )
    return parser.parse_args(argv)


def run_lab_campaign(args: argparse.Namespace) -> int:
    errors: list[BaseException] = []

    try:
        if args.assume_lab_running:
            _log("Skipping lab startup because --assume-lab-running was requested")
        else:
            try:
                _run_command(_build_up_command(args.campaign, args.provider), "bring up lab")
            except BaseException as error:
                errors.append(error)

        if not errors:
            try:
                _run_command(
                    [sys.executable, str(RUN_CAMPAIGN_SCRIPT), "--campaign", args.campaign],
                    "execute campaign",
                )
            except BaseException as error:
                errors.append(error)

        if not args.skip_collect_evidence and errors:
            try:
                _run_command(
                    ["bash", str(COLLECT_EVIDENCE_SCRIPT)],
                    "refresh evidence summary",
                )
            except BaseException as error:
                errors.append(error)

            try:
                _run_command(
                    [sys.executable, str(GENERATE_CORPUS_STATE_SCRIPT)],
                    "refresh corpus state",
                )
            except BaseException as error:
                errors.append(error)

        elif not args.skip_collect_evidence:
            try:
                _run_command(
                    ["bash", str(COLLECT_EVIDENCE_SCRIPT)],
                    "refresh evidence summary",
                )
            except BaseException as error:
                errors.append(error)

            try:
                _run_command(
                    [sys.executable, str(GENERATE_CORPUS_STATE_SCRIPT)],
                    "refresh corpus state",
                )
            except BaseException as error:
                errors.append(error)
    finally:
        if args.keep_lab:
            _log("Keeping lab running because --keep-lab was requested")
        else:
            try:
                _run_command(_build_destroy_command(args.campaign), "tear down lab")
            except BaseException as error:
                errors.append(error)

    _raise_errors(errors)
    _log("VM-backed execution path completed successfully")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    return run_lab_campaign(args)


if __name__ == "__main__":
    raise SystemExit(main())
