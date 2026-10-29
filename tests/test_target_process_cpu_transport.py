"""Guest CPU transport accepts only a scoped, structured observation."""

import json
import subprocess

import pytest

from runners.capability_facts import FactScope
from runners.target_process_cpu_transport import (
    TargetCpuSampleRequest,
    collect_guest_cpu_sample,
)


@pytest.fixture
def cpu_request() -> TargetCpuSampleRequest:
    return TargetCpuSampleRequest(
        sut_profile_id="0.shadowray",
        scope=FactScope(
            run_id="run-1", environment_id="environment-1", epoch="boot-1",
            locus="target", host_id="target-1", principal="rayuser"
        ),
        process_id=123,
        nonce="nonce-1",
        command_sha256="a" * 64,
    )


def reply(**changes: object) -> subprocess.CompletedProcess[str]:
    values = {
        "nonce": "nonce-1",
        "process_id": 123,
        "process_start_ticks": 400,
        "process_command_sha256": "a" * 64,
        "monotonic_ns": 1000,
        "user_cpu_ticks": 20,
        "system_cpu_ticks": 2,
        "boot_id": "boot-1",
        "hostname": "target-1",
        "principal": "rayuser",
    }
    values.update(changes)
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=json.dumps(values), stderr="")


def test_guest_reply_yields_measurement_without_granting_fact(
    cpu_request: TargetCpuSampleRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "runners.target_process_cpu_transport._check_profile_principal",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "runners.target_process_cpu_transport.run_bash_on_target_vm",
        lambda *args, **kwargs: reply(),
    )

    sample = collect_guest_cpu_sample(cpu_request)

    assert sample.scope == cpu_request.scope
    assert sample.user_cpu_ticks == 20
    assert not hasattr(sample, "established_facts")


@pytest.mark.parametrize("change", ({"nonce": "other"}, {"boot_id": "other"},
                                    {"hostname": "other"}, {"principal": "root"},
                                    {"process_command_sha256": "b" * 64}))
def test_mismatched_guest_reply_fails_closed(
    cpu_request: TargetCpuSampleRequest, monkeypatch: pytest.MonkeyPatch, change: dict
) -> None:
    monkeypatch.setattr(
        "runners.target_process_cpu_transport._check_profile_principal",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "runners.target_process_cpu_transport.run_bash_on_target_vm",
        lambda *args, **kwargs: reply(**change),
    )

    with pytest.raises(ValueError, match="selected scope"):
        collect_guest_cpu_sample(cpu_request)


def test_guest_transport_failure_is_not_a_negative_sample(
    cpu_request: TargetCpuSampleRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "runners.target_process_cpu_transport._check_profile_principal",
        lambda *args: None,
    )
    monkeypatch.setattr(
        "runners.target_process_cpu_transport.run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="probe failed"
        ),
    )

    with pytest.raises(RuntimeError, match="no sample"):
        collect_guest_cpu_sample(cpu_request)
