#!/usr/bin/env python3
"""
Canonical VM-backed campaign orchestration for STICKS.

This script turns the existing lab helpers into one explicit realism path:

    up_lab -> run_campaign -> collect_evidence -> generate_corpus_state -> teardown

This is the provider-aware canonical execution path. Host-local runs may still
be useful for unit tests, but they are not campaign/SUT evidence and are never
used by the reviewer-facing artifact wrapper.
It preserves honest failure semantics: failed campaigns still refresh the
evidence summary and corpus state before teardown.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from runners.caldera_campaign_support import SUPPORTED_CALDERA_CAMPAIGNS
UP_LAB_SCRIPT = PROJECT_ROOT / "scripts" / "up_lab.sh"
DESTROY_LAB_SCRIPT = PROJECT_ROOT / "scripts" / "destroy_lab.sh"
RUN_CAMPAIGN_SCRIPT = PROJECT_ROOT / "scripts" / "run_campaign.py"
COLLECT_EVIDENCE_SCRIPT = PROJECT_ROOT / "scripts" / "collect_evidence.sh"
GENERATE_CORPUS_STATE_SCRIPT = PROJECT_ROOT / "scripts" / "generate_corpus_state.py"
EVIDENCE_DIR = PROJECT_ROOT / "release" / "evidence"
SNAPSHOT_ROOTS = (
    PROJECT_ROOT / "release",
    PROJECT_ROOT / "results",
)
RUNTIME_ONLY_DIRS = (
    PROJECT_ROOT / "release" / "realistic_data",
    PROJECT_ROOT / "release" / "sut_reports",
)
SNAPSHOT_SKIP_DIRS = (
    PROJECT_ROOT / "release" / "evidence",
    PROJECT_ROOT / "results" / "evidence",
    *RUNTIME_ONLY_DIRS,
)
RECOVERABLE_FAILURES = (OSError, subprocess.SubprocessError, RuntimeError, ValueError)


def _log(message: str) -> None:
    print(f"[RUN-LAB] {message}", flush=True)


def _build_up_command(campaign_id: str, provider: str | None) -> list[str]:
    command = ["bash", str(UP_LAB_SCRIPT), "--campaign", campaign_id]
    if provider:
        command.extend(["--provider", provider])
    return command


def _build_destroy_command(campaign_id: str) -> list[str]:
    return ["bash", str(DESTROY_LAB_SCRIPT), "--campaign", campaign_id]


def _run_command(
    command: Sequence[str],
    label: str,
    environment: dict[str, str] | None = None,
) -> None:
    _log(f"Starting: {label}")
    subprocess.run(
        list(command),
        cwd=str(PROJECT_ROOT),
        check=True,
        env=environment or os.environ.copy(),
    )
    _log(f"Completed: {label}")


def _raise_errors(errors: list[Exception]) -> None:
    if not errors:
        return
    if len(errors) == 1:
        raise errors[0]
    raise ExceptionGroup("VM-backed execution encountered multiple failures", errors)


def _evidence_available(evidence_dir: Path) -> bool:
    return evidence_dir.exists() and any(evidence_dir.iterdir())


def _is_within(path: Path, candidate_root: Path) -> bool:
    return path == candidate_root or candidate_root in path.parents


def _iter_snapshot_files() -> list[Path]:
    files: list[Path] = []
    for root in SNAPSHOT_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if any(_is_within(path, skip_dir) for skip_dir in SNAPSHOT_SKIP_DIRS):
                continue
            files.append(path)
    return files


def _remove_empty_directories(root: Path) -> None:
    if not root.exists():
        return
    for directory in sorted(
        (path for path in root.rglob("*") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if any(_is_within(directory, skip_dir) for skip_dir in SNAPSHOT_SKIP_DIRS):
            continue
        try:
            directory.rmdir()
        except OSError:
            continue


class _DerivedStateSnapshot:
    def __init__(self, temp_dir: tempfile.TemporaryDirectory[str], files: dict[Path, Path]):
        self._temp_dir = temp_dir
        self._files = files
        self._restored = False

    @classmethod
    def capture(cls) -> _DerivedStateSnapshot:
        temp_dir = tempfile.TemporaryDirectory(prefix="sticks_derived_state_")
        snapshot_root = Path(temp_dir.name)
        files: dict[Path, Path] = {}

        for source_path in _iter_snapshot_files():
            relative_path = source_path.relative_to(PROJECT_ROOT)
            snapshot_path = snapshot_root / relative_path
            snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_path, snapshot_path)
            files[source_path] = snapshot_path

        return cls(temp_dir, files)

    def restore(self) -> None:
        if self._restored:
            return

        original_paths = set(self._files.keys())
        current_paths = set(_iter_snapshot_files())

        for extra_path in current_paths - original_paths:
            extra_path.unlink()

        for live_path, snapshot_path in self._files.items():
            live_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(snapshot_path, live_path)

        for root in SNAPSHOT_ROOTS:
            _remove_empty_directories(root)

        self._temp_dir.cleanup()
        self._restored = True

    def discard(self) -> None:
        """Release only the private snapshot after a retained run succeeds."""
        if self._restored:
            return
        self._temp_dir.cleanup()
        self._restored = True


def _capture_derived_state() -> _DerivedStateSnapshot:
    return _DerivedStateSnapshot.capture()


def _cleanup_runtime_outputs() -> None:
    for runtime_dir in RUNTIME_ONLY_DIRS:
        shutil.rmtree(runtime_dir, ignore_errors=True)


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
            "compatible lab is already running. The pre-existing lab is preserved "
            "unless --tear-down-assumed-lab is also set."
        ),
    )
    parser.add_argument(
        "--tear-down-assumed-lab",
        action="store_true",
        help=(
            "Allow teardown of a lab selected with --assume-lab-running. This is "
            "required because the current invocation did not create that lab."
        ),
    )
    parser.add_argument(
        "--persist-derived-state",
        action="store_true",
        help=(
            "Keep refreshed release/results summaries and runtime-only outputs in the "
            "checkout after the run."
        ),
    )
    parser.add_argument(
        "--evidence-output",
        type=Path,
        help=(
            "Write campaign evidence to this directory instead of release/evidence. "
            "Use a distinct prospective run directory to preserve frozen evidence."
        ),
    )
    parser.add_argument("--caldera-session", type=Path,
                        help="Prepared isolated CALDERA session for target execution")
    parser.add_argument("--caldera-dispatch", action="store_true",
                        help="Enroll a target agent after lab startup and dispatch through CALDERA")
    args = parser.parse_args(argv)
    if args.caldera_session and args.caldera_dispatch:
        parser.error("Select either a prepared session or fresh CALDERA enrollment")
    if (args.caldera_session or args.caldera_dispatch) and args.campaign not in SUPPORTED_CALDERA_CAMPAIGNS:
        parser.error("CALDERA session requires a reviewed C0010 or C0026 campaign")
    return args


def run_lab_campaign(args: argparse.Namespace) -> int:
    from runners.lab_campaign_support import require_live_campaign

    require_live_campaign(args.campaign)
    errors: list[Exception] = []
    lab_started = bool(args.assume_lab_running)
    snapshot = None if args.persist_derived_state else _capture_derived_state()
    evidence_output = (
        args.evidence_output.resolve() if args.evidence_output else EVIDENCE_DIR
    )
    command_environment = os.environ.copy()
    command_environment["STICKS_EVIDENCE_DIR"] = str(evidence_output)
    isolated_evidence = evidence_output != EVIDENCE_DIR

    if args.persist_derived_state:
        _log("Preserving derived state because --persist-derived-state was requested")
    if isolated_evidence:
        _log(f"Writing prospective evidence to {evidence_output}")

    try:
        if args.assume_lab_running:
            _log("Skipping lab startup because --assume-lab-running was requested")
        else:
            try:
                _run_command(
                    _build_up_command(args.campaign, args.provider),
                    "bring up lab",
                    command_environment,
                )
                lab_started = True
            except RECOVERABLE_FAILURES as error:
                errors.append(error)

        if not errors:
            try:
                session_path = args.caldera_session
                if args.caldera_dispatch:
                    session_path = evidence_output / "caldera-session.json"
                    _run_command(
                        [sys.executable, str(PROJECT_ROOT / "scripts/prepare_caldera_session.py"),
                         "--lab-root", str(PROJECT_ROOT / "lab/vagrant"),
                         "--output", str(session_path)],
                        "enroll fresh target agent", command_environment,
                    )
                campaign_command = [
                    sys.executable,
                    str(RUN_CAMPAIGN_SCRIPT),
                    "--campaign",
                    args.campaign,
                    "--require-lab",
                ]
                if isolated_evidence:
                    campaign_command.extend(["--output", str(evidence_output)])
                if session_path:
                    campaign_command.extend(["--caldera-session", str(session_path.resolve())])
                _run_command(
                    campaign_command,
                    "execute campaign",
                    command_environment,
                )
            except RECOVERABLE_FAILURES as error:
                errors.append(error)

        if isolated_evidence:
            _log("Skipping release summary refresh for isolated prospective evidence")
        elif not args.skip_collect_evidence and not errors:
            try:
                _run_command(
                    ["bash", str(COLLECT_EVIDENCE_SCRIPT)],
                    "refresh evidence summary",
                )
            except RECOVERABLE_FAILURES as error:
                errors.append(error)

            try:
                _run_command(
                    [sys.executable, str(GENERATE_CORPUS_STATE_SCRIPT)],
                    "refresh corpus state",
                )
            except RECOVERABLE_FAILURES as error:
                errors.append(error)

        elif (
            not args.skip_collect_evidence
            and lab_started
            and _evidence_available(evidence_output)
        ):
            _log(
                "Execution failed after lab startup; refreshing evidence and corpus state"
            )
            try:
                _run_command(
                    ["bash", str(COLLECT_EVIDENCE_SCRIPT)],
                    "refresh evidence summary",
                )
            except RECOVERABLE_FAILURES as error:
                errors.append(error)

            try:
                _run_command(
                    [sys.executable, str(GENERATE_CORPUS_STATE_SCRIPT)],
                    "refresh corpus state",
                )
            except RECOVERABLE_FAILURES as error:
                errors.append(error)
        elif errors:
            _log(
                "Skipping evidence refresh because the lab did not reach an evidence-producing state"
            )
    finally:
        if args.keep_lab and not errors:
            _log("Keeping lab running because --keep-lab was requested")
        elif args.assume_lab_running and not args.tear_down_assumed_lab:
            _log("Preserving the pre-existing lab because this run did not create it")
        else:
            try:
                _run_command(
                    _build_destroy_command(args.campaign),
                    "tear down lab",
                    command_environment,
                )
            except RECOVERABLE_FAILURES as error:
                errors.append(error)

        retain_workspace_for_completion = args.keep_lab and not errors
        if retain_workspace_for_completion and snapshot is not None:
            snapshot.discard()
            _log(
                "Preserved derived workspace state for independent observation and sealing"
            )
        elif snapshot is not None:
            try:
                snapshot.restore()
                _cleanup_runtime_outputs()
                _log("Restored tracked derived state and cleaned runtime-only outputs")
            except RECOVERABLE_FAILURES as error:
                errors.append(error)

    _raise_errors(errors)
    _log("VM-backed execution path completed successfully")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    return run_lab_campaign(args)


if __name__ == "__main__":
    raise SystemExit(main())
