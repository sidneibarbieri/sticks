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

from concretization.workbench import (  # noqa: E402
    RealizationWorkbench,
    WorkbenchEnumerationRequest,
    WorkbenchEnumerationResponse,
)
from concretization.workbench_http import serve_workbench  # noqa: E402


def enumerate_from_file(
    workbench: RealizationWorkbench,
    input_path: Path,
    *,
    from_result: bool,
) -> WorkbenchEnumerationResponse:
    reference = (
        WorkbenchEnumerationResponse.model_validate_json(
            input_path.read_text(encoding="utf-8")
        )
        if from_result
        else None
    )
    request = (
        reference.request
        if reference is not None
        else WorkbenchEnumerationRequest.model_validate_json(
            input_path.read_text(encoding="utf-8")
        )
    )
    response = workbench.enumerate_campaign(request)
    if reference is not None and response.model_dump(
        mode="json"
    ) != reference.model_dump(mode="json"):
        raise ValueError(
            "Recomputed planning result differs from the supplied export. "
            "Check the artifact inputs, version and request; no output was written."
        )
    return response


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8765, type=int)
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument(
        "--request", type=Path, help="Enumerate a workbench request JSON"
    )
    inputs.add_argument(
        "--from-result", type=Path, help="Recompute and compare a workbench JSON export"
    )
    parser.add_argument(
        "--output", type=Path, help="New output file for a CLI planning result"
    )
    args = parser.parse_args()
    input_path = args.request or args.from_result
    if bool(input_path) != bool(args.output):
        parser.error(
            "CLI mode requires --request or --from-result together with --output"
        )
    if input_path is not None:
        if input_path.resolve() == args.output.resolve():
            parser.error("The output must differ from the input")
        response = enumerate_from_file(
            RealizationWorkbench(PROJECT_ROOT),
            input_path,
            from_result=args.from_result is not None,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as output:
            output.write(response.model_dump_json(indent=2) + "\n")
        print(f"[workbench] campaign: {response.campaign.campaign_id}")
        print(f"[workbench] operational status: {response.result.operational_status}")
        print(f"[workbench] output: {args.output}")
        return 0
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
