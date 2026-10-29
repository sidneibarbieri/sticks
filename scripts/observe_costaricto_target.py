"""Record the bounded CostaRicto observation from a retained target guest."""

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from pydantic import BaseModel


class RunContext(BaseModel):
    campaign_id: str
    exit_code: int
    keep_lab_requested: bool
    source_tree_sha256: str


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    run_root = args.run_root.resolve(strict=True)
    context = RunContext.model_validate_json((run_root / "run_context.json").read_text())
    if context.campaign_id != "0.costaricto" or context.exit_code or not context.keep_lab_requested:
        raise ValueError("Expected a completed CostaRicto run with its target lab retained")

    evidence = run_root / "evidence"
    receipt_path = evidence / "costaricto-target-observation.json"
    transport_path = evidence / "costaricto-target-observation.transport.json"
    if receipt_path.exists() or transport_path.exists():
        raise FileExistsError("CostaRicto observation receipts cannot be overwritten")

    probe_path = run_root / "workspace/scripts/probe_costaricto_target.py"
    probe_bytes = probe_path.read_bytes()
    probe_sha256 = hashlib.sha256(probe_bytes).hexdigest()
    target_directory = run_root / "workspace/lab/vagrant/target-linux-1"
    completed = subprocess.run(
        ["vagrant", "ssh", "-c", "sudo -n python3 -"],
        cwd=target_directory,
        input=probe_bytes.decode("utf-8"),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=dict(os.environ, VAGRANT_DEFAULT_PROVIDER="qemu"),
    )
    with transport_path.open("x", encoding="utf-8") as stream:
        json.dump({
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "probe_sha256": probe_sha256,
        }, stream, indent=2, sort_keys=True)
        stream.write("\n")
    if completed.returncode:
        raise RuntimeError(f"Target observation failed; inspect {transport_path}")

    observation = json.loads(completed.stdout)
    if observation.get("schema") != "costaricto-bounded-guest-observation/v1":
        raise ValueError("Unexpected CostaRicto observation schema")
    with receipt_path.open("x", encoding="utf-8") as stream:
        json.dump({
            "schema": "costaricto-target-observer-receipt/v1",
            "campaign_id": context.campaign_id,
            "source_tree_sha256": context.source_tree_sha256,
            "probe_sha256": probe_sha256,
            "observation": observation,
        }, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"passed": observation["passed"], "checks": observation["checks"]}))
    return int(not observation["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
