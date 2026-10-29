import hashlib
import json
import subprocess

import pytest
from pydantic import ValidationError
import yaml

from scripts import observe_controlled_target as observer_cli

from validators.controlled_target_observer import (
    FixtureDeclaration,
    TargetObservation,
    validate_observation,
)


def declared_fixture():
    return FixtureDeclaration(
        path="/home/analyst/.mozilla/profiles.ini",
        content="controlled browser fixture",
        owner="analyst",
        permissions="644",
    )


def observation_payload():
    fixture = declared_fixture()
    return {
        "hostname": "target-linux-1",
        "boot_id": "controlled-boot",
        "files": [{
            "path": fixture.path,
            "sha256": hashlib.sha256(fixture.content.encode()).hexdigest(),
            "owner": fixture.owner,
            "mode": "644",
            "owner_read_exit_code": 0,
        }],
        "payload_sha256": hashlib.sha256(
            b"#!/bin/sh\necho STICKS benign payload\n"
        ).hexdigest(),
        "server_log": '127.0.0.1 "GET /payload.sh HTTP/1.1" 200 -',
        "mac_addresses": {"eth0": "52:54:00:35:54:10", "eth1": "52:54:00:12:34:10"},
    }


def validate(payload, report="[identity] analyst\n/home/analyst/.mozilla/profiles.ini\n"):
    return validate_observation(
        [declared_fixture()], TargetObservation.model_validate(payload), report
    )


def test_complete_observation_passes():
    assert validate(observation_payload()) == []


def test_missing_declared_fixture_is_not_vacuous_success():
    payload = observation_payload()
    payload["files"] = []
    assert "fixture_set_mismatch" in validate(payload)


def test_duplicate_observation_is_rejected():
    payload = observation_payload()
    payload["files"] *= 2
    assert "duplicate_observed_path" in validate(payload)


@pytest.mark.parametrize("field,value", [
    ("sha256", "0" * 64), ("owner", "root"), ("mode", "600"),
    ("owner_read_exit_code", 1),
])
def test_fixture_tampering_is_rejected(field, value):
    payload = observation_payload()
    payload["files"][0][field] = value
    assert validate(payload)


@pytest.mark.parametrize("report", [
    "[identity] root\n/home/analyst/.mozilla/profiles.ini\n",
    "[identity] analyst\nmissing\n",
    "[identity] analyst-other\n/home/analyst/.mozilla/profiles.ini\n",
])
def test_browser_report_requires_exact_identity_and_declared_paths(report):
    assert validate(observation_payload(), report)


def test_numeric_mac_is_rejected_by_schema():
    payload = observation_payload()
    payload["mac_addresses"]["eth0"] = 41135169250
    with pytest.raises(ValidationError):
        TargetObservation.model_validate(payload)


def test_empty_network_is_rejected():
    payload = observation_payload()
    payload["mac_addresses"] = {}
    assert "network_mac_observation_incomplete" in validate(payload)


@pytest.mark.parametrize("field", ["payload_sha256", "server_log"])
def test_transfer_requires_payload_and_server_observation(field):
    payload = observation_payload()
    payload[field] = ""
    assert "controlled_loopback_transfer_mismatch" in validate(payload)


def test_empty_declaration_is_rejected():
    with pytest.raises(ValueError, match="nonempty"):
        validate_observation([], TargetObservation.model_validate(observation_payload()), "")


def test_duplicate_declaration_is_rejected():
    with pytest.raises(ValueError, match="unique"):
        validate_observation(
            [declared_fixture(), declared_fixture()],
            TargetObservation.model_validate(observation_payload()), "",
        )


def invoke_cli(tmp_path, monkeypatch, payload, exit_code=0):
    workspace = tmp_path / "workspace"
    profile = workspace / "data/sut_profiles/controlled.yml"
    profile.parent.mkdir(parents=True)
    profile.write_text(yaml.safe_dump({
        "sut_configuration": {"target-base": {"files": [declared_fixture().model_dump()]}}
    }))
    target = workspace / "lab/vagrant/target-linux-1"
    target.mkdir(parents=True)
    (workspace / "browser.txt").write_text(
        "[identity] analyst\n/home/analyst/.mozilla/profiles.ini\n"
    )
    output = tmp_path / "observation.json"

    def run_probe(command, **kwargs):
        assert kwargs["cwd"] == target
        assert kwargs["env"]["VAGRANT_DEFAULT_PROVIDER"] == "qemu"
        assert "controlled browser fixture" not in command[-1]
        return subprocess.CompletedProcess(command, exit_code, json.dumps(payload), "")

    monkeypatch.setattr(observer_cli.subprocess, "run", run_probe)
    monkeypatch.setattr(observer_cli.sys, "argv", [
        "observe_controlled_target.py", "--workspace", str(workspace),
        "--campaign", "controlled", "--browser-report", "browser.txt",
        "--output", str(output),
    ])
    return output


def test_cli_records_hash_bound_observation(tmp_path, monkeypatch):
    output = invoke_cli(tmp_path, monkeypatch, observation_payload())
    assert observer_cli.main() == 0
    receipt = json.loads(output.read_text())
    assert receipt["passed"] is True
    for field in ("profile_sha256", "browser_report_sha256", "probe_sha256",
                  "validator_sha256", "cli_sha256"):
        assert len(receipt[field]) == 64
    assert output.with_suffix(".json.transport.json").is_file()
    with pytest.raises(FileExistsError):
        observer_cli.main()


def test_cli_preserves_failed_transport_without_success_receipt(tmp_path, monkeypatch):
    output = invoke_cli(tmp_path, monkeypatch, {}, exit_code=7)
    with pytest.raises(RuntimeError, match="Guest observation failed"):
        observer_cli.main()
    assert not output.exists()
    raw = json.loads(output.with_suffix(".json.transport.json").read_text())
    assert raw["transport_exit_code"] == 7


def test_cli_preserves_malformed_observation_without_success_receipt(tmp_path, monkeypatch):
    output = invoke_cli(tmp_path, monkeypatch, {})
    with pytest.raises(ValidationError):
        observer_cli.main()
    assert not output.exists()
    assert output.with_suffix(".json.transport.json").is_file()


def test_cli_rejects_profile_mutation_during_observation(tmp_path, monkeypatch):
    output = invoke_cli(tmp_path, monkeypatch, observation_payload())
    profile = tmp_path / "workspace/data/sut_profiles/controlled.yml"
    original_digest = hashlib.sha256(profile.read_bytes()).hexdigest()
    transport = observer_cli.subprocess.run

    def mutate_profile(command, **kwargs):
        profile.write_text("sut_configuration: {}\n")
        return transport(command, **kwargs)

    monkeypatch.setattr(observer_cli.subprocess, "run", mutate_profile)
    with pytest.raises(RuntimeError, match="Observer inputs changed"):
        observer_cli.main()
    assert not output.exists()
    receipt = json.loads(output.with_suffix(".json.transport.json").read_text())
    assert receipt["profile_sha256"] == original_digest
    assert receipt["changed_inputs"] == ["profile_sha256"]


def test_cli_rejects_browser_mutation_during_observation(tmp_path, monkeypatch):
    output = invoke_cli(tmp_path, monkeypatch, observation_payload())
    browser_report = tmp_path / "workspace/browser.txt"
    original_digest = hashlib.sha256(browser_report.read_bytes()).hexdigest()
    transport = observer_cli.subprocess.run

    def mutate_browser(command, **kwargs):
        browser_report.write_text("[identity] root\n")
        return transport(command, **kwargs)

    monkeypatch.setattr(observer_cli.subprocess, "run", mutate_browser)
    with pytest.raises(RuntimeError, match="Observer inputs changed"):
        observer_cli.main()
    assert not output.exists()
    receipt = json.loads(output.with_suffix(".json.transport.json").read_text())
    assert receipt["browser_report_sha256"] == original_digest
    assert receipt["changed_inputs"] == ["browser_report_sha256"]
