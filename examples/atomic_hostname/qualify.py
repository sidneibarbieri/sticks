"""Qualify one pinned external discovery command with independent negative controls."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import yaml
from pydantic import BaseModel, ConfigDict

ARTIFACT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ARTIFACT_ROOT / "src"))

from concretization.models import ActionTemplate, BindingCatalog, BindingValue, ConcretizedPlan
from concretization.pipeline import concretize_plan
from contracts.procedural_ir import ProcedureStep, ProceduralPlan, SourceSnapshot

COMMAND_TIMEOUT_SECONDS = 20
CONTAINER_LIFETIME_SECONDS = 120


class CellResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    cell: str
    container_id: str
    image_id: str
    contract_sha256: str
    executed_command: str
    command_matches_source: bool
    returncode: int
    stdout: str
    stderr: str
    observed_hostname: str
    predicate_passed: bool
    expected_predicate: bool
    teardown_verified: bool


def docker(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", *arguments], check=check, capture_output=True, text=True,
        timeout=COMMAND_TIMEOUT_SECONDS,
    )


@contextmanager
def isolated_target(image: str, hostname: str):
    name = "sticks-art-hostname-" + uuid4().hex[:12]
    container = docker(
        "create", "--pull=never", "--network=none", "--read-only", "--cap-drop=ALL",
        "--security-opt=no-new-privileges", "--user=65534:65534", "--pids-limit=16",
        "--memory=64m", "--cpus=0.5", "--hostname", hostname, "--name", name,
        image, "sleep", str(CONTAINER_LIFETIME_SECONDS),
    ).stdout.strip()
    try:
        docker("start", container)
        yield container
    finally:
        docker("rm", "--force", container)
        remaining = docker("ps", "--all", "--quiet", "--filter", "id=" + container)
        if remaining.stdout.strip():
            raise RuntimeError("External-procedure target survived teardown")


def load_source() -> dict:
    manifest = json.loads((EXAMPLE_ROOT / "manifest.json").read_text())
    for filename, digest_key in (("T1082.yaml", "sha256"), ("LICENSE.upstream.txt", "license_sha256")):
        if hashlib.sha256((EXAMPLE_ROOT / filename).read_bytes()).hexdigest() != manifest[digest_key]:
            raise ValueError("Pinned external source or license changed")
    upstream = yaml.safe_load((EXAMPLE_ROOT / "T1082.yaml").read_text())
    selected = [atomic for atomic in upstream["atomic_tests"]
                if atomic["auto_generated_guid"] == manifest["atomic_guid"]]
    if (upstream["attack_technique"] != "T1082" or len(selected) != 1
            or "linux" not in selected[0]["supported_platforms"]
            or selected[0]["executor"]["name"] != "sh"
            or selected[0]["executor"]["command"] != "hostname\n"
            or manifest["command"] != "hostname\n"):
        raise ValueError("External procedure differs from the qualified read-only command")
    return manifest


def admitted_contract(container: str, source_digest: str) -> tuple[ActionTemplate, ProceduralPlan, BindingCatalog, ConcretizedPlan]:
    template = ActionTemplate(
        template_id="art-hostname-discovery", technique_ids=["T1082"],
        execution_domain="target", parameter_kinds={"target": "target_host"},
        requires=["lab.shell.ready"], produces=["discovery.target_hostname"],
        evidence_predicates=["hostname_matches_independent_target_identity"],
        fidelity_ceiling="adapted",
        description="Run the unchanged external hostname command on the bound Linux target.",
    )
    plan = ProceduralPlan(
        campaign_id="external-atomic-qualification", campaign_name="External procedure qualification",
        source=SourceSnapshot(
            bundle_sha256=source_digest, object_count=1,
            campaign_stix_id="atomic-red-team:486e88ea-4f56-470f-9b57-3f4d73f39133",
            campaign_external_id="external-atomic-qualification",
        ),
        steps=[ProcedureStep(
            technique_id="T1082", technique_stix_id="atomic-red-team:T1082",
            name="Hostname Discovery", execution_domain="target", platforms=["Linux"],
            relationship_ids=["external-atomic-selection"],
        )],
    )
    catalog = BindingCatalog(
        sut_id="isolated-linux-container", source_sha256=source_digest,
        initial_facts=["lab.shell.ready"], goal_facts=["discovery.target_hostname"],
        bindings=[BindingValue(binding_id="target.primary", kind="target_host",
                               value="lab://" + container, source="sut")],
    )
    plan.finalize_hash()
    catalog.finalize_hash()
    concretized = concretize_plan(plan, catalog, [template])
    if len(concretized.steps) != 1 or concretized.unresolved_technique_ids:
        raise ValueError("External procedure was not admitted")
    return template, plan, catalog, concretized


def selected_command(cell: str, manifest: dict) -> tuple[str, bool]:
    commands = {
        "upstream_command": (manifest["command"], True),
        "wrong_hostname_exit_zero": ("printf 'wrong-hostname\\n'", False),
        "empty_output_exit_zero": ("true", False),
    }
    return commands[cell]


def qualify_cell(cell: str, manifest: dict, output: Path) -> CellResult:
    command, expected = selected_command(cell, manifest)
    directory = output / cell
    directory.mkdir()
    with isolated_target(manifest["image"], manifest["expected_hostname"]) as container:
        configuration = json.loads(docker("inspect", container).stdout)[0]
        host = configuration["HostConfig"]
        if (host["NetworkMode"] != "none" or not host["ReadonlyRootfs"]
                or host["CapDrop"] != ["ALL"]
                or "no-new-privileges" not in host["SecurityOpt"]
                or configuration["Config"]["User"] != "65534:65534"):
            raise ValueError("Target does not satisfy its isolation contract")
        observed = docker("exec", container, "cat", "/etc/hostname").stdout.strip()
        if observed != manifest["expected_hostname"] or configuration["Config"]["Hostname"] != observed:
            raise ValueError("Independent target identities disagree")
        template, plan, catalog, concretized = admitted_contract(container, manifest["sha256"])
        for name, record in (("template", template), ("source-plan", plan),
                             ("binding-catalog", catalog), ("admitted-plan", concretized)):
            (directory / (name + ".json")).write_text(record.model_dump_json(indent=2) + "\n")
        executed = docker("exec", container, "sh", "-c", command, check=False)
        passed = executed.returncode == 0 and executed.stdout.strip() == observed
        result = CellResult(
            cell=cell, container_id=container, image_id=configuration["Image"],
            contract_sha256=concretized.content_sha256, returncode=executed.returncode,
            executed_command=command, command_matches_source=command == manifest["command"],
            stdout=executed.stdout, stderr=executed.stderr, observed_hostname=observed,
            predicate_passed=passed, expected_predicate=expected, teardown_verified=False,
        )
        (directory / "observation-before-teardown.json").write_text(result.model_dump_json(indent=2) + "\n")
    result = result.model_copy(update={"teardown_verified": True})
    (directory / "result.json").write_text(result.model_dump_json(indent=2) + "\n")
    if passed != expected or executed.returncode != 0:
        raise ValueError(f"External-procedure qualification failed for {cell}")
    return result


def verify_qualification(output: Path, manifest: dict) -> None:
    """Recompute admission and the output predicate; retained cleanup is not a live probe."""
    receipt = json.loads((output / "qualification.json").read_text())
    if (receipt["schema_version"] != "external-atomic-qualification/v1"
            or receipt["claim_ceiling"] != manifest["claim_ceiling"]
            or receipt["source"] != manifest
            or receipt["qualification_source_sha256"] != hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            or receipt["manifest_sha256"] != hashlib.sha256((EXAMPLE_ROOT / "manifest.json").read_bytes()).hexdigest()):
        raise ValueError("Qualification source differs from the retained receipt")
    records = [CellResult.model_validate(item) for item in receipt["cells"]]
    if [record.cell for record in records] != manifest["cells"]:
        raise ValueError("Qualification omits or reorders a selected cell")
    if len({record.container_id for record in records}) != len(records):
        raise ValueError("Qualification reused a target across selected cells")
    for record in records:
        template, plan, catalog, admitted = admitted_contract(record.container_id, manifest["sha256"])
        directory = output / record.cell
        for name, expected in (("template", template), ("source-plan", plan),
                               ("binding-catalog", catalog), ("admitted-plan", admitted)):
            if json.loads((directory / (name + ".json")).read_text()) != expected.model_dump(mode="json"):
                raise ValueError("Retained external contract or admission differs from replay")
        expected_command, expected_predicate = selected_command(record.cell, manifest)
        observed_predicate = record.returncode == 0 and record.stdout.strip() == manifest["expected_hostname"]
        if (record.contract_sha256 != admitted.content_sha256
                or record.observed_hostname != manifest["expected_hostname"]
                or record.image_id != "sha256:" + manifest["image"].split("@sha256:")[1]
                or record.returncode != 0 or not record.teardown_verified
                or record.expected_predicate != expected_predicate
                or record.executed_command != expected_command
                or record.predicate_passed != observed_predicate
                or observed_predicate != expected_predicate
                or record.command_matches_source != (record.executed_command == manifest["command"])
                or record.command_matches_source != expected_predicate):
            raise ValueError("Retained external observation differs from qualification expectations")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    options = parser.parse_args()
    manifest = load_source()
    if options.verify_only:
        verify_qualification(options.output_dir, manifest)
        print("External admission and observation replay: PASS (offline)")
        return
    options.output_dir.mkdir(parents=True, exist_ok=False)
    results = [qualify_cell(cell, manifest, options.output_dir) for cell in manifest["cells"]]
    receipt = {"schema_version": "external-atomic-qualification/v1", "source": manifest,
               "qualification_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "manifest_sha256": hashlib.sha256((EXAMPLE_ROOT / "manifest.json").read_bytes()).hexdigest(),
               "cells": [result.model_dump() for result in results],
               "claim_ceiling": manifest["claim_ceiling"]}
    (options.output_dir / "qualification.json").write_text(json.dumps(receipt, indent=2) + "\n")
    verify_qualification(options.output_dir, manifest)
    print(json.dumps({"cells": len(results), "expectations_matched": True, "teardown_verified": True}))


if __name__ == "__main__":
    main()
