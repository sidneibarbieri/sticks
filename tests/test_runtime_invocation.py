"""Typed invocation controls real executor effects without promoting products."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from executors.executor_registry import (
    ExecutorRegistry,
    ExecutorMetadata,
    ExecutionMode,
)
from runners.capability_facts import CapabilityRequirement, FactScope
from runners.capability_authority import LabShellRequest, acquire_registered_observation
from runners.capability_store import CapabilityStore
from runners.runtime_step_contracts import RuntimeStepContract
from runners.runtime_invocation import invoke_runtime_step, portable_invocation_text


def test_portable_invocation_text_projects_workspace_paths(tmp_path):
    root = tmp_path / "artifact"
    artifact = root / "data" / "artifacts" / "fixture.txt"
    assert portable_invocation_text(f"created at {artifact}", root) == (
        "created at ./data/artifacts/fixture.txt"
    )


def test_portable_invocation_text_rejects_external_home_path(tmp_path):
    with pytest.raises(ValueError, match="host home path outside"):
        portable_invocation_text(str(Path.home() / "secret.txt"), tmp_path)


def write_marker(campaign_id, sut_profile_id):
    Path(sut_profile_id).write_text(campaign_id, encoding="utf-8")
    return True, "completed", "", [sut_profile_id]


def fail_with_original_error(campaign_id, sut_profile_id):
    raise RuntimeError("original executor failure")


def report_workspace_path(campaign_id, sut_profile_id):
    artifact = (
        Path(__file__).resolve().parents[1] / "data" / "artifacts" / "fixture.txt"
    )
    return True, f"created at {artifact}", "", [str(artifact)]


def setup_executor(executor=write_marker):
    registered = ExecutorRegistry()
    metadata = ExecutorMetadata(
        technique_id="T1005",
        technique_name="bounded test",
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        produces=["declared:output"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
    )
    registered.register("T1005", metadata, executor, campaign_id="test-campaign")
    scope = FactScope(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-a",
        principal="ubuntu",
    )
    contract = RuntimeStepContract(
        campaign_id="test-campaign",
        occurrence=1,
        technique_id="T1005",
        executor_id=f"{executor.__module__}.{executor.__qualname__}",
        executor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        mode="real_controlled",
        scope=scope,
        requirements=(),
        observers=(),
    )
    return registered, contract


def test_invocation_records_completion_without_authority_promotion(tmp_path):
    registered, contract = setup_executor()
    store = CapabilityStore()
    marker = tmp_path / "marker"
    result = invoke_runtime_step(
        contract, store, registered, sut_profile_id=str(marker)
    )
    assert marker.read_text() == "test-campaign"
    assert result.executor_completed is True
    assert result.declared_products == ("declared:output",)
    assert store.snapshot() == ()


def test_invocation_retains_portable_paths(tmp_path):
    registered, contract = setup_executor(report_workspace_path)
    result = invoke_runtime_step(
        contract, CapabilityStore(), registered, sut_profile_id=str(tmp_path)
    )
    assert result.stdout == "created at ./data/artifacts/fixture.txt"
    assert result.artifacts == ("./data/artifacts/fixture.txt",)


def test_unmet_scoped_precondition_prevents_executor_effect(tmp_path):
    registered, contract = setup_executor()
    required = CapabilityRequirement(
        name="lab:shell", scope=contract.scope, accepted_origins={"observed"}
    )
    guarded = RuntimeStepContract(
        **(contract.model_dump() | {"requirements": (required,)})
    )
    marker = tmp_path / "marker"
    with pytest.raises(ValueError):
        invoke_runtime_step(
            guarded, CapabilityStore(), registered, sut_profile_id=str(marker)
        )
    assert not marker.exists()


def test_source_drift_prevents_executor_effect(tmp_path):
    registered, contract = setup_executor()
    altered = RuntimeStepContract(
        **(contract.model_dump() | {"executor_sha256": "a" * 64})
    )
    marker = tmp_path / "marker"
    with pytest.raises(ValueError):
        invoke_runtime_step(
            altered, CapabilityStore(), registered, sut_profile_id=str(marker)
        )
    assert not marker.exists()


def test_executor_exception_is_not_masked(tmp_path):
    registered, contract = setup_executor(fail_with_original_error)
    with pytest.raises(RuntimeError, match="original executor failure"):
        invoke_runtime_step(
            contract,
            CapabilityStore(),
            registered,
            sut_profile_id=str(tmp_path / "marker"),
        )


def observed_shell(monkeypatch, tmp_path):
    measured = FactScope(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-linux-1",
        principal="ubuntu",
    )

    def probe(*args, **kwargs):
        reply = json.dumps(
            dict(
                hostname="target-linux-1",
                principal="ubuntu",
                boot_id="boot-a",
                nonce="nonce-a",
            )
        )
        return subprocess.CompletedProcess(["probe"], 0, reply, "")

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", probe)
    request = LabShellRequest(sut_profile_id="0.c0026", scope=measured, nonce="nonce-a")
    reference = acquire_registered_observation("lab-shell", request, run_root=tmp_path)
    store = CapabilityStore()
    store.add_observed(
        reference,
        run_root=tmp_path,
        expected_scope=measured,
        expected_predicate="shell-nonce",
    )
    return store, measured


def test_observed_prerequisite_enables_legitimate_executor_effect(
    monkeypatch, tmp_path
):
    store, measured = observed_shell(monkeypatch, tmp_path)
    registered, contract = setup_executor()
    required = CapabilityRequirement(
        name="lab:shell", scope=measured, accepted_origins={"observed"}
    )
    guarded = RuntimeStepContract(
        **(contract.model_dump() | {"scope": measured, "requirements": (required,)})
    )
    marker = tmp_path / "marker"
    result = invoke_runtime_step(guarded, store, registered, sut_profile_id=str(marker))
    assert result.executor_completed
    assert marker.read_text() == "test-campaign"
    assert [fact.name for fact in store.snapshot()] == ["lab:shell"]


def test_one_observed_prerequisite_does_not_satisfy_two_requirements(
    monkeypatch, tmp_path
):
    store, measured = observed_shell(monkeypatch, tmp_path)
    registered, contract = setup_executor()
    requirements = tuple(
        CapabilityRequirement(name=name, scope=measured, accepted_origins={"observed"})
        for name in ("lab:shell", "collection:verified")
    )
    guarded = RuntimeStepContract(
        **(contract.model_dump() | {"scope": measured, "requirements": requirements})
    )
    marker = tmp_path / "marker"
    with pytest.raises(ValueError):
        invoke_runtime_step(guarded, store, registered, sut_profile_id=str(marker))
    assert not marker.exists()
