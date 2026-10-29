"""C0010 transfer evidence must come from its target guest."""

import subprocess

import pytest

from executors import executor_registry as executors


def reject_host_fallback(**kwargs):
    pytest.fail("Host fallback invoked for C0010")


def test_c0010_transfer_uses_declared_guest(monkeypatch):
    def transport(**arguments):
        assert arguments["sut_profile_id"] == "0.c0010"
        assert arguments["execution_user"] == "ubuntu"
        return subprocess.CompletedProcess(["guest"], 0, "guest transfer", "")

    monkeypatch.setattr(executors, "run_bash_on_target_vm", transport)
    monkeypatch.setattr(executors, "_try_run_on_target_vm", reject_host_fallback)

    success, stdout, stderr, artifacts = executors.execute_t1105_real(
        "0.c0010", "0.c0010"
    )

    assert success is True
    assert "guest transfer" in stdout
    assert stderr == ""
    assert artifacts == ["target-vm:/tmp/sticks_downloaded_payload.sh"]


def test_c0010_guest_transport_error_is_not_replaced(monkeypatch, tmp_path):
    failure = FileNotFoundError("target guest unavailable")

    def transport(**kwargs):
        raise failure

    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(executors, "run_bash_on_target_vm", transport)
    monkeypatch.setattr(executors, "_try_run_on_target_vm", reject_host_fallback)

    with pytest.raises(FileNotFoundError) as observed:
        executors.execute_t1105_real("0.c0010", "0.c0010")

    assert observed.value is failure
    assert list(tmp_path.iterdir()) == []


def test_c0010_guest_transfer_nonzero_exit_retains_error(monkeypatch, tmp_path):
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(
        executors,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess(
            ["guest"], 17, "partial", "transfer failed"
        ),
    )
    monkeypatch.setattr(executors, "_try_run_on_target_vm", reject_host_fallback)

    with pytest.raises(subprocess.CalledProcessError) as observed:
        executors.execute_t1105_real("0.c0010", "0.c0010")

    assert observed.value.returncode == 17
    assert observed.value.stderr == "transfer failed"
    assert list(tmp_path.iterdir()) == []
