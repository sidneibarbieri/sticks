"""C0045 authority replays guest counters before granting a bounded fact."""

from pathlib import Path
import hashlib
import json

import pytest

from executors.c0045_compute_command import build_c0045_compute_command
from runners.c0045_compute_observer import C0045ComputeRequest
from runners.capability_authority import (
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import FactScope
from runners.capability_store import CapabilityStore
from runners.target_compute_predicate import TargetProcessCpuSample
from runners.target_process_cpu_transport import (
    GuestCpuAcquisition, TargetCpuSampleRequest, _PROBE_PATH,
)


def make_acquisition(
    request: TargetCpuSampleRequest, monotonic_ns: int, cpu_ticks: int
) -> GuestCpuAcquisition:
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


def compute_request() -> C0045ComputeRequest:
    nonce = "c0045prospective01"
    selected = build_c0045_compute_command(nonce)
    return C0045ComputeRequest(
        sut_profile_id="0.shadowray",
        scope=FactScope(
            run_id="run-c0045", environment_id="lab-c0045", epoch="boot-c0045",
            locus="target", host_id="target-linux-1", principal="rayuser",
        ),
        nonce=nonce,
        producer_occurrence=10,
        process_id=123,
        command_sha256=selected.expected_command_sha256,
    )


@pytest.mark.parametrize("after_ticks", (12, 20))
def test_registered_compute_observer_grants_only_replayed_positive_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, after_ticks: int
) -> None:
    request = compute_request()
    sample_request = TargetCpuSampleRequest(
        sut_profile_id=request.sut_profile_id, scope=request.scope,
        process_id=request.process_id, nonce=request.nonce,
        command_sha256=request.command_sha256,
    )
    acquisitions = iter((
        make_acquisition(sample_request, 1000, 10),
        make_acquisition(sample_request, 2000, after_ticks),
    ))
    monkeypatch.setattr(
        "runners.target_cpu_measurement.acquire_guest_cpu_sample",
        lambda _request: next(acquisitions),
    )
    monkeypatch.setattr("runners.target_cpu_measurement.time.sleep", lambda _: None)

    reference = acquire_registered_observation(
        "c0045-compute", request, run_root=tmp_path
    )
    observed = verify_registered_observation(
        reference, run_root=tmp_path, expected_scope=request.scope,
        expected_predicate="bounded-guest-cpu",
    )
    assert observed.passed is (after_ticks == 20)
    assert observed.established_facts == (
        ("compute:bounded_guest_cpu",) if observed.passed else ()
    )
    facts = CapabilityStore().add_observed(
        reference, run_root=tmp_path, expected_scope=request.scope,
        expected_predicate="bounded-guest-cpu",
    )
    assert len(facts) == int(observed.passed)

    nested = observed.details["measurement_reference"]
    from runners.capability_facts import ObservationReference

    measurement_reference = ObservationReference.model_validate_json(nested)
    record = tmp_path / measurement_reference.record_path
    record.write_bytes(record.read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest differs"):
        verify_registered_observation(
            reference, run_root=tmp_path, expected_scope=request.scope,
            expected_predicate="bounded-guest-cpu",
        )


def test_compute_request_rejects_unselected_command() -> None:
    request = compute_request()
    with pytest.raises(ValueError, match="frozen study"):
        C0045ComputeRequest.model_validate({
            **request.model_dump(mode="python"), "command_sha256": "a" * 64,
        })
