"""C0026 adapters bind independently measured effects to the guest scope."""

import json
import subprocess
import shlex

import pytest
from pydantic import ValidationError

from runners.capability_facts import FactScope
from runners.c0026_capability_observers import (
    C0026EffectRequest,
    observe_c0026_effect,
    _guest_script,
    _PROBE_PATH,
)
from runners.capability_authority import (
    acquire_registered_observation,
    verify_registered_observation,
)


def request(predicate="collection-bytes"):
    return C0026EffectRequest(
        sut_profile_id="0.c0026",
        nonce="nonce-a",
        predicate_id=predicate,
        scope=FactScope(
            run_id="run-a",
            environment_id="lab-a",
            epoch="boot-a",
            locus="target",
            host_id="target-linux-1",
            principal="ubuntu",
        ),
    )


def reply(monkeypatch, acquired, **changes):
    def probe(profile_id, script, **kwargs):
        assert profile_id == "0.c0026"
        assert kwargs["execution_user"] == "ubuntu"
        payload = dict(
            hostname="target-linux-1",
            principal="ubuntu",
            boot_id="boot-a",
            nonce="nonce-a",
            predicate_id=acquired.predicate_id,
            passed=True,
        )
        return subprocess.CompletedProcess(
            ["probe"], 0, json.dumps(payload | changes), ""
        )

    monkeypatch.setattr(
        "runners.c0026_capability_observers.run_bash_on_target_vm", probe
    )


@pytest.mark.parametrize(
    "predicate,product",
    [
        ("collection-bytes", "collection:verified"),
        ("archive-member", "archive:verified"),
        ("archive-chunks", "chunks:verified"),
        ("benign-payload", "payload:verified"),
    ],
)
def test_adapter_establishes_only_its_measured_product(monkeypatch, predicate, product):
    acquired = request(predicate)
    reply(monkeypatch, acquired)
    result = observe_c0026_effect(acquired)
    assert result.passed
    assert result.established_facts == (product,)


@pytest.mark.parametrize(
    "changes",
    [
        {"principal": "vagrant"},
        {"boot_id": "old"},
        {"hostname": "other"},
        {"nonce": "other"},
        {"passed": False},
    ],
)
def test_failed_or_wrong_scope_effect_grants_nothing(monkeypatch, changes):
    acquired = request()
    reply(monkeypatch, acquired, **changes)
    result = observe_c0026_effect(acquired)
    assert not result.passed
    assert result.established_facts == ()


def test_registered_effect_acquisition_can_be_verified(monkeypatch, tmp_path):
    acquired = request()
    reply(monkeypatch, acquired)
    reference = acquire_registered_observation(
        "c0026-collection", acquired, run_root=tmp_path
    )
    result = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=acquired.scope,
        expected_predicate="collection-bytes",
    )
    assert result.established_facts == ("collection:verified",)


def test_registry_refuses_predicate_for_another_authority_before_probe(tmp_path):
    with pytest.raises(ValueError):
        acquire_registered_observation(
            "c0026-collection", request("archive-member"), run_root=tmp_path
        )
    assert list(tmp_path.iterdir()) == []


def test_arbitrary_proposer_predicate_is_not_loadable():
    with pytest.raises(ValidationError):
        request("proposer.callback")


def test_resolution_adapter_retains_negative_control_measurements(
    monkeypatch, tmp_path
):
    acquired = request("files-resolution")
    measurements = {
        "hosts_mapping": True,
        "positive_returncode": 0,
        "positive_stdout": "127.0.0.1 c2.dynamic.local\n",
        "positive_stderr": "",
        "negative_returncode": 2,
        "negative_stdout": "",
        "negative_stderr": "",
        "negative_name": "absent-e0f5d528756fc4ff0893.invalid",
        "passed": True,
    }
    reply(monkeypatch, acquired, measurements=measurements)
    reference = acquire_registered_observation(
        "c0026-resolution", acquired, run_root=tmp_path
    )
    result = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=acquired.scope,
        expected_predicate="files-resolution",
    )
    assert result.established_facts == ("resolution:files_verified",)
    assert result.details["nss_negative_returncode"] == 2
    assert result.details["nss_positive_stdout"] == "127.0.0.1 c2.dynamic.local\n"


def test_resolution_claim_without_negative_control_is_not_authority(monkeypatch):
    acquired = request("files-resolution")
    reply(monkeypatch, acquired)
    result = observe_c0026_effect(acquired)
    assert not result.passed
    assert result.established_facts == ()


def test_assembled_guest_code_executes_shared_predicate_with_literal_nonce(tmp_path):
    target = tmp_path / "tmp/sticks_downloaded_payload.sh"
    target.parent.mkdir()
    target.write_bytes(b"#!/bin/sh\necho STICKS benign payload\n")
    acquired = C0026EffectRequest(
        **(request("benign-payload").model_dump() | {"nonce": "a' \" $() \\ ;"})
    )
    command = shlex.split(
        _guest_script(acquired, _PROBE_PATH.read_text(encoding="utf-8"))
    )
    command[2] = command[2].replace(
        "pathlib.Path('/')", f"pathlib.Path({str(tmp_path)!r})"
    )
    boot_file = tmp_path / "boot-id"
    boot_file.write_text("fixture-boot", encoding="utf-8")
    command[2] = command[2].replace(
        "pathlib.Path('/proc/sys/kernel/random/boot_id')",
        f"pathlib.Path({str(boot_file)!r})",
    )
    completed = subprocess.run(
        command, capture_output=True, text=True, check=False, timeout=10
    )
    assert completed.returncode == 0, completed.stderr
    measured = json.loads(completed.stdout)
    assert measured["passed"] is True
    assert measured["nonce"] == acquired.nonce
    target.write_bytes(b"wrong payload")
    failed = subprocess.run(
        command, capture_output=True, text=True, check=True, timeout=10
    )
    assert json.loads(failed.stdout)["passed"] is False
