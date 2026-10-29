"""Observe, tear down, and seal one retained CostaRicto QEMU run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


CAMPAIGN_ID = "0.costaricto"


def run_workspace_script(run_root: Path, script_name: str) -> None:
    workspace = run_root / "workspace"
    subprocess.run(
        [sys.executable, str(workspace / "scripts" / script_name),
         "--run-root", str(run_root)],
        cwd=workspace,
        check=True,
    )


def observe_target(run_root: Path) -> None:
    run_workspace_script(run_root, "observe_costaricto_target.py")


def destroy_lab(run_root: Path) -> None:
    workspace = run_root / "workspace"
    subprocess.run(
        ["bash", str(workspace / "scripts/destroy_lab.sh"), "--campaign", CAMPAIGN_ID],
        cwd=workspace,
        check=True,
    )


def finalize_run(run_root: Path) -> None:
    run_workspace_script(run_root, "finalize_isolated_lab_run.py")


def complete_run(run_root: Path) -> None:
    context = json.loads((run_root / "run_context.json").read_text(encoding="utf-8"))
    if context["campaign_id"] != CAMPAIGN_ID or not context["keep_lab_requested"]:
        raise ValueError("Completion requires a retained CostaRicto lab run")
    errors: list[BaseException] = []
    if context["exit_code"] != 0:
        errors.append(ValueError("Campaign failed; inspect its retained evidence"))
    else:
        try:
            evidence = run_root / "evidence"
            receipt_exists = (evidence / "costaricto-target-observation.json").exists()
            transport_exists = (evidence / "costaricto-target-observation.transport.json").exists()
            if receipt_exists != transport_exists:
                raise ValueError("Incomplete CostaRicto observation; inspect retained evidence")
            if not receipt_exists:
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
    complete_run(args.run_root.resolve(strict=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
