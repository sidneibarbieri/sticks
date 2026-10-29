"""Observe fixtures and two controlled effects in a retained Linux QEMU guest."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

import yaml

ARTIFACT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ARTIFACT_ROOT / "src"))

from validators.controlled_target_observer import (  # noqa: E402
    FixtureDeclaration, TargetObservation, declaration_by_path, validate_observation,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace_file(workspace: Path, path: Path) -> Path:
    resolved = (workspace / path).resolve()
    if not resolved.is_relative_to(workspace):
        raise ValueError("Input must belong to the retained workspace")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--sut-host", default="target-base")
    parser.add_argument("--target-directory", type=Path, default=Path("lab/vagrant/target-linux-1"))
    parser.add_argument("--browser-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve(strict=True)
    profile = workspace_file(workspace, Path("data/sut_profiles") / f"{args.campaign}.yml")
    browser_path = workspace_file(workspace, args.browser_report)
    target_directory = workspace_file(workspace, args.target_directory)
    probe_path = ARTIFACT_ROOT / "scripts/probe_controlled_target.py"
    input_paths = {
        "profile_sha256": profile,
        "browser_report_sha256": browser_path,
        "probe_sha256": probe_path,
        "validator_sha256": ARTIFACT_ROOT / "src/validators/controlled_target_observer.py",
        "cli_sha256": Path(__file__),
    }
    input_bytes = {name: path.read_bytes() for name, path in input_paths.items()}
    input_hashes = {
        name: hashlib.sha256(content).hexdigest() for name, content in input_bytes.items()
    }
    profile_data = yaml.safe_load(input_bytes["profile_sha256"])
    fixtures = [FixtureDeclaration.model_validate(fixture) for fixture in
                profile_data["sut_configuration"][args.sut_host]["files"]]
    declaration_by_path(fixtures)
    declaration = [{"path": fixture.path, "owner": fixture.owner} for fixture in fixtures]
    command = "sudo -n python3 -c " + shlex.quote(input_bytes["probe_sha256"].decode("utf-8"))
    command += " " + shlex.quote(json.dumps(declaration))
    transport_path = args.output.with_suffix(args.output.suffix + ".transport.json")
    if args.output.exists() or transport_path.exists():
        raise FileExistsError("Observer receipts cannot overwrite an earlier observation")
    result = subprocess.run(
        ["vagrant", "ssh", "-c", command], cwd=target_directory,
        env=dict(os.environ, VAGRANT_DEFAULT_PROVIDER="qemu"),
        capture_output=True, text=True, timeout=60, check=False,
    )
    changed_inputs = [
        name for name, path in input_paths.items()
        if not path.is_file() or sha256(path) != input_hashes[name]
    ]
    receipt = {
        "transport_exit_code": result.returncode, "stdout": result.stdout,
        "stderr": result.stderr, **input_hashes, "changed_inputs": changed_inputs,
    }
    with transport_path.open("x") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    if result.returncode:
        raise RuntimeError(f"Guest observation failed; inspect {transport_path}")
    if changed_inputs:
        raise RuntimeError(f"Observer inputs changed; inspect {transport_path}")
    observation = TargetObservation.model_validate_json(result.stdout)
    errors = validate_observation(
        fixtures, observation, input_bytes["browser_report_sha256"].decode("utf-8")
    )
    receipt.pop("stdout")
    receipt.update(observation=observation.model_dump(), errors=errors, passed=not errors)
    with args.output.open("x") as stream:
        stream.write(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"files_observed": len(observation.files), "errors": errors}))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
