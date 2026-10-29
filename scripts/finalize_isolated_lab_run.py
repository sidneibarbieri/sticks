"""Seal one isolated VM run after independent observation and lab teardown."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

if __package__:
    from scripts.run_isolated_lab_campaign import sha256_file, tree_manifest, write_json
else:
    from run_isolated_lab_campaign import sha256_file, tree_manifest, write_json


VM_ALIASES = {
    "target-base": "target-linux-1",
    "target-1": "target-linux-1",
    "target": "target-linux-1",
    "target-2": "target-linux-2",
}
FINAL_RECEIPT = "final_run_receipt.json"
C0010_CHECKS = frozenset(
    {
        "declared_notice_present",
        "declared_page_present",
        "download_executable",
        "http_get_recorded",
        "transfer_matches_source",
    }
)
OBSERVATION_FILES = {
    "0.c0010": frozenset(
        {
            "c0010-target-observation.json",
            "c0010-target-observation.transport.json",
        }
    ),
    "0.c0026": frozenset(
        {
            "c0026-target-observation.json",
            "c0026-target-observation.transport.json",
        }
    ),
    "0.costaricto": frozenset(
        {
            "costaricto-target-observation.json",
            "costaricto-target-observation.transport.json",
        }
    ),
    "0.shadowray": frozenset(
        {
            "shadowray-target-observation.json",
            "shadowray-target-observation.transport.json",
        }
    ),
    "0.outer_space": frozenset(
        {
            "outer-space-target-observation.json",
            "outer-space-target-observation.json.transport.json",
        }
    ),
}
SHADOWRAY_CHECKS = frozenset(
    {
        "transfer_matches_source",
        "http_get_recorded",
        "backup_matches_fixture",
        "toolkit_files_executable",
    }
)
SHADOWRAY_SCOPE = (
    "Retained fixtures only; no proof of escalation, historical fidelity, "
    "executor identity, shell-startup behavior, or cross-host ingress."
)
COSTARICTO_CHECKS = frozenset(
    {
        "declared_target_hostname",
        "declared_ssh_service_listening",
        "collection_source_declared",
        "collection_copy_matches_source",
        "collection_destination_owner_mode",
        "tool_source_declared",
        "tool_copy_matches_source",
        "tool_destination_owner_mode",
        "known_benign_payload_present",
    }
)
COSTARICTO_SCOPE = (
    "Declared synthetic guest files, copies, benign payload, and listening SSH; "
    "not external tool acquisition or complete historical campaign effects."
)
COSTARICTO_PAYLOAD_SHA256 = (
    "b088ddaef2625e7f19f1ef1031b8af0617d4e849134d367bde139c77b7ad7be9"
)
OUTER_SPACE_SCOPE = (
    "Declared guest fixtures, browser identity, and benign loopback transfer; "
    "six other steps are simulations, not observed target effects or historical fidelity."
)


class RunContext(BaseModel):
    """Fields needed to bind the initial run to its final evidence."""

    campaign_id: str
    exit_code: int
    keep_lab_requested: bool
    source_tree_sha256: str
    evidence_tree_sha256: str
    artifact_tree_sha256: str | None
    execution_log_path: str | None = None
    execution_log_sha256: str | None = None


class TargetObservation(BaseModel):
    """Independent observation recorded inside the target guest."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    hostname: str
    boot_id: str
    checks: dict[str, bool]
    passed: bool


class C0010ObserverReceipt(BaseModel):
    """C0010 guest observation bound to the run source and probe."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    campaign_id: str
    source_tree_sha256: str
    probe_sha256: str
    observation: TargetObservation


class C0026Observation(TargetObservation):
    """Measured guest chain and its bounded input digests."""

    observer_uid: int
    collection_sha256: str
    archive_sha256: str
    chunk_count: int
    scope: str


class C0026ObserverReceipt(BaseModel):
    """C0026 guest observation bound to source and guest transport."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    campaign_id: str
    source_tree_sha256: str
    probe_sha256: str
    observation: C0026Observation


class ShadowRayObservation(TargetObservation):
    """Bounded guest fixture observation; it does not certify campaign effects."""

    observer_uid: int
    files: dict[str, dict]
    http_log: dict
    scope: str


class ShadowRayObserverReceipt(BaseModel):
    """ShadowRay guest observation bound to its run and transport."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    campaign_id: str
    source_tree_sha256: str
    probe_sha256: str
    observation: ShadowRayObservation


class CostaRictoObservation(TargetObservation):
    """Bounded guest-file and service observation."""

    observer_uid: int
    file_sha256: dict[str, str]
    scope: str


class CostaRictoObserverReceipt(BaseModel):
    """CostaRicto observation bound to its source probe and guest transport."""

    model_config = ConfigDict(populate_by_name=True)

    schema_name: str = Field(alias="schema")
    campaign_id: str
    source_tree_sha256: str
    probe_sha256: str
    observation: CostaRictoObservation


class ProbeTransport(BaseModel):
    """The persisted transport result from the guest probe."""

    exit_code: int
    stdout: str
    stderr: str
    probe_sha256: str


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def unique_manifest_digest(manifest: dict, path: str) -> str:
    matches = [entry["sha256"] for entry in manifest["files"] if entry["path"] == path]
    if len(matches) != 1:
        raise ValueError(f"Observer input is not unique in its manifest: {path}")
    return matches[0]


def validate_outer_space_observation(
    run_root: Path,
    context: RunContext,
    source_manifest: dict,
) -> tuple[TargetObservation, dict]:
    """Bind the generic fixture observer to this run's source and raw transport."""
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from validators.controlled_target_observer import (
        FixtureDeclaration,
    )
    from validators.controlled_target_observer import (
        TargetObservation as FixtureObservation,
    )
    from validators.controlled_target_observer import (
        validate_observation as validate_fixtures,
    )

    workspace = run_root / "workspace"
    evidence = run_root / "evidence"
    receipt = read_json(evidence / "outer-space-target-observation.json")
    transport = read_json(
        evidence / "outer-space-target-observation.json.transport.json"
    )
    profile_path = "data/sut_profiles/0.outer_space.yml"
    browser_path = "data/artifacts/0.outer_space_browser_discovery.txt"
    source_paths = {
        "profile_sha256": profile_path,
        "probe_sha256": "scripts/probe_controlled_target.py",
        "validator_sha256": "src/validators/controlled_target_observer.py",
        "cli_sha256": "scripts/observe_controlled_target.py",
    }
    hashes = {}
    for field, path in source_paths.items():
        expected = unique_manifest_digest(source_manifest, path)
        actual = sha256_file(workspace / path)
        if actual != expected:
            raise ValueError(f"Outer Space observer source changed: {path}")
        hashes[field] = actual
    browser_report = workspace / browser_path
    browser_digest = unique_manifest_digest(
        read_json(run_root / "artifact_manifest.json"),
        browser_path.removeprefix("data/artifacts/"),
    )
    if sha256_file(browser_report) != browser_digest:
        raise ValueError("Outer Space browser report changed after runner capture")
    hashes["browser_report_sha256"] = browser_digest
    if (
        any(
            receipt.get(field) != digest or transport.get(field) != digest
            for field, digest in hashes.items()
        )
        or receipt.get("changed_inputs") != []
        or transport.get("changed_inputs") != []
        or transport.get("transport_exit_code") != 0
        or receipt.get("errors") != []
        or receipt.get("passed") is not True
    ):
        raise ValueError("Outer Space observer inputs or transport did not pass")
    measured = FixtureObservation.model_validate_json(transport["stdout"])
    if measured.model_dump() != receipt.get("observation"):
        raise ValueError("Outer Space observation differs from raw guest stdout")
    profile = yaml.safe_load((workspace / profile_path).read_text(encoding="utf-8"))
    fixtures = [
        FixtureDeclaration.model_validate(item)
        for item in profile["sut_configuration"]["target-base"]["files"]
    ]
    errors = validate_fixtures(
        fixtures, measured, browser_report.read_text(encoding="utf-8")
    )
    if errors or measured.hostname != "target-linux-1":
        raise ValueError(f"Outer Space guest fixture observation failed: {errors}")
    observation = TargetObservation.model_validate(
        {
            "schema": "outer-space-bounded-guest-observation/v1",
            "hostname": measured.hostname,
            "boot_id": measured.boot_id,
            "checks": {
                "browser_and_fixture_consistent": True,
                "loopback_transfer_consistent": True,
            },
            "passed": True,
        }
    )
    return observation, {
        "observer_transport_path": "evidence/outer-space-target-observation.json.transport.json",
        "observer_transport_sha256": sha256_file(
            evidence / "outer-space-target-observation.json.transport.json"
        ),
        "probe_sha256": hashes["probe_sha256"],
    }


def validate_outer_space_summary(summary: dict) -> None:
    """Keep the two guest effects separate from six controller simulations."""
    controlled_executors = {
        "T1105": "executors.executor_registry.execute_t1105_real",
        "T1217": "executors.executor_registry.execute_t1217_real",
    }
    controlled = set(controlled_executors)
    simulated = {
        "T1584.004",
        "T1071.001",
        "T1585.003",
        "T1027.013",
        "T1587.001",
        "T1059.005",
    }
    results = summary.get("technique_results", [])
    if summary["total_techniques"] != 8 or len(results) != 8:
        raise ValueError("Outer Space runner classification is incomplete")
    by_technique = {result.get("technique_id"): result for result in results}
    if len(by_technique) != 8 or set(by_technique) != controlled | simulated:
        raise ValueError(
            "Outer Space runner classification differs from the declared inventory"
        )
    for technique_id, result in by_technique.items():
        expected_mode = (
            "real_controlled" if technique_id in controlled else "naive_simulated"
        )
        expected_host = "target-linux-1" if technique_id in controlled else "localhost"
        if (
            result.get("status") != "success"
            or result.get("execution_mode") != expected_mode
            or result.get("host") not in ("", expected_host)
            or not result.get("executor_name")
            or (
                technique_id in controlled
                and result["executor_name"] != controlled_executors[technique_id]
            )
        ):
            raise ValueError(
                f"Outer Space runner classification mismatch: {technique_id}"
            )


def required_vms(workspace: Path, campaign_id: str) -> list[str]:
    profile_path = workspace / "data" / "sut_profiles" / f"{campaign_id}.yml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    declared = profile["requirements"]["required_vms"]
    if not isinstance(declared, list) or not declared:
        raise ValueError("SUT profile must declare at least one required VM")
    vm_names = list(dict.fromkeys(VM_ALIASES.get(name, name) for name in declared))
    if any(
        not (workspace / "lab" / "vagrant" / name / "Vagrantfile").is_file()
        for name in vm_names
    ):
        raise ValueError("SUT profile refers to a VM without a Vagrantfile")
    return vm_names


def read_vm_state(vm_directory: Path) -> str:
    completed = subprocess.run(
        ["vagrant", "status", "--machine-readable"],
        cwd=vm_directory,
        capture_output=True,
        text=True,
        check=True,
    )
    states = [
        line.split(",", 3)[3]
        for line in completed.stdout.splitlines()
        if len(line.split(",", 3)) == 4 and line.split(",", 3)[2] == "state"
    ]
    if len(states) != 1:
        raise ValueError(f"Expected one Vagrant state in {vm_directory}")
    return states[0]


def receipt_vm_states(
    workspace: Path,
    campaign_id: str,
    recorded_states: dict[str, str] | None = None,
) -> dict[str, str]:
    vm_names = required_vms(workspace, campaign_id)
    if recorded_states is None:
        return {
            name: read_vm_state(workspace / "lab" / "vagrant" / name)
            for name in vm_names
        }
    if (
        not isinstance(recorded_states, dict)
        or set(recorded_states) != set(vm_names)
        or any(state != "not_created" for state in recorded_states.values())
    ):
        raise ValueError("Recorded VM states do not match the required teardown")
    return {name: recorded_states[name] for name in vm_names}


def unchanged_initial_evidence(
    run_root: Path, current_manifest: dict, expected_new_files: frozenset[str]
) -> None:
    initial_manifest = read_json(run_root / "evidence_manifest.json")
    initial_files = {file["path"]: file["sha256"] for file in initial_manifest["files"]}
    current_files = {file["path"]: file["sha256"] for file in current_manifest["files"]}
    if any(current_files.get(path) != digest for path, digest in initial_files.items()):
        raise ValueError(
            "Initial runner evidence changed after its manifest was written"
        )
    if set(current_files) - set(initial_files) != expected_new_files:
        raise ValueError("Unexpected independent observation files")


def validate_c0010_observation(
    run_root: Path, context: RunContext, source_manifest: dict
) -> tuple[TargetObservation, dict]:
    """Check the C0010 receipt against guest transport and the sealed probe."""
    evidence = run_root / "evidence"
    observation_path = evidence / "c0010-target-observation.json"
    transport_path = evidence / "c0010-target-observation.transport.json"
    receipt = C0010ObserverReceipt.model_validate(read_json(observation_path))
    transport = ProbeTransport.model_validate(read_json(transport_path))
    observation = receipt.observation
    probe_path = "scripts/probe_c0010_target.py"
    source_entries = [
        entry for entry in source_manifest["files"] if entry["path"] == probe_path
    ]
    if len(source_entries) != 1:
        raise ValueError("C0010 probe is not uniquely bound in the source manifest")
    probe_sha256 = sha256_file(run_root / "workspace" / probe_path)
    if (
        receipt.schema_name != "c0010-target-observer-receipt/v1"
        or receipt.campaign_id != context.campaign_id
        or receipt.source_tree_sha256 != context.source_tree_sha256
        or probe_sha256 != source_entries[0]["sha256"]
        or receipt.probe_sha256 != probe_sha256
        or transport.probe_sha256 != probe_sha256
        or transport.exit_code != 0
        or TargetObservation.model_validate_json(transport.stdout) != observation
    ):
        raise ValueError(
            "C0010 observation is not bound to the run and guest transport"
        )
    if set(observation.checks) != C0010_CHECKS:
        raise ValueError("C0010 independent observation has missing or extra checks")
    return observation, {
        "observer_transport_path": transport_path.relative_to(run_root).as_posix(),
        "observer_transport_sha256": sha256_file(transport_path),
        "probe_sha256": probe_sha256,
    }


def validate_c0026_observation(
    run_root: Path,
    context: RunContext,
    source_manifest: dict,
) -> tuple[C0026Observation, dict]:
    """Bind the C0026 guest-chain receipt to its probe and SSH transport."""
    evidence = run_root / "evidence"
    transport_path = evidence / "c0026-target-observation.transport.json"
    receipt = C0026ObserverReceipt.model_validate(
        read_json(evidence / "c0026-target-observation.json")
    )
    transport = ProbeTransport.model_validate(read_json(transport_path))
    probe_sha256 = source_file_digest(
        run_root, source_manifest, "scripts/probe_c0026_target.py"
    )
    observation = receipt.observation
    if (
        receipt.schema_name != "c0026-target-observer-receipt/v1"
        or receipt.campaign_id != context.campaign_id
        or receipt.source_tree_sha256 != context.source_tree_sha256
        or receipt.probe_sha256 != probe_sha256
        or transport.probe_sha256 != probe_sha256
        or transport.exit_code != 0
        or C0026Observation.model_validate_json(transport.stdout) != observation
        or observation.observer_uid != 0
        or observation.chunk_count < 2
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in (observation.collection_sha256, observation.archive_sha256)
        )
    ):
        raise ValueError(
            "C0026 observation is not bound to the run and guest transport"
        )
    return observation, {
        "observer_transport_path": transport_path.relative_to(run_root).as_posix(),
        "observer_transport_sha256": sha256_file(transport_path),
        "probe_sha256": probe_sha256,
    }


def source_file_digest(run_root: Path, source_manifest: dict, relative: str) -> str:
    """Require one source-manifest entry matching the retained source file."""
    entries = [entry for entry in source_manifest["files"] if entry["path"] == relative]
    if len(entries) != 1:
        raise ValueError(f"Source file is not uniquely bound: {relative}")
    digest = sha256_file(run_root / "workspace" / relative)
    if digest != entries[0]["sha256"]:
        raise ValueError(f"Source file is not bound to the run: {relative}")
    return digest


def validate_shadowray_observation(
    run_root: Path, context: RunContext, source_manifest: dict
) -> tuple[ShadowRayObservation, dict]:
    """Bind the fixture probe, guest transport, and observation to one source."""
    evidence = run_root / "evidence"
    receipt_path = evidence / "shadowray-target-observation.json"
    transport_path = evidence / "shadowray-target-observation.transport.json"
    receipt = ShadowRayObserverReceipt.model_validate(read_json(receipt_path))
    transport = ProbeTransport.model_validate(read_json(transport_path))
    probe_sha256 = source_file_digest(
        run_root, source_manifest, "scripts/probe_shadowray_target.py"
    )
    if (
        receipt.schema_name != "shadowray-target-observer-receipt/v1"
        or receipt.campaign_id != context.campaign_id
        or receipt.source_tree_sha256 != context.source_tree_sha256
        or receipt.probe_sha256 != probe_sha256
        or transport.probe_sha256 != probe_sha256
        or transport.exit_code != 0
        or ShadowRayObservation.model_validate_json(transport.stdout)
        != receipt.observation
    ):
        raise ValueError(
            "ShadowRay observation is not bound to the run and guest transport"
        )
    observation = receipt.observation
    if set(observation.checks) != SHADOWRAY_CHECKS:
        raise ValueError("ShadowRay observation has missing or extra checks")
    if (
        not observation.files
        or not observation.http_log
        or observation.scope != SHADOWRAY_SCOPE
    ):
        raise ValueError("ShadowRay observation exceeds or omits its fixture scope")
    return observation, {
        "observer_transport_path": transport_path.relative_to(run_root).as_posix(),
        "observer_transport_sha256": sha256_file(transport_path),
        "probe_sha256": probe_sha256,
    }


def validate_costaricto_observation(
    run_root: Path, context: RunContext, source_manifest: dict
) -> tuple[CostaRictoObservation, dict]:
    """Bind the CostaRicto guest probe to the exact run and transport."""
    evidence = run_root / "evidence"
    receipt_path = evidence / "costaricto-target-observation.json"
    transport_path = evidence / "costaricto-target-observation.transport.json"
    receipt = CostaRictoObserverReceipt.model_validate(read_json(receipt_path))
    transport = ProbeTransport.model_validate(read_json(transport_path))
    probe_sha256 = source_file_digest(
        run_root, source_manifest, "scripts/probe_costaricto_target.py"
    )
    if (
        receipt.schema_name != "costaricto-target-observer-receipt/v1"
        or receipt.campaign_id != context.campaign_id
        or receipt.source_tree_sha256 != context.source_tree_sha256
        or receipt.probe_sha256 != probe_sha256
        or transport.probe_sha256 != probe_sha256
        or transport.exit_code != 0
        or CostaRictoObservation.model_validate_json(transport.stdout)
        != receipt.observation
    ):
        raise ValueError(
            "CostaRicto observation is not bound to the run and guest transport"
        )
    observation = receipt.observation
    if (
        set(observation.checks) != COSTARICTO_CHECKS
        or observation.observer_uid != 0
        or observation.scope != COSTARICTO_SCOPE
        or set(observation.file_sha256)
        != {
            "collection_source",
            "collection_copy",
            "tool_source",
            "tool_copy",
            "benign_payload",
        }
        or any(
            not re.fullmatch(r"[0-9a-f]{64}", digest)
            for digest in observation.file_sha256.values()
        )
        or observation.file_sha256["collection_source"]
        != observation.file_sha256["collection_copy"]
        or observation.file_sha256["tool_source"]
        != observation.file_sha256["tool_copy"]
        or observation.file_sha256["benign_payload"] != COSTARICTO_PAYLOAD_SHA256
    ):
        raise ValueError(
            "CostaRicto guest observation exceeds or omits its bounded scope"
        )
    return observation, {
        "observer_transport_path": transport_path.relative_to(run_root).as_posix(),
        "observer_transport_sha256": sha256_file(transport_path),
        "probe_sha256": probe_sha256,
    }


def validate_costaricto_summary(
    run_root: Path, source_manifest: dict, summary: dict
) -> None:
    """Reject runner rows that exceed the version-bound CostaRicto contract."""
    campaign_path = "campaigns/0.costaricto.json"
    source_file_digest(run_root, source_manifest, campaign_path)
    campaign = read_json(run_root / "workspace" / campaign_path)
    declared = campaign["techniques"]
    results = summary.get("technique_results", [])
    if (
        campaign["campaign_id"] != "0.costaricto"
        or len(declared) != len(results)
        or len(declared) != 10
    ):
        raise ValueError("CostaRicto runner rows do not match the campaign contract")
    for technique, result in zip(declared, results, strict=True):
        products = result.get("capabilities_produced", [])
        if (
            result.get("technique_id") != technique["technique_id"]
            or result.get("execution_mode") != technique["expected_mode"]
            or not isinstance(result.get("fidelity"), dict)
            or result["fidelity"].get("declared") != technique["expected_fidelity"]
            or result.get("status") != "success"
            or not result.get("executor_name")
            or (
                technique["expected_mode"] == "naive_simulated"
                and (
                    not products
                    or any(
                        not product.startswith("simulation:") for product in products
                    )
                )
            )
        ):
            raise ValueError("CostaRicto runner row exceeds its declared contract")
        if technique["technique_id"] == "T1588.002" and products != [
            "simulation:guest_tool_staged"
        ]:
            raise ValueError("CostaRicto tool staging was promoted to acquisition")
        if technique["technique_id"] == "T1005" and products != [
            "collection:local_data"
        ]:
            raise ValueError("CostaRicto fixture copy claimed unobserved discovery")
    if sum(result["execution_mode"] == "real_controlled" for result in results) != 3:
        raise ValueError("CostaRicto controlled-step count changed")


def validate_shadowray_summary(
    run_root: Path, source_manifest: dict, summary: dict
) -> None:
    """Require every runner row to match the version-bound campaign contract."""
    campaign_path = "campaigns/0.shadowray.json"
    source_file_digest(run_root, source_manifest, campaign_path)
    campaign = read_json(run_root / "workspace" / campaign_path)
    declared = campaign["techniques"]
    results = summary.get("technique_results", [])
    if campaign["campaign_id"] != "0.shadowray" or len(results) != len(declared):
        raise ValueError("ShadowRay runner rows do not match the campaign contract")
    for technique, result in zip(declared, results, strict=True):
        if technique["expected_mode"] == "naive_simulated" and any(
            not product.startswith("simulation:")
            for product in result.get("capabilities_produced", [])
        ):
            raise ValueError("ShadowRay runner has an unscoped simulated product")
        if (
            result.get("technique_id") != technique["technique_id"]
            or result.get("execution_mode") != technique["expected_mode"]
            or result.get("status") != "success"
            or not result.get("executor_name")
            or set(result.get("capabilities_produced", []))
            != set(technique.get("produces", []))
        ):
            raise ValueError(
                "ShadowRay runner row does not match the campaign contract"
            )


def validate_observation(
    run_root: Path, context: RunContext, source_manifest: dict
) -> tuple[Path, TargetObservation, dict]:
    """Validate the declared campaign's independent guest observation."""
    evidence = run_root / "evidence"
    if context.campaign_id == "0.c0010":
        observation_path = evidence / "c0010-target-observation.json"
        observation, extra = validate_c0010_observation(
            run_root, context, source_manifest
        )
        expected_schema = "c0010-target-transfer-observation/v1"
    elif context.campaign_id == "0.shadowray":
        observation_path = evidence / "shadowray-target-observation.json"
        observation, extra = validate_shadowray_observation(
            run_root, context, source_manifest
        )
        expected_schema = "shadowray-fixture-observation/v1"
    elif context.campaign_id == "0.costaricto":
        observation_path = evidence / "costaricto-target-observation.json"
        observation, extra = validate_costaricto_observation(
            run_root, context, source_manifest
        )
        expected_schema = "costaricto-bounded-guest-observation/v1"
    elif context.campaign_id == "0.outer_space":
        observation_path = evidence / "outer-space-target-observation.json"
        observation, extra = validate_outer_space_observation(
            run_root, context, source_manifest
        )
        expected_schema = "outer-space-bounded-guest-observation/v1"
    else:
        observation_path = evidence / "c0026-target-observation.json"
        observation, extra = validate_c0026_observation(
            run_root, context, source_manifest
        )
        expected_schema = "c0026-target-chain-observation/v1"
    if (
        observation.schema_name != expected_schema
        or observation.hostname != "target-linux-1"
        or not observation.boot_id
        or not observation.checks
        or not observation.passed
        or not all(observation.checks.values())
    ):
        raise ValueError("Independent target observation did not pass")
    return observation_path, observation, extra


def runner_summary(evidence: Path, campaign_id: str) -> tuple[str, dict]:
    candidates = list(evidence.glob(f"{campaign_id}_*/summary.json"))
    candidates.extend(evidence.glob("runtime-v2/*/summary.json"))
    if len(candidates) != 1:
        raise ValueError("Expected exactly one campaign summary")
    path = candidates[0]
    return path.relative_to(evidence).as_posix(), read_json(path)


def typed_runner_fields(
    summary: dict,
    summary_root: Path,
    run_root: Path,
    source_manifest: dict,
    observation: TargetObservation,
) -> dict:
    """Bind typed acquisitions to the independent guest observation."""
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from typed_runtime_seal import validate_typed_completion
    else:
        from scripts.typed_runtime_seal import validate_typed_completion

    report = validate_typed_completion(
        summary, summary_root, run_root / "workspace", source_manifest
    )
    independent = read_json(run_root / "evidence/c0026-target-observation.json")[
        "observation"
    ]
    expected_checks = {
        "collection_matches_declared_sources",
        "archive_contains_collection",
        "chunks_reassemble_archive",
        "dynamic_resolution_recorded",
        "benign_transfer_retained",
    }
    if (
        observation.hostname != report.bootstrap.scope.host_id
        or observation.boot_id != report.bootstrap.scope.epoch
        or set(observation.checks) != expected_checks
    ):
        raise ValueError(
            "Independent C0026 observation differs from the typed lifecycle or checks"
        )
    products = {
        fact.name: fact.content_sha256
        for step in report.steps
        for fact in step.outcome.authorizing_facts
    }
    for name, key in (
        ("collection:verified", "collection_sha256"),
        ("archive:verified", "archive_sha256"),
    ):
        if independent.get(key) != products.get(name) or products.get(name) is None:
            raise ValueError(
                "Independent C0026 content differs from the acquired runtime products"
            )
    return {
        "runner_schema_version": report.schema_version,
        "runner_run_id": report.run_id,
        "runner_total_techniques": report.total_techniques,
        "runner_effects_observed": report.effects_observed,
        "runner_simulated": report.simulated,
    }


def build_receipt(
    run_root: Path, *, recorded_vm_states: dict[str, str] | None = None
) -> dict:
    context = RunContext.model_validate(read_json(run_root / "run_context.json"))
    if (
        not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", context.campaign_id)
        or ".." in context.campaign_id
    ):
        raise ValueError("Invalid campaign ID in run context")
    if context.campaign_id not in OBSERVATION_FILES:
        raise ValueError("No finalization contract for this campaign")
    if context.campaign_id == "0.c0010":
        summary_path, summary = runner_summary(
            run_root / "evidence", context.campaign_id
        )
        if summary.get("schema_version") == "runtime-campaign/v2":
            return build_typed_c0010_receipt(
                run_root, context, summary_path, summary, recorded_vm_states
            )
    if context.campaign_id == "0.costaricto":
        summary_path, summary = runner_summary(
            run_root / "evidence", context.campaign_id
        )
        if summary.get("schema_version") == "runtime-campaign/v2":
            return build_typed_costaricto_receipt(
                run_root, context, summary_path, summary, recorded_vm_states
            )
    if context.exit_code != 0 or not context.keep_lab_requested:
        raise ValueError("Runner did not finish with a retained lab for observation")
    if (context.execution_log_path is None) != (context.execution_log_sha256 is None):
        raise ValueError("Incomplete execution log binding in run context")
    if context.execution_log_path is not None:
        if context.execution_log_path != "execution.log":
            raise ValueError("Unexpected execution log path in run context")
        execution_log = run_root / context.execution_log_path
        if execution_log.is_symlink() or not execution_log.is_file():
            raise ValueError("Execution log is missing or is not a regular file")
        if sha256_file(execution_log) != context.execution_log_sha256:
            raise ValueError("Execution log differs from the run context")

    source_manifest = read_json(run_root / "source_manifest.json")
    initial_evidence = read_json(run_root / "evidence_manifest.json")
    if source_manifest["tree_sha256"] != context.source_tree_sha256:
        raise ValueError("Source manifest does not match the run context")
    if initial_evidence["tree_sha256"] != context.evidence_tree_sha256:
        raise ValueError("Initial evidence manifest does not match the run context")

    evidence = run_root / "evidence"
    final_manifest = tree_manifest(evidence)
    unchanged_initial_evidence(
        run_root, final_manifest, OBSERVATION_FILES[context.campaign_id]
    )
    observation_path, observation, observer_evidence = validate_observation(
        run_root, context, source_manifest
    )

    summary_path, summary = runner_summary(evidence, context.campaign_id)
    typed = summary.get("schema_version") == "runtime-campaign/v2"
    typed_layout = summary_path.startswith("runtime-v2/")
    if typed != typed_layout:
        raise ValueError("Runtime summary schema differs from its evidence layout")
    if typed:
        if summary_path != f"runtime-v2/{summary['run_id']}/summary.json":
            raise ValueError(
                "Runtime summary run identity differs from its evidence layout"
            )
        if (
            context.campaign_id != "0.c0026"
            or summary["campaign_id"] != context.campaign_id
        ):
            raise ValueError("No typed finalization contract for this campaign")
        runner_fields = typed_runner_fields(
            summary,
            (evidence / summary_path).parent,
            run_root,
            source_manifest,
            observation,
        )
    elif (
        summary["campaign_id"] != context.campaign_id
        or summary["successful"] != summary["total_techniques"]
        or summary["failed"] != 0
        or summary["skipped"] != 0
    ):
        raise ValueError("Runner summary did not complete every declared step")
    else:
        runner_fields = {"runner_successful": summary["successful"]}
    if context.campaign_id == "0.c0010":
        results = summary.get("technique_results", [])
        if (
            len(results) != summary["total_techniques"]
            or any(
                result.get("status") != "success" or not result.get("executor_name")
                for result in results
            )
            or [
                result["executor_name"]
                for result in results
                if result.get("technique_id") == "T1588.002"
            ]
            not in (
                ["executors.executor_registry.execute_t1588_002_real"],
                ["executors.executor_registry.execute_t1588_002_simulated"],
            )
            or any("shadowray" in result["executor_name"].lower() for result in results)
        ):
            raise ValueError("C0010 runner used an incompatible or unrecorded executor")
    elif context.campaign_id == "0.shadowray":
        validate_shadowray_summary(run_root, source_manifest, summary)
    elif context.campaign_id == "0.costaricto":
        validate_costaricto_summary(run_root, source_manifest, summary)
    elif context.campaign_id == "0.outer_space":
        validate_outer_space_summary(summary)

    workspace = run_root / "workspace"
    vm_states = receipt_vm_states(workspace, context.campaign_id, recorded_vm_states)
    if any(state != "not_created" for state in vm_states.values()):
        raise ValueError("Declared lab VMs have not all been destroyed")

    artifact_manifest = read_json(run_root / "artifact_manifest.json")
    if artifact_manifest["tree_sha256"] != context.artifact_tree_sha256:
        raise ValueError("Artifact manifest does not match the run context")
    if tree_manifest(workspace / "data" / "artifacts") != artifact_manifest:
        raise ValueError("Runner artifacts changed after the initial manifest")

    scopes = {
        "0.c0010": "C0010 declared SUT fixtures and bounded guest transfer record; "
        "not historical watering-hole fidelity or external delivery.",
        "0.c0026": "Controlled guest effects only; not historical fidelity or external C2.",
        "0.costaricto": COSTARICTO_SCOPE,
        "0.shadowray": SHADOWRAY_SCOPE,
        "0.outer_space": OUTER_SPACE_SCOPE,
    }
    return {
        "schema": "isolated-lab-final-receipt/v2"
        if typed
        else "isolated-lab-final-receipt/v1",
        "campaign_id": context.campaign_id,
        "source_tree_sha256": context.source_tree_sha256,
        "initial_evidence_tree_sha256": context.evidence_tree_sha256,
        "final_evidence_tree_sha256": final_manifest["tree_sha256"],
        "artifact_tree_sha256": context.artifact_tree_sha256,
        **(
            {"execution_log_sha256": context.execution_log_sha256}
            if context.execution_log_sha256 is not None
            else {}
        ),
        "observation_path": observation_path.relative_to(run_root).as_posix(),
        "observation_sha256": sha256_file(observation_path),
        "runner_summary_path": summary_path,
        **runner_fields,
        "observer_checks": observation.checks,
        **observer_evidence,
        "vm_states": vm_states,
        "cycle_passed": True,
        "scope": scopes[context.campaign_id],
    }


def _verify_typed_source_manifest(run_root: Path, context: RunContext) -> dict:
    manifest = read_json(run_root / "source_manifest.json")
    entries = manifest.get("files")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Typed source manifest has no file list")
    workspace = run_root / "workspace"
    digest = hashlib.sha256()
    seen = set()
    for entry in entries:
        relative = entry["path"]
        path = Path(relative)
        if (
            path.is_absolute()
            or "\\" in relative
            or any(part in {"", ".", ".."} for part in relative.split("/"))
            or relative in seen
        ):
            raise ValueError(
                "Typed source manifest contains an unsafe or repeated path"
            )
        seen.add(relative)
        source = workspace / path
        if source.is_symlink() or not source.is_file():
            raise ValueError("Typed source file is missing or linked")
        if (
            sha256_file(source) != entry["sha256"]
            or source.stat().st_size != entry["size"]
        ):
            raise ValueError("Typed source file differs from its initial manifest")
        digest.update(relative.encode("utf-8") + b"\0")
        digest.update(entry["sha256"].encode("ascii") + b"\0")
    if (
        digest.hexdigest() != manifest.get("tree_sha256")
        or digest.hexdigest() != context.source_tree_sha256
    ):
        raise ValueError("Typed source tree differs from the run context")
    return manifest


def build_typed_c0010_receipt(
    run_root: Path,
    context: RunContext,
    summary_path: str,
    summary: dict,
    recorded_vm_states: dict[str, str] | None = None,
) -> dict:
    """Seal the bounded C0010 run using its retained in-run observers."""
    if context.exit_code != 0 or summary.get("campaign_id") != "0.c0010":
        raise ValueError("C0010 typed run did not finish successfully")
    if (
        context.execution_log_path != "execution.log"
        or context.execution_log_sha256 is None
    ):
        raise ValueError("C0010 typed run lacks a bound execution log")
    log_path = run_root / context.execution_log_path
    if log_path.is_symlink() or sha256_file(log_path) != context.execution_log_sha256:
        raise ValueError("C0010 execution log differs from the run context")
    source_manifest = _verify_typed_source_manifest(run_root, context)
    evidence = run_root / "evidence"
    evidence_manifest = read_json(run_root / "evidence_manifest.json")
    if evidence_manifest["tree_sha256"] != context.evidence_tree_sha256:
        raise ValueError("C0010 initial evidence manifest differs from the run context")
    final_evidence_manifest = tree_manifest(evidence)
    unchanged_initial_evidence(
        run_root,
        final_evidence_manifest,
        OBSERVATION_FILES[context.campaign_id],
    )
    observation, observer_evidence = validate_c0010_observation(
        run_root,
        context,
        source_manifest,
    )
    if summary_path != f"runtime-v2/{summary['run_id']}/summary.json":
        raise ValueError("C0010 summary path differs from its run identity")
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from typed_runtime_seal import validate_c0010_typed_completion
    else:
        from scripts.typed_runtime_seal import validate_c0010_typed_completion
    report = validate_c0010_typed_completion(
        summary,
        (evidence / summary_path).parent,
        run_root / "workspace",
        source_manifest,
    )
    vm_states = receipt_vm_states(run_root / "workspace", "0.c0010", recorded_vm_states)
    if any(state != "not_created" for state in vm_states.values()):
        raise ValueError("C0010 declared lab VMs have not all been destroyed")
    artifact_manifest = read_json(run_root / "artifact_manifest.json")
    if (
        context.artifact_tree_sha256 is None
        or artifact_manifest["tree_sha256"] != context.artifact_tree_sha256
        or tree_manifest(run_root / "workspace/data/artifacts") != artifact_manifest
    ):
        raise ValueError("C0010 runner artifacts differ from the retained manifest")
    controller_count = sum(
        step.status == "observed" and step.contract.scope.locus == "controller"
        for step in report.steps
    )
    guest_count = sum(
        step.status == "observed" and step.contract.scope.locus == "target"
        for step in report.steps
    )
    if (controller_count, guest_count, report.simulated) != (4, 1, 4):
        raise ValueError(
            "C0010 bounded outcome counts differ from the reviewed contract"
        )
    return {
        "schema": "isolated-c0010-typed-receipt/v1",
        "campaign_id": report.campaign_id,
        "run_id": report.run_id,
        "source_tree_sha256": context.source_tree_sha256,
        "evidence_tree_sha256": context.evidence_tree_sha256,
        "final_evidence_tree_sha256": final_evidence_manifest["tree_sha256"],
        "artifact_tree_sha256": context.artifact_tree_sha256,
        "execution_log_sha256": context.execution_log_sha256,
        "summary_path": summary_path,
        "summary_sha256": sha256_file(evidence / summary_path),
        "observer_checks": observation.checks,
        **observer_evidence,
        "controller_effects_observed": controller_count,
        "guest_effects_observed": guest_count,
        "simulated": report.simulated,
        "vm_states": vm_states,
        "cycle_passed": True,
        "scope": "Four controller staging/fetch effects and one bounded guest transfer; "
        "not historical watering-hole fidelity, external delivery, or five guest effects.",
    }


def build_typed_costaricto_receipt(
    run_root: Path,
    context: RunContext,
    summary_path: str,
    summary: dict,
    recorded_vm_states: dict[str, str] | None = None,
) -> dict:
    """Seal the exact typed run and its three bounded guest effects."""
    if context.exit_code != 0 or summary.get("campaign_id") != "0.costaricto":
        raise ValueError("CostaRicto typed run did not finish successfully")
    if (
        context.execution_log_path != "execution.log"
        or context.execution_log_sha256 is None
    ):
        raise ValueError("CostaRicto typed run lacks a bound execution log")
    log_path = run_root / context.execution_log_path
    if log_path.is_symlink() or sha256_file(log_path) != context.execution_log_sha256:
        raise ValueError("CostaRicto execution log differs from its run context")
    source_manifest = _verify_typed_source_manifest(run_root, context)
    evidence = run_root / "evidence"
    evidence_manifest = read_json(run_root / "evidence_manifest.json")
    if (
        evidence_manifest["tree_sha256"] != context.evidence_tree_sha256
        or tree_manifest(evidence) != evidence_manifest
    ):
        raise ValueError("CostaRicto evidence differs from its initial manifest")
    if summary_path != f"runtime-v2/{summary['run_id']}/summary.json":
        raise ValueError("CostaRicto summary path differs from its run identity")
    if not __package__:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
        from typed_runtime_seal import validate_costaricto_typed_completion
    else:
        from scripts.typed_runtime_seal import validate_costaricto_typed_completion
    report = validate_costaricto_typed_completion(
        summary,
        (evidence / summary_path).parent,
        run_root / "workspace",
        source_manifest,
    )
    vm_states = receipt_vm_states(
        run_root / "workspace", "0.costaricto", recorded_vm_states
    )
    if any(state != "not_created" for state in vm_states.values()):
        raise ValueError("CostaRicto declared VMs have not all been destroyed")
    artifact_manifest = read_json(run_root / "artifact_manifest.json")
    if (
        context.artifact_tree_sha256 is None
        or artifact_manifest["tree_sha256"] != context.artifact_tree_sha256
        or tree_manifest(run_root / "workspace/data/artifacts") != artifact_manifest
    ):
        raise ValueError("CostaRicto runner artifacts differ from the manifest")
    return {
        "schema": "isolated-costaricto-typed-receipt/v1",
        "campaign_id": report.campaign_id,
        "run_id": report.run_id,
        "source_tree_sha256": context.source_tree_sha256,
        "evidence_tree_sha256": context.evidence_tree_sha256,
        "artifact_tree_sha256": context.artifact_tree_sha256,
        "execution_log_sha256": context.execution_log_sha256,
        "summary_path": summary_path,
        "summary_sha256": sha256_file(evidence / summary_path),
        "guest_effects_observed": report.effects_observed,
        "simulated": report.simulated,
        "vm_states": vm_states,
        "cycle_passed": True,
        "scope": "Guest-local service listing, loopback benign transfer, and declared "
        "fixture copy; not remote scanning, historical APT fidelity, or seven "
        "additional observed effects.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing final receipt without writing",
    )
    args = parser.parse_args()
    run_root = args.run_root.resolve()
    receipt = build_receipt(run_root)
    receipt_path = run_root / FINAL_RECEIPT
    if args.verify:
        if read_json(receipt_path) != receipt:
            raise ValueError("Final receipt no longer matches the run")
    else:
        if receipt_path.exists():
            raise FileExistsError(receipt_path)
        write_json(receipt_path, receipt)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
