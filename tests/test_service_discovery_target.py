"""Service discovery must inspect the declared SUT, not the controller."""

import subprocess

import pytest

from executors import fox_kitten_real


def test_service_discovery_uses_target_transport_and_retains_output(monkeypatch, tmp_path):
    observed = []

    def target_transport(**arguments):
        observed.append(arguments)
        return subprocess.CompletedProcess([], 0, "LISTEN target-only:22\n", "")

    monkeypatch.setattr(fox_kitten_real, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(fox_kitten_real, "run_bash_on_target_vm", target_transport)
    success, output, error, artifacts = fox_kitten_real.execute_t1046_real(
        "0.costaricto", "0.costaricto",
    )
    assert observed and observed[0]["sut_profile_id"] == "0.costaricto"
    assert "set -euo pipefail" in observed[0]["bash_script"]
    assert "ss -tlnp" in observed[0]["bash_script"]
    assert "ss -ulnp" in observed[0]["bash_script"]
    assert success is True and error == ""
    assert "target VM" in output
    assert len(artifacts) == 1
    assert (tmp_path / "0.costaricto_service_discovery.txt").read_text() == "LISTEN target-only:22\n"


def test_failed_guest_service_command_propagates_original_error(monkeypatch, tmp_path):
    monkeypatch.setattr(fox_kitten_real, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(fox_kitten_real, "run_bash_on_target_vm", lambda **arguments:
                        subprocess.CompletedProcess(["guest-enumeration"], 7, "partial\n", "guest failure"))
    with pytest.raises(subprocess.CalledProcessError) as failure:
        fox_kitten_real.execute_t1046_real("0.costaricto", "0.costaricto")
    assert failure.value.returncode == 7
    assert failure.value.stderr == "guest failure"
    assert (tmp_path / "0.costaricto_service_discovery.txt").read_text() == "partial\n"


def test_service_discovery_transport_error_is_not_masked(monkeypatch):
    def broken_transport(**arguments):
        raise RuntimeError("transport programming error")

    monkeypatch.setattr(fox_kitten_real, "run_bash_on_target_vm", broken_transport)
    with pytest.raises(RuntimeError, match="transport programming error"):
        fox_kitten_real.execute_t1046_real("0.costaricto", "0.costaricto")
