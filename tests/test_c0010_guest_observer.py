"""C0010 guest transfer requires a scoped, passing target observation."""

import json
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from runners.c0010_guest_observer import C0010TransferRequest, observe_c0010_transfer
from runners.capability_authority import (
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import FactScope


def _request() -> C0010TransferRequest:
    return C0010TransferRequest(
        sut_profile_id="0.c0010",
        nonce="nonce-c0010",
        scope=FactScope(
            run_id="run-c0010",
            environment_id="lab-c0010",
            epoch="boot-c0010",
            locus="target",
            host_id="target-linux-1",
            principal="ubuntu",
        ),
        producer_occurrence=9,
    )


def _reply(**changes: object) -> dict:
    baseline = {
        "schema": "c0010-target-transfer-observation/v1",
        "hostname": "target-linux-1",
        "principal": "ubuntu",
        "observer_uid": 1000,
        "boot_id": "boot-c0010",
        "nonce": "nonce-c0010",
        "payload_sha256": "b088ddaef2625e7f19f1ef1031b8af0617d4e849134d367bde139c77b7ad7be9",
        "checks": {
            "declared_notice_present": True,
            "declared_page_present": True,
            "transfer_matches_source": True,
            "http_get_recorded": True,
            "download_executable": True,
        },
        "passed": True,
        "scope": "bounded target fixture",
    }
    return baseline | changes


def _mock_transport(
    monkeypatch: pytest.MonkeyPatch, reply: dict, code: int = 0
) -> None:
    def transport(profile_id: str, script: str, **kwargs: object):
        assert profile_id == "0.c0010"
        assert kwargs["execution_user"] == "ubuntu"
        assert "nonce-c0010" in script
        return subprocess.CompletedProcess(
            ["guest"], code, json.dumps(reply), "guest error"
        )

    monkeypatch.setattr("runners.c0010_guest_observer.run_bash_on_target_vm", transport)


def test_transfer_fact_requires_retained_target_observation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    request = _request()
    _mock_transport(monkeypatch, _reply())

    reference = acquire_registered_observation(
        "c0010-transfer", request, run_root=tmp_path
    )
    observed = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=request.scope,
        expected_predicate="benign-transfer",
    )

    assert observed.passed
    assert observed.established_facts == ("target:benign_payload_transferred",)
    assert observed.producer_occurrence == 9
    assert observed.content_sha256 == _reply()["payload_sha256"]


@pytest.mark.parametrize(
    "changes",
    [
        {"hostname": "controller"},
        {"principal": "root"},
        {"boot_id": "stale-boot"},
        {"nonce": "stale-nonce"},
        {"payload_sha256": "0" * 64},
        {"checks": _reply()["checks"] | {"http_get_recorded": False}},
        {"checks": _reply()["checks"] | {"unreviewed_effect": True}},
        {"passed": False},
    ],
)
def test_changed_guest_reply_grants_no_transfer(
    monkeypatch: pytest.MonkeyPatch, changes: dict
) -> None:
    _mock_transport(monkeypatch, _reply(**changes))

    observed = observe_c0010_transfer(_request())

    assert not observed.passed
    assert observed.established_facts == ()
    assert observed.content_sha256 is None


def test_nonzero_guest_probe_grants_no_transfer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mock_transport(monkeypatch, _reply(), code=17)

    observed = observe_c0010_transfer(_request())

    assert not observed.passed
    assert observed.details["returncode"] == 17
    assert observed.details["stderr"] == "guest error"


def test_unexpected_occurrence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        C0010TransferRequest(
            sut_profile_id="0.c0010",
            nonce="nonce-c0010",
            scope=_request().scope,
            producer_occurrence=8,
        )


def test_guest_scope_cannot_impersonate_controller() -> None:
    scope = _request().scope.model_copy(update={"locus": "controller"})
    with pytest.raises(ValueError, match="non-root target"):
        C0010TransferRequest(
            sut_profile_id="0.c0010",
            nonce="nonce-c0010",
            scope=scope,
            producer_occurrence=9,
        )
