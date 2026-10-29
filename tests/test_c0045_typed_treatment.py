"""A typed C0045 occurrence joins a live guest PID to replayed CPU evidence."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from runners.c0045_compute_observer import C0045ComputeRequest
from runners.c0045_runtime_contracts import (
    c0045_treatment_registry, load_c0045_runtime_contract,
)
from runners.campaign_runner import C0045LiveObserverBinding, UnifiedCampaignRunner
from runners.capability_authority import LabShellRequest, acquire_registered_observation
from runners.capability_facts import FactScope
from runners.capability_observations import PredicateObservation
from runners.target_compute_predicate import TargetProcessCpuSample
from runners.target_process_cpu_transport import GuestCpuAcquisition, _PROBE_PATH


def _acquisition(request, monotonic_ns, cpu_ticks):
    sample = TargetProcessCpuSample(
        scope=request.scope, process_id=request.process_id,
        process_start_ticks=400,
        process_command_sha256=request.command_sha256,
        monotonic_ns=monotonic_ns, user_cpu_ticks=cpu_ticks,
        system_cpu_ticks=2,
    )
    reply = {
        "nonce": request.nonce, "boot_id": request.scope.epoch,
        "hostname": request.scope.host_id, "principal": request.scope.principal,
        "process_id": request.process_id,
        "process_start_ticks": sample.process_start_ticks,
        "process_command_sha256": request.command_sha256,
        "monotonic_ns": monotonic_ns, "user_cpu_ticks": cpu_ticks,
        "system_cpu_ticks": sample.system_cpu_ticks,
    }
    return GuestCpuAcquisition(
        sample=sample, reply_json=json.dumps(reply),
        probe_source_sha256=hashlib.sha256(_PROBE_PATH.read_bytes()).hexdigest(),
    )


@pytest.mark.parametrize("after_ticks", (12, 20))
def test_typed_occurrence_grants_only_positive_guest_compute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_ticks: int
) -> None:
    runner = UnifiedCampaignRunner("0.shadowray", tmp_path / "output")
    run_root = tmp_path / "run"
    run_root.mkdir()
    scope = FactScope(
        run_id=runner.run_id, environment_id=f"lab-{runner.run_id}",
        epoch="boot-c0045", locus="target", host_id="target-linux-1",
        principal="rayuser",
    )
    selected_registry = c0045_treatment_registry()
    contract = load_c0045_runtime_contract(scope, selected_registry)

    def fake_shell(**_kwargs):
        return PredicateObservation(
            scope=scope, predicate_id="shell-nonce", passed=True,
            established_facts=("lab:shell",), details={},
        )

    monkeypatch.setattr("runners.capability_authority.observe_lab_shell", fake_shell)
    shell_reference = acquire_registered_observation(
        "lab-shell",
        LabShellRequest(sut_profile_id="0.shadowray", scope=scope, nonce="shellnonce01"),
        run_root=run_root,
    )
    runner.fact_store.add_observed(
        shell_reference, run_root=run_root, expected_scope=scope,
        expected_predicate="shell-nonce",
    )
    guest_commands = []

    def fake_guest(profile, script, *, execution_user, timeout):
        guest_commands.append(script)
        assert profile == "0.shadowray" and execution_user == "rayuser"
        return subprocess.CompletedProcess(
            args=script, returncode=0,
            stdout="123\n" if len(guest_commands) == 1 else "", stderr="",
        )

    monkeypatch.setattr(
        "executors.c0045_compute_executor.run_bash_on_target_vm", fake_guest
    )
    sample_count = 0

    def fake_sample(request):
        nonlocal sample_count
        sample_count += 1
        return _acquisition(
            request, 1000 if sample_count == 1 else 2000,
            10 if sample_count == 1 else after_ticks,
        )

    monkeypatch.setattr(
        "runners.target_cpu_measurement.acquire_guest_cpu_sample", fake_sample
    )
    monkeypatch.setattr("runners.target_cpu_measurement.time.sleep", lambda _: None)

    def request_for_process(selection):
        return C0045ComputeRequest(
            sut_profile_id="0.shadowray", scope=scope,
            nonce=selection.nonce, producer_occurrence=10,
            process_id=selection.process_id,
            command_sha256=selection.command_sha256,
        )

    outcome = runner.execute_contracted_occurrence(
        contract, {}, run_root=run_root, selected_registry=selected_registry,
        live_observer=C0045LiveObserverBinding(request_for_process),
    )
    assert len(guest_commands) == 2 and sample_count == 2
    assert outcome.invocation.executor_completed
    assert len(outcome.observation_references) == 1
    assert outcome.observations[0].passed is (after_ticks == 20)
    assert [fact.name for fact in outcome.authorizing_facts] == (
        ["compute:bounded_guest_cpu"] if after_ticks == 20 else []
    )
    assert all(fact.scope.locus == "target" for fact in outcome.authorizing_facts)
