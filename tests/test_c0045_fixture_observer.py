"""Occurrence and identity boundaries for retained C0045 fixtures."""

import importlib
import importlib.util
import json
import subprocess

import pytest
from pydantic import ValidationError

from runners.capability_facts import FactScope


def observer_module():
    assert importlib.util.find_spec("runners.c0045_fixture_observer") is not None
    return importlib.import_module("runners.c0045_fixture_observer")


def request(predicate="toolkit-staged", occurrence=5, **scope_changes):
    scope = dict(
        run_id="run",
        environment_id="lab",
        epoch="boot",
        locus="target",
        host_id="target-linux-1",
        principal="rayuser",
    )
    scope.update(scope_changes)
    return observer_module().C0045FixtureRequest(
        sut_profile_id="0.shadowray",
        predicate_id=predicate,
        producer_occurrence=occurrence,
        nonce="challenge",
        scope=FactScope(**scope),
    )


@pytest.mark.parametrize(
    "predicate,occurrence",
    [("toolkit-staged", 6), ("loopback-transfer", 5), ("toolkit-staged", True)],
)
def test_wrong_occurrence_is_rejected(predicate, occurrence):
    with pytest.raises(ValidationError):
        request(predicate, occurrence)


@pytest.mark.parametrize("scope", [{"principal": "root"}, {"locus": "controller"}])
def test_non_target_scope_is_rejected(scope):
    with pytest.raises(ValidationError):
        request(**scope)


def transfer_response(**changes):
    response = dict(
        hostname="target-linux-1",
        principal="rayuser",
        observer_uid=1001,
        boot_id="boot",
        nonce="challenge",
        measurement=dict(
            passed=True,
            input_sha256="924d5485379f04c5f82ade19a2d9c65709dca9a279f758d879a1f5c8e5f051d6",
            content_sha256="924d5485379f04c5f82ade19a2d9c65709dca9a279f758d879a1f5c8e5f051d6",
            target_executable=True,
            http_get_recorded=True,
            owner="rayuser",
        ),
    )
    response.update(changes)
    return response


def test_registered_transfer_rechecks_bytes_and_retains_scope(monkeypatch, tmp_path):
    module = observer_module()
    response = transfer_response()

    def transport(*args, **kwargs):
        assert kwargs["execution_user"] == "rayuser"
        return subprocess.CompletedProcess([], 0, json.dumps(response), "")

    monkeypatch.setattr(module, "run_bash_on_target_vm", transport)
    from runners.capability_authority import (
        acquire_registered_observation,
        verify_registered_observation,
    )

    selected = request("loopback-transfer", 6)
    reference = acquire_registered_observation(
        "c0045-transfer", selected, run_root=tmp_path
    )
    observed = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=selected.scope,
        expected_predicate="loopback-transfer",
    )
    assert observed.passed
    assert observed.established_facts == ("transfer:guest_loopback_verified",)
    assert observed.producer_occurrence == 6


@pytest.mark.parametrize(
    "changes",
    [
        {"boot_id": "another"},
        {"nonce": "stale"},
        {"principal": "other"},
        {"hostname": "controller"},
    ],
)
def test_identity_mismatch_cannot_grant_facts(monkeypatch, changes):
    module = observer_module()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(transfer_response(**changes)), ""
        ),
    )
    observed = module.observe_c0045_fixture(request("loopback-transfer", 6))
    assert not observed.passed
    assert not observed.established_facts


def test_claimed_success_with_wrong_bytes_is_rejected(monkeypatch):
    module = observer_module()
    response = transfer_response()
    response["measurement"]["input_sha256"] = "0" * 64
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(response), ""
        ),
    )
    assert not module.observe_c0045_fixture(request("loopback-transfer", 6)).passed


def test_transport_error_propagates(monkeypatch):
    module = observer_module()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess([], 9, "", "guest error"),
    )
    with pytest.raises(subprocess.CalledProcessError):
        module.observe_c0045_fixture(request("loopback-transfer", 6))


def toolkit_response():
    files = [
        dict(
            name="port_scanner.py",
            sha256="83a2ca4b1764db5f4456b5f5fc017be6967e1af0b256a57ca014e3d68d884c0c",
        ),
        dict(
            name="service_enum.sh",
            sha256="82debdb73005a09027938daa32a4ffb01daf21b2190160c5f1f8927ac71365bf",
        ),
        dict(
            name="sys_profiler.py",
            sha256="2259202e3c6dd7864d660be26dc9696135e54ac8962f134f2758a9c5663746c7",
        ),
    ]
    return transfer_response(
        measurement=dict(
            passed=True,
            files=[
                dict(**entry, size=100, owner="rayuser", mode="755", executable=True)
                for entry in files
            ],
        )
    )


def test_registered_toolkit_grants_staging_only(monkeypatch, tmp_path):
    module = observer_module()
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(toolkit_response()), ""
        ),
    )
    from runners.capability_authority import (
        acquire_registered_observation,
        verify_registered_observation,
    )

    selected = request()
    reference = acquire_registered_observation(
        "c0045-toolkit", selected, run_root=tmp_path
    )
    observed = verify_registered_observation(
        reference,
        run_root=tmp_path,
        expected_scope=selected.scope,
        expected_predicate="toolkit-staged",
    )
    assert observed.passed
    assert observed.established_facts == ("toolkit:declared_files_staged",)
    assert observed.producer_occurrence == 5


@pytest.mark.parametrize(
    "changes", [{"sha256": "0" * 64}, {"executable": False}, {"owner": "other"}]
)
def test_toolkit_claimed_pass_cannot_override_measurements(monkeypatch, changes):
    module = observer_module()
    response = toolkit_response()
    response["measurement"]["files"][0].update(changes)
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(response), ""
        ),
    )
    assert not module.observe_c0045_fixture(request()).passed


def test_toolkit_duplicate_names_are_rejected(monkeypatch):
    module = observer_module()
    response = toolkit_response()
    response["measurement"]["files"][1] = response["measurement"]["files"][0]
    monkeypatch.setattr(
        module,
        "run_bash_on_target_vm",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            [], 0, json.dumps(response), ""
        ),
    )
    with pytest.raises(ValidationError):
        module.observe_c0045_fixture(request())


def test_authority_cannot_dispatch_another_predicate(tmp_path):
    from runners.capability_authority import acquire_registered_observation

    with pytest.raises(ValueError, match="differs"):
        acquire_registered_observation(
            "c0045-toolkit", request("loopback-transfer", 6), run_root=tmp_path
        )


def test_embedded_probe_collects_only_declared_toolkit(monkeypatch, tmp_path):
    from pathlib import Path
    from types import SimpleNamespace

    from scripts import probe_shadowray_target as probe

    directory = tmp_path / "sticks-shadowray-toolkit"
    directory.mkdir()
    for name in ("port_scanner.py", "service_enum.sh", "sys_profiler.py"):
        (directory / name).write_text("changed fixture\n")
    boot_file = tmp_path / "boot"
    boot_file.write_text("controlled-boot\n")
    original_path = Path

    def guest_path(value):
        return {"/tmp": tmp_path, "/proc/sys/kernel/random/boot_id": boot_file}.get(
            value, original_path(value)
        )

    monkeypatch.setattr(probe, "Path", guest_path)
    monkeypatch.setattr(probe.os, "geteuid", lambda: 1001)
    monkeypatch.setattr(
        probe.pwd, "getpwuid", lambda uid: SimpleNamespace(pw_name="rayuser")
    )
    monkeypatch.setattr(probe.socket, "gethostname", lambda: "target-linux-1")
    result = probe.collect_fixture_observation("toolkit-staged", "challenge")
    parsed = observer_module().GuestFixtureResult.model_validate(result)
    assert parsed.boot_id == "controlled-boot"
    assert parsed.nonce == "challenge"
    assert not parsed.measurement.passed
    assert not (tmp_path / "sticks-shadowray-transfer").exists()
