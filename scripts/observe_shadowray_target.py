"""Record a read-only ShadowRay fixture observation from the retained guest."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

from pydantic import BaseModel


class RunContext(BaseModel):
    campaign_id: str
    exit_code: int
    keep_lab_requested: bool
    source_tree_sha256: str


EXPECTED_CHECKS = frozenset({
    "transfer_matches_source", "http_get_recorded",
    "backup_matches_fixture", "toolkit_files_executable",
})
EXPECTED_SCOPE = (
    "Retained fixtures only; no proof of escalation, historical fidelity, "
    "executor identity, shell-startup behavior, or cross-host ingress."
)


def write_json_once(path: Path, payload: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    args = parser.parse_args()
    run_root = args.run_root.resolve(strict=True)
    context = RunContext.model_validate_json(
        (run_root / "run_context.json").read_text(encoding="utf-8")
    )
    if context.campaign_id != "0.shadowray" or context.exit_code or not context.keep_lab_requested:
        raise ValueError("Expected a completed ShadowRay run with its target lab retained")

    evidence = run_root / "evidence"
    receipt_path = evidence / "shadowray-target-observation.json"
    transport_path = evidence / "shadowray-target-observation.transport.json"
    if receipt_path.exists() or transport_path.exists():
        raise FileExistsError("ShadowRay observation receipts cannot be overwritten")
    probe = run_root / "workspace/scripts/probe_shadowray_target.py"
    probe_bytes = probe.read_bytes()
    probe_sha256 = hashlib.sha256(probe_bytes).hexdigest()
    target = run_root / "workspace/lab/vagrant/target-linux-1"
    completed = subprocess.run(
        ["vagrant", "ssh", "-c", "sudo -n python3 -"],
        cwd=target,
        input=probe_bytes.decode("utf-8"),
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
        env=dict(os.environ, VAGRANT_DEFAULT_PROVIDER="qemu"),
    )
    write_json_once(transport_path, {
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "probe_sha256": probe_sha256,
    })
    if completed.returncode:
        raise RuntimeError(f"ShadowRay target observation exited {completed.returncode}; inspect {transport_path}")
    observation = json.loads(completed.stdout)
    if (
        observation.get("schema") != "shadowray-fixture-observation/v1"
        or set(observation.get("checks", {})) != EXPECTED_CHECKS
        or observation.get("scope") != EXPECTED_SCOPE
    ):
        raise ValueError("Unexpected ShadowRay observation contract")
    write_json_once(receipt_path, {
        "schema": "shadowray-target-observer-receipt/v1",
        "campaign_id": context.campaign_id,
        "source_tree_sha256": context.source_tree_sha256,
        "probe_sha256": probe_sha256,
        "observation": observation,
    })
    print(json.dumps({"passed": observation["passed"], "checks": observation["checks"]}))
    return int(not observation["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
