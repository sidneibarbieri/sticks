"""Selected C0026 archive steps preserve original guest transport failures."""

import subprocess

import pytest

from executors import executor_registry as executors


@pytest.mark.parametrize(
    "execute", [executors.execute_t1560_001_real, executors.execute_t1030_real]
)
def test_archive_steps_preserve_original_guest_exception(
    monkeypatch, execute, tmp_path
):
    failure = FileNotFoundError("guest absent")

    def fail(**kwargs):
        assert kwargs["execution_user"] == "ubuntu"
        raise failure

    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(executors, "run_bash_on_target_vm", fail)
    with pytest.raises(FileNotFoundError) as caught:
        execute("0.c0026", "0.c0026")
    assert caught.value is failure
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "execute", [executors.execute_t1560_001_real, executors.execute_t1030_real]
)
def test_archive_steps_preserve_guest_nonzero_exit(monkeypatch, execute, tmp_path):
    failed = subprocess.CompletedProcess(
        ["guest"], 17, "partial", "original guest stderr"
    )
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    monkeypatch.setattr(executors, "run_bash_on_target_vm", lambda **kwargs: failed)
    with pytest.raises(subprocess.CalledProcessError) as caught:
        execute("0.c0026", "0.c0026")
    assert caught.value.returncode == 17
    assert caught.value.stderr == "original guest stderr"
    assert list(tmp_path.iterdir()) == []
