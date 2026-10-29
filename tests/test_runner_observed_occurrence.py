"""Runner keeps executor completion separate from independently observed facts."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from executors.executor_registry import (
    ExecutorMetadata,
    ExecutorRegistry,
    ExecutionMode,
)
from runners.campaign_runner import UnifiedCampaignRunner
from runners.capability_authority import LabShellRequest
from runners.capability_facts import CapabilityRequirement, FactScope
from runners.runtime_step_contracts import RuntimeStepContract


def bounded_executor(campaign_id, sut_profile_id):
    return True, campaign_id + ":" + sut_profile_id, "", []


def prepared_runner(tmp_path):
    runner = UnifiedCampaignRunner("0.c0026", tmp_path)
    selected = ExecutorRegistry()
    step = runner.campaign.steps[1]
    metadata = ExecutorMetadata(
        technique_id=step.technique_id,
        technique_name="test effect",
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        produces=["unobserved:assertion"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
    )
    selected.register(
        step.technique_id, metadata, bounded_executor, campaign_id="0.c0026"
    )
    scope = FactScope(
        run_id=runner.run_id,
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-linux-1",
        principal="ubuntu",
    )
    contract = RuntimeStepContract(
        campaign_id="0.c0026",
        occurrence=step.order,
        technique_id=step.technique_id,
        executor_id=f"{bounded_executor.__module__}.{bounded_executor.__qualname__}",
        executor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        mode="real_controlled",
        scope=scope,
        requirements=(),
        observers=("lab-shell",),
    )
    request = LabShellRequest(sut_profile_id="0.c0026", scope=scope, nonce="nonce-a")
    return runner, selected, contract, request


def guest_probe(monkeypatch, principal):
    def run(*args, **kwargs):
        payload = dict(
            hostname="target-linux-1",
            principal=principal,
            boot_id="boot-a",
            nonce="nonce-a",
        )
        return subprocess.CompletedProcess(["probe"], 0, json.dumps(payload), "")

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", run)


def test_completed_executor_with_failed_observation_grants_no_facts(
    monkeypatch, tmp_path
):
    runner, selected, contract, request = prepared_runner(tmp_path)
    guest_probe(monkeypatch, "vagrant")
    result = runner.execute_contracted_occurrence(
        contract, {"lab-shell": request}, run_root=tmp_path, selected_registry=selected
    )
    assert result.invocation.executor_completed is True
    assert result.observations[0].passed is False
    assert result.authorizing_facts == ()
    assert not any(fact.origin == "observed" for fact in runner.fact_store.snapshot())


def test_only_independently_measured_product_becomes_authority(monkeypatch, tmp_path):
    runner, selected, contract, request = prepared_runner(tmp_path)
    guest_probe(monkeypatch, "ubuntu")
    result = runner.execute_contracted_occurrence(
        contract, {"lab-shell": request}, run_root=tmp_path, selected_registry=selected
    )
    assert result.invocation.declared_products == ("unobserved:assertion",)
    assert [fact.name for fact in result.authorizing_facts] == ["lab:shell"]
    assert "unobserved:assertion" not in [
        fact.name for fact in runner.fact_store.snapshot()
    ]


def test_wrong_occurrence_identity_is_refused_before_execution(tmp_path):
    runner, selected, contract, request = prepared_runner(tmp_path)
    wrong = RuntimeStepContract(
        **(contract.model_dump() | {"campaign_id": "other-campaign"})
    )
    with pytest.raises(ValueError):
        runner.execute_contracted_occurrence(
            wrong, {"lab-shell": request}, run_root=tmp_path, selected_registry=selected
        )
    assert not (tmp_path / "observations").exists()


def test_missing_observer_request_is_not_silently_skipped(tmp_path):
    runner, selected, contract, _ = prepared_runner(tmp_path)
    with pytest.raises(ValueError):
        runner.execute_contracted_occurrence(
            contract, {}, run_root=tmp_path, selected_registry=selected
        )


def test_observer_exception_preserves_completed_invocation(monkeypatch, tmp_path):
    runner, selected, contract, request = prepared_runner(tmp_path)
    failure = OSError("observer transport failed")

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", fail)
    with pytest.raises(OSError) as caught:
        runner.execute_contracted_occurrence(
            contract,
            {"lab-shell": request},
            run_root=tmp_path,
            selected_registry=selected,
        )
    assert caught.value is failure
    assert len(runner.runtime_invocations) == 1
    assert runner.runtime_invocations[0][1].executor_completed is True
    assert not any(fact.origin == "observed" for fact in runner.fact_store.snapshot())


def test_observer_failure_preserves_completion_in_disk_journal(monkeypatch, tmp_path):
    runner, selected, contract, request = prepared_runner(tmp_path)

    def fail(*args, **kwargs):
        raise OSError("observer failure")

    monkeypatch.setattr("runners.lab_bootstrap_observer.run_bash_on_target_vm", fail)
    with pytest.raises(OSError):
        runner.execute_contracted_occurrence(
            contract,
            {"lab-shell": request},
            run_root=tmp_path,
            selected_registry=selected,
        )
    records = [
        json.loads(path.read_text())
        for path in (tmp_path / "runtime_journal").glob("*.json")
    ]
    assert {record["phase"] for record in records} == {
        "started",
        "executor_completed",
        "error",
    }
    completed = next(
        record for record in records if record["phase"] == "executor_completed"
    )
    assert completed["invocation"]["executor_completed"] is True
    failure = next(record for record in records if record["phase"] == "error")
    assert failure["error_type"] == "OSError"
    assert failure["error_message"] == "observer failure"
    assert failure["authorizing_facts"] == []


@pytest.mark.parametrize("stage", ["executor", "observer", "timeout"])
def test_process_failure_retains_original_streams_and_exit(
    monkeypatch, tmp_path, stage
):
    runner, selected, contract, request = prepared_runner(tmp_path)
    original = subprocess.CalledProcessError(
        23, ["guest-command"], output="UNIQUE_STDOUT", stderr="UNIQUE_STDERR"
    )
    if stage == "timeout":
        original = subprocess.TimeoutExpired(
            ["guest-command"], 20, output=b"UNIQUE_STDOUT", stderr=b"UNIQUE_STDERR"
        )

    def fail(*args, **kwargs):
        raise original

    target = (
        "runners.campaign_runner.invoke_runtime_step"
        if stage == "executor"
        else "runners.lab_bootstrap_observer.run_bash_on_target_vm"
    )
    monkeypatch.setattr(target, fail)
    with pytest.raises(type(original)) as caught:
        runner.execute_contracted_occurrence(
            contract,
            {"lab-shell": request},
            run_root=tmp_path,
            selected_registry=selected,
        )
    assert caught.value is original
    records = [
        json.loads(path.read_text())
        for path in (tmp_path / "runtime_journal").glob("*.json")
    ]
    retained = next(record for record in records if record["phase"] == "error")
    assert {
        name: retained["process_failure"][name]
        for name in ("returncode", "stdout", "stderr", "timed_out")
    } == {
        "returncode": None if stage == "timeout" else 23,
        "stdout": "UNIQUE_STDOUT",
        "stderr": "UNIQUE_STDERR",
        "timed_out": stage == "timeout",
    }
    assert retained["authorizing_facts"] == []


def test_simulated_product_is_recorded_without_controlled_authority(tmp_path):
    runner, selected, _, _ = prepared_runner(tmp_path)
    step = runner.campaign.steps[0]
    metadata = ExecutorMetadata(
        technique_id=step.technique_id,
        technique_name="simulated input",
        execution_mode=ExecutionMode.NAIVE_SIMULATED,
        produces=["lab:shell"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
    )
    selected.register(
        step.technique_id, metadata, bounded_executor, campaign_id="0.c0026"
    )
    scoped = FactScope(
        run_id=runner.run_id,
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-linux-1",
        principal="ubuntu",
    )
    contract = RuntimeStepContract(
        campaign_id="0.c0026",
        occurrence=step.order,
        technique_id=step.technique_id,
        executor_id=f"{bounded_executor.__module__}.{bounded_executor.__qualname__}",
        executor_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        mode="naive_simulated",
        scope=scoped,
        requirements=(),
        observers=(),
    )
    outcome = runner.execute_contracted_occurrence(
        contract, {}, run_root=tmp_path, selected_registry=selected
    )
    assert outcome.authorizing_facts == ()
    assert len(outcome.simulated_facts) == 1
    assert outcome.simulated_facts[0].origin == "simulation"
    requirement = CapabilityRequirement(
        name="lab:shell", scope=scoped, accepted_origins={"observed"}
    )
    assert runner.fact_store.match(requirement) is None
    records = [
        json.loads(path.read_text())
        for path in (tmp_path / "runtime_journal").glob("*.json")
    ]
    assert any(record["simulated_facts"] for record in records)
