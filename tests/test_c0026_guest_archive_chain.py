"""C0026 archive and chunk steps cannot report host-fallback success."""

import subprocess

import pytest

from executors import executor_registry


@pytest.mark.parametrize(
    ("executor", "expected_artifact"),
    [
        (executor_registry.execute_t1560_001_real, "target-vm:/tmp/sticks_collected_data.tar.gz"),
        (executor_registry.execute_t1030_real, "target-vm:/tmp/sticks_chunk.aa"),
    ],
)
def test_c0026_chain_runs_as_declared_target_user(
    monkeypatch: pytest.MonkeyPatch, executor, expected_artifact: str
) -> None:
    calls: list[dict] = []

    def run_target(**kwargs) -> subprocess.CompletedProcess[str]:
        calls.append(kwargs)
        stdout = "/tmp/sticks_chunk.aa\n" if "split -b" in kwargs["bash_script"] else "archived\n"
        return subprocess.CompletedProcess(["vagrant", "ssh"], 0, stdout, "")

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", run_target)

    success, stdout, stderr, artifacts = executor("0.c0026", "0.c0026")

    assert success
    assert "target VM" in stdout
    assert stderr == ""
    assert expected_artifact in artifacts
    assert calls[0]["execution_user"] == "ubuntu"
    if expected_artifact.endswith("sticks_collected_data.tar.gz"):
        assert "test -f /tmp/sticks_t1005/local_collection.txt" in calls[0]["bash_script"]
        assert "hostname >" not in calls[0]["bash_script"]
    else:
        assert "cd /tmp" in calls[0]["bash_script"]
        assert "split -b 128" in calls[0]["bash_script"]


@pytest.mark.parametrize(
    "executor",
    [executor_registry.execute_t1560_001_real, executor_registry.execute_t1030_real],
)
def test_c0026_chain_refuses_host_fallback(
    monkeypatch: pytest.MonkeyPatch, executor
) -> None:
    def missing_guest(**kwargs):
        raise FileNotFoundError("guest unavailable")

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", missing_guest)

    with pytest.raises(FileNotFoundError, match="guest unavailable"):
        executor("0.c0026", "0.c0026")
