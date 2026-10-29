"""C0026 guest failures must remain failures from the selected guest."""

import subprocess

import pytest

from executors import executor_registry


@pytest.mark.parametrize(
    "executor",
    [
        executor_registry.execute_t1105_real,
        executor_registry.execute_t1560_001_real,
        executor_registry.execute_t1030_real,
    ],
)
def test_c0026_preserves_guest_process_failure(monkeypatch, executor) -> None:
    failure = subprocess.CalledProcessError(23, ["vagrant", "ssh"], stderr="guest failed")

    def fail_guest(**kwargs):
        assert kwargs["execution_user"] == "ubuntu"
        raise failure

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", fail_guest)
    with pytest.raises(subprocess.CalledProcessError) as captured:
        executor("0.c0026", "0.c0026")
    assert captured.value is failure


@pytest.mark.parametrize(
    "executor",
    [
        executor_registry.execute_t1105_real,
        executor_registry.execute_t1560_001_real,
        executor_registry.execute_t1030_real,
    ],
)
def test_c0026_preserves_nonzero_guest_result(monkeypatch, executor) -> None:
    guest_result = subprocess.CompletedProcess(
        ["vagrant", "ssh"], 23, stdout="", stderr="guest failed"
    )

    def run_guest(**kwargs):
        assert kwargs["execution_user"] == "ubuntu"
        return guest_result

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", run_guest)
    with pytest.raises(subprocess.CalledProcessError) as captured:
        executor("0.c0026", "0.c0026")
    assert captured.value.returncode == 23
    assert captured.value.stderr == "guest failed"
