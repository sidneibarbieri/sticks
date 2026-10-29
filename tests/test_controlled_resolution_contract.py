"""A simulated registration or local lookup does not establish a C2 channel."""

import subprocess

import pytest

from executors import executor_registry as executors
from executors.registry_initializer import initialize_registry
from loaders.campaign_loader import load_campaign


def test_c0026_registration_cannot_authorize_a_controlled_action():
    initialize_registry()
    metadata = executors.registry.get_metadata("T1583.001", "0.c0026")
    assert metadata.produces == ["simulation:domain_registration_recorded"]
    resolution = executors.registry.get_metadata("T1568", "0.c0026")
    assert resolution.requires == ["network:ssh_available"]
    assert resolution.produces == ["discovery:lab_domain_resolved"]


def test_c0026_loaded_plan_has_no_fictitious_c2_dependency():
    campaign = load_campaign("0.c0026")
    registration, resolution, transfer = campaign.steps[:3]
    assert registration.produces == ["simulation:domain_registration_recorded"]
    assert resolution.requires == ["network:ssh_available"]
    assert resolution.produces == ["discovery:lab_domain_resolved"]
    assert transfer.requires == []


def test_simulated_link_can_consume_only_the_simulated_registration():
    initialize_registry()
    metadata = executors.registry.get_metadata("T1566.002")
    assert metadata.requires == ["simulation:domain_registration_recorded"]


def test_controlled_resolution_executes_on_target_without_host_fallback(monkeypatch):
    def target_transport(**arguments):
        assert arguments["sut_profile_id"] == "0.c0026"
        return subprocess.CompletedProcess(["guest"], 0, "127.0.0.1 c2.dynamic.local\n", "")

    monkeypatch.setattr(executors, "run_bash_on_target_vm", target_transport)
    monkeypatch.setattr(executors, "_try_run_on_target_vm", lambda **arguments: (None, "No target"))
    monkeypatch.setattr(executors.subprocess, "run", lambda *arguments, **options: pytest.fail("Controller fallback invoked"))
    result = executors.execute_t1568_real("0.c0026", "0.c0026")
    assert result[0] is True
    assert "127.0.0.1 c2.dynamic.local" in result[1]
    assert result[3] == ["target-vm:/tmp/sticks_dynamic_resolution.txt"]


@pytest.mark.parametrize("failure", [
    subprocess.CalledProcessError(7, ["guest"], "partial", "resolution failed"),
    FileNotFoundError("Target VM missing"),
])
def test_controlled_resolution_preserves_original_transport_failure(monkeypatch, failure):
    def broken_transport(**arguments):
        raise failure

    monkeypatch.setattr(executors, "run_bash_on_target_vm", broken_transport)
    monkeypatch.setattr(executors, "_try_run_on_target_vm", lambda **arguments: (None, "No target"))
    monkeypatch.setattr(executors.subprocess, "run", lambda *arguments, **options: pytest.fail("Controller fallback invoked"))
    with pytest.raises(type(failure)) as observed:
        executors.execute_t1568_real("0.c0026", "0.c0026")
    assert observed.value is failure


def test_failed_guest_resolution_does_not_return_success(monkeypatch):
    failed = subprocess.CompletedProcess(["guest"], 8, "partial", "getent failed")
    monkeypatch.setattr(executors, "run_bash_on_target_vm", lambda **arguments: failed)
    monkeypatch.setattr(executors, "_try_run_on_target_vm", lambda **arguments: (None, "No target"))
    monkeypatch.setattr(executors.subprocess, "run", lambda *arguments, **options: pytest.fail("Controller fallback invoked"))
    with pytest.raises(subprocess.CalledProcessError) as observed:
        executors.execute_t1568_real("0.c0026", "0.c0026")
    assert observed.value.returncode == 8
    assert observed.value.stderr == "getent failed"
