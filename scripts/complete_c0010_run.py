"""Observe, tear down, and seal one retained C0010 QEMU run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


CAMPAIGN_ID = "0.c0010"


def run_context(run_root: Path) -> dict:
    """Read the C0010 run identity before acting on its workspace."""
    context = json.loads((run_root / "run_context.json").read_text(encoding="utf-8"))
    if context["campaign_id"] != CAMPAIGN_ID or not context["keep_lab_requested"]:
        raise ValueError("Completion requires a retained C0010 lab run")
    return context


def observe_target(run_root: Path) -> None:
    """Run the packaged guest observer without replacing existing evidence."""
    workspace = run_root / "workspace"
    observer = workspace / "scripts" / "observe_c0010_target.py"
    subprocess.run(
        [sys.executable, str(observer), "--run-root", str(run_root)],
        cwd=workspace,
        check=True,
    )


def destroy_lab(run_root: Path) -> None:
    """Destroy only the VMs declared for C0010."""
    workspace = run_root / "workspace"
    subprocess.run(
        ["bash", str(workspace / "scripts" / "destroy_lab.sh"), "--campaign", CAMPAIGN_ID],
        cwd=workspace,
        check=True,
    )


def finalize_run(run_root: Path) -> None:
    """Seal the observed run after successful teardown."""
    workspace = run_root / "workspace"
    finalizer = workspace / "scripts" / "finalize_isolated_lab_run.py"
    subprocess.run(
        [sys.executable, str(finalizer), "--run-root", str(run_root)],
        cwd=workspace,
        check=True,
    )


def complete_run(run_root: Path) -> None:
    """Preserve failures while always attempting campaign-scoped cleanup."""
    context = run_context(run_root)
    errors: list[BaseException] = []
    if context["exit_code"] != 0:
        errors.append(ValueError("Campaign failed; inspect its retained evidence"))
    else:
        try:
            evidence = run_root / "evidence"
            if (evidence / "caldera-session.json").is_file():
                workspace = run_root / "workspace"
                subprocess.run(
                    [sys.executable, str(workspace / "scripts/verify_caldera_run_journal.py"),
                     "--evidence", str(evidence)],
                    cwd=workspace, check=True,
                )
            observation_exists = (evidence / "c0010-target-observation.json").exists()
            transport_exists = (evidence / "c0010-target-observation.transport.json").exists()
            if observation_exists != transport_exists:
                raise ValueError("Incomplete C0010 observation; inspect retained evidence")
            if not observation_exists:
                observe_target(run_root)
        except BaseException as error:
            errors.append(error)
    try:
        destroy_lab(run_root)
    except BaseException as error:
        errors.append(error)
    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise BaseExceptionGroup("Observation and teardown both failed", errors)
    finalize_run(run_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    complete_run(args.run_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
