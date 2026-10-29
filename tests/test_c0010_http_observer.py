"""A separate live probe must observe C0010's controller-local HTTP fetch."""

import os
import hashlib
from pathlib import Path

import pytest
from pydantic import ValidationError

from executors import legacy_campaign_executors as executors
from runners.c0010_http_observer import (
    C0010HttpRequest,
    _EXPECTED_BODIES,
    observe_c0010_http,
)
from runners.capability_authority import (
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import FactScope, ObservationReference
from scripts.probe_c0010_http import _EXPECTED_BODIES as PROBE_EXPECTED_BODIES


def _scope() -> FactScope:
    return FactScope(
        run_id="run-c0010-http",
        environment_id="lab-c0010-http",
        epoch="run-c0010-http",
        locus="controller",
        host_id="controller",
        principal=str(os.geteuid()),
    )


def _request(port: int) -> C0010HttpRequest:
    return C0010HttpRequest(
        sut_profile_id="0.c0010",
        scope=_scope(),
        nonce="nonce-c0010-http",
        producer_occurrence=4,
        port=port,
    )


def test_live_observer_acquires_fact_before_server_teardown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    executors.execute_t1608_004_real("0.c0010", "0.c0010")
    retained: list[ObservationReference] = []

    def observe(port: int) -> bool:
        request = _request(port)
        reference = acquire_registered_observation(
            "c0010-http", request, run_root=tmp_path
        )
        retained.append(reference)
        result = verify_registered_observation(
            reference,
            run_root=tmp_path,
            expected_scope=request.scope,
            expected_predicate="loopback-http-fetch",
        )
        return result.passed

    success, _, _, artifacts = executors.execute_t1189_real(
        "0.c0010", "0.c0010", live_observer=observe
    )

    assert success
    assert len(retained) == 1
    assert artifacts == [str(tmp_path / "0.c0010_drive_by_visit.log")]
    observed = verify_registered_observation(
        retained[0],
        run_root=tmp_path,
        expected_scope=_scope(),
        expected_predicate="loopback-http-fetch",
    )
    assert observed.established_facts == ("controller:watering_hole_fetched",)
    assert observed.producer_occurrence == 4


def test_failed_live_observer_prevents_success_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    executors.execute_t1608_004_real("0.c0010", "0.c0010")

    with pytest.raises(RuntimeError, match="did not pass"):
        executors.execute_t1189_real(
            "0.c0010", "0.c0010", live_observer=lambda port: False
        )

    assert not (tmp_path / "0.c0010_drive_by_visit.log").exists()


def test_closed_port_grants_no_http_fact() -> None:
    observed = observe_c0010_http(_request(1))

    assert not observed.passed
    assert observed.established_facts == ()
    assert observed.details["returncode"] != 0


def test_wrong_http_occurrence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        C0010HttpRequest(
            sut_profile_id="0.c0010",
            scope=_scope(),
            nonce="nonce-c0010-http",
            producer_occurrence=3,
            port=8080,
        )


def test_http_probe_and_adapter_expectations_remain_in_sync() -> None:
    assert set(_EXPECTED_BODIES) == set(PROBE_EXPECTED_BODIES)
    for path, expected in _EXPECTED_BODIES.items():
        assert expected.size == len(PROBE_EXPECTED_BODIES[path])
        assert (
            expected.sha256 == hashlib.sha256(PROBE_EXPECTED_BODIES[path]).hexdigest()
        )
