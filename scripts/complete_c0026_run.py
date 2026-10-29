"""Observe, tear down, and seal one retained C0026 QEMU run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path


PROBE_NAME = "probe_c0026_target.py"


def run_context(run_root: Path) -> dict:
    context = json.loads((run_root / "run_context.json").read_text(encoding="utf-8"))
    if context["campaign_id"] != "0.c0026" or not context["keep_lab_requested"]:
        raise ValueError("Completion requires a retained C0026 lab run")
    return context


def observe_target(run_root: Path) -> None:
    workspace = run_root / "workspace"
    target_directory = workspace / "lab" / "vagrant" / "target-linux-1"
    source_probe = workspace / "scripts" / PROBE_NAME
    evidence = run_root / "evidence"
    observation_path = evidence / "c0026-target-observation.json"
    transport_path = evidence / "c0026-target-observation.transport.json"
    if observation_path.exists() or transport_path.exists():
        raise FileExistsError("C0026 observation receipts cannot be overwritten")
    if not source_probe.is_file() or not target_directory.is_dir():
        raise FileNotFoundError("Packaged C0026 probe or target VM is missing")

    probe_bytes = source_probe.read_bytes()
    probe_sha256 = hashlib.sha256(probe_bytes).hexdigest()
    result = subprocess.run(
        ["vagrant", "ssh", "-c", "sudo -n python3 -"],
        cwd=target_directory,
        input=probe_bytes.decode("utf-8"),
        check=False,
        capture_output=True,
        text=True,
        timeout=90,
        env=dict(os.environ, VAGRANT_DEFAULT_PROVIDER="qemu"),
    )
    with transport_path.open("x", encoding="utf-8") as output:
        json.dump({
            "exit_code": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "probe_sha256": probe_sha256,
        }, output, indent=2, sort_keys=True)
        output.write("\n")
    if result.returncode:
        raise RuntimeError(f"C0026 target observation failed; inspect {transport_path}")
    observation = json.loads(result.stdout)
    if observation.get("schema") != "c0026-target-chain-observation/v1":
        raise ValueError("Guest returned an unexpected observation schema")
    context = run_context(run_root)
    with observation_path.open("x", encoding="utf-8") as output:
        json.dump({
            "schema": "c0026-target-observer-receipt/v1",
            "campaign_id": context["campaign_id"],
            "source_tree_sha256": context["source_tree_sha256"],
            "probe_sha256": probe_sha256,
            "observation": observation,
        }, output, indent=2, sort_keys=True)
        output.write("\n")


def destroy_lab(run_root: Path) -> None:
    workspace = run_root / "workspace"
    subprocess.run(
        ["bash", str(workspace / "scripts" / "destroy_lab.sh"), "--campaign", "0.c0026"],
        cwd=workspace,
        check=True,
    )


def complete_run(run_root: Path) -> None:
    context = run_context(run_root)
    errors: list[BaseException] = []
    if context["exit_code"] != 0:
        errors.append(ValueError("Campaign failed; inspect its retained evidence"))
    else:
        try:
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

    workspace = run_root / "workspace"
    finalizer = workspace / "scripts" / "finalize_isolated_lab_run.py"
    subprocess.run(
        [sys.executable, str(finalizer), "--run-root", str(run_root)],
        cwd=workspace,
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    complete_run(args.run_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
