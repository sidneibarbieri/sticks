"""C0026 procedures must use the declared guest account without host fallback."""

import subprocess

import pytest

from executors import executor_registry as executors


@pytest.mark.parametrize(
    "execute,artifact",
    [
        (executors.execute_t1568_real, "target-vm:/tmp/sticks_dynamic_resolution.txt"),
        (executors.execute_t1105_real, "target-vm:/tmp/sticks_downloaded_payload.sh"),
    ],
)
def test_c0026_guest_action_uses_declared_principal(monkeypatch, execute, artifact):
    def transport(**arguments):
        assert arguments["sut_profile_id"] == "0.c0026"
        assert arguments["execution_user"] == "ubuntu"
        return subprocess.CompletedProcess(["guest"], 0, "guest evidence", "")

    monkeypatch.setattr(executors, "run_bash_on_target_vm", transport)
    monkeypatch.setattr(
        executors,
        "_try_run_on_target_vm",
        lambda **kwargs: pytest.fail("Fallback transport invoked"),
    )
    result = execute("0.c0026", "0.c0026")
    assert result[0] is True
    assert "guest evidence" in result[1]
    assert result[3] == [artifact]


@pytest.mark.parametrize(
    "execute", [executors.execute_t1568_real, executors.execute_t1105_real]
)
def test_c0026_guest_transport_error_is_not_replaced_by_host_execution(
    monkeypatch, execute, tmp_path
):
    failure = FileNotFoundError("guest unavailable")

    def broken(**kwargs):
        raise failure

    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(executors, "run_bash_on_target_vm", broken)
    monkeypatch.setattr(
        executors,
        "_try_run_on_target_vm",
        lambda **kwargs: pytest.fail("Fallback transport invoked"),
    )
    with pytest.raises(FileNotFoundError) as observed:
        execute("0.c0026", "0.c0026")
    assert observed.value is failure
    assert list(tmp_path.iterdir()) == []


def test_c0026_guest_transfer_nonzero_exit_retains_error(monkeypatch, tmp_path):
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(
        executors,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess(
            ["guest"], 17, "partial", "transfer failed"
        ),
    )
    monkeypatch.setattr(
        executors,
        "_try_run_on_target_vm",
        lambda **kwargs: pytest.fail("Fallback transport invoked"),
    )
    with pytest.raises(subprocess.CalledProcessError) as observed:
        executors.execute_t1105_real("0.c0026", "0.c0026")
    assert observed.value.returncode == 17
    assert observed.value.stderr == "transfer failed"
    assert list(tmp_path.iterdir()) == []
