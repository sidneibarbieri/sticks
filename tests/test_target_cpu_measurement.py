"""Retained CPU samples stay measurements and detect receipt tampering."""

import hashlib
import json
from pathlib import Path

import pytest

from runners.capability_facts import FactScope
from runners.capability_observations import verify_observation_reference
from runners.target_compute_predicate import TargetProcessCpuSample
from runners.target_cpu_measurement import (
    measure_and_retain_target_cpu,
    verify_retained_cpu_measurement,
)
from runners.target_process_cpu_transport import (
    GuestCpuAcquisition,
    TargetCpuSampleRequest,
    _PROBE_PATH,
)


def make_request() -> TargetCpuSampleRequest:
    return TargetCpuSampleRequest(
        sut_profile_id="0.shadowray",
        scope=FactScope(
            run_id="run-1", environment_id="lab-1", epoch="boot-1",
            locus="target", host_id="target-linux-1", principal="rayuser"
        ),
        process_id=123,
        nonce="run-nonce",
        command_sha256="a" * 64,
    )


def make_acquisition(
    request: TargetCpuSampleRequest, monotonic_ns: int, cpu_ticks: int
) -> GuestCpuAcquisition:
    sample = TargetProcessCpuSample(
        scope=request.scope,
        process_id=request.process_id,
        process_start_ticks=400,
        process_command_sha256=request.command_sha256,
        monotonic_ns=monotonic_ns,
        user_cpu_ticks=cpu_ticks,
        system_cpu_ticks=2,
    )
    reply = {
        "nonce": request.nonce,
        "boot_id": request.scope.epoch,
        "hostname": request.scope.host_id,
        "principal": request.scope.principal,
        "process_id": request.process_id,
        "process_start_ticks": sample.process_start_ticks,
        "process_command_sha256": request.command_sha256,
        "monotonic_ns": monotonic_ns,
        "user_cpu_ticks": cpu_ticks,
        "system_cpu_ticks": sample.system_cpu_ticks,
    }
    return GuestCpuAcquisition(
        sample=sample,
        reply_json=json.dumps(reply),
        probe_source_sha256=hashlib.sha256(_PROBE_PATH.read_bytes()).hexdigest(),
    )


@pytest.mark.parametrize(
    ("after_ticks", "expected_passed"), ((20, True), (10, False))
)
def test_measurement_retains_replies_without_authorizing_fact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    after_ticks: int,
    expected_passed: bool,
) -> None:
    request = make_request()
    acquisitions = iter(
        (make_acquisition(request, 1000, 10),
         make_acquisition(request, 2000, after_ticks))
    )
    monkeypatch.setattr(
        "runners.target_cpu_measurement.acquire_guest_cpu_sample",
        lambda _request: next(acquisitions),
    )
    monkeypatch.setattr("runners.target_cpu_measurement.time.sleep", lambda _: None)

    result = measure_and_retain_target_cpu(request, run_root=tmp_path)
    retained = verify_observation_reference(
        result.reference,
        run_root=tmp_path,
        expected_scope=request.scope,
        expected_predicate="target-cpu-delta-measurement",
    )

    assert result.verdict.passed is expected_passed
    assert retained.passed is expected_passed
    assert retained.established_facts == ()
    assert retained.producer_occurrence is None
    assert retained.details["before_reply_json"] != retained.details["after_reply_json"]
    replayed = verify_retained_cpu_measurement(
        result.reference, run_root=tmp_path, expected_scope=request.scope
    )
    assert replayed == result.verdict

    record = tmp_path / result.reference.record_path
    record.write_bytes(record.read_bytes() + b" ")
    with pytest.raises(ValueError, match="digest differs"):
        verify_observation_reference(
            result.reference,
            run_root=tmp_path,
            expected_scope=request.scope,
            expected_predicate="target-cpu-delta-measurement",
        )


def test_source_change_fails_before_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = make_request()
    before = make_acquisition(request, 1000, 10)
    after = make_acquisition(request, 2000, 20).model_copy(
        update={"probe_source_sha256": "c" * 64}
    )
    acquisitions = iter((before, after))
    monkeypatch.setattr(
        "runners.target_cpu_measurement.acquire_guest_cpu_sample",
        lambda _request: next(acquisitions),
    )
    monkeypatch.setattr("runners.target_cpu_measurement.time.sleep", lambda _: None)

    with pytest.raises(ValueError, match="source changed"):
        measure_and_retain_target_cpu(request, run_root=tmp_path)
    assert list(tmp_path.iterdir()) == []
