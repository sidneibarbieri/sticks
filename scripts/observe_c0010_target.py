"""Record one read-only C0010 observation from a retained target guest."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from pydantic import BaseModel


ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
PROBE = ARTIFACT_ROOT / "scripts/probe_c0010_target.py"


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
    if context.campaign_id != "0.c0010" or context.exit_code or not context.keep_lab_requested:
        raise ValueError("Expected a completed C0010 run with its target lab retained")

    output = run_root / "evidence/c0010-target-observation.json"
    transport = run_root / "evidence/c0010-target-observation.transport.json"
    if output.exists() or transport.exists():
        raise FileExistsError("C0010 observation receipts cannot be overwritten")
    probe_bytes = PROBE.read_bytes()
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
    with transport.open("x", encoding="utf-8") as stream:
        json.dump(
            {"exit_code": completed.returncode, "stdout": completed.stdout,
             "stderr": completed.stderr, "probe_sha256": hashlib.sha256(probe_bytes).hexdigest()},
            stream,
            indent=2,
            sort_keys=True,
        )
        stream.write("\n")
    if completed.returncode:
        raise RuntimeError(f"Target observation failed; inspect {transport}")
    observation = json.loads(completed.stdout)
    if observation.get("schema") != "c0010-target-transfer-observation/v1":
        raise ValueError("Unexpected C0010 observation schema")
    receipt = {
        "schema": "c0010-target-observer-receipt/v1",
        "campaign_id": context.campaign_id,
        "source_tree_sha256": context.source_tree_sha256,
        "probe_sha256": hashlib.sha256(probe_bytes).hexdigest(),
        "observation": observation,
    }
    with output.open("x", encoding="utf-8") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"passed": observation["passed"], "checks": observation["checks"]}))
    return int(not observation["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
