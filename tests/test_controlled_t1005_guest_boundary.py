"""Controlled local collection must occur in the selected guest."""

import subprocess

import pytest

from executors import executor_registry


CAMPAIGN_ID = "0.operation_midnighteclipse"


def test_guest_collection_reports_target_artifact(monkeypatch, tmp_path):
    def run_guest(**arguments):
        assert arguments["sut_profile_id"] == CAMPAIGN_ID
        return subprocess.CompletedProcess(["guest"], 0, stdout="guest collection", stderr="")

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", run_guest)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    success, stdout, stderr, artifacts = executor_registry.execute_t1005_real(
        CAMPAIGN_ID, CAMPAIGN_ID
    )

    assert success is True
    assert "guest collection" in stdout
    assert stderr == ""
    assert artifacts == ["target-vm:/tmp/sticks_t1005/local_collection.txt"]
    assert list(tmp_path.iterdir()) == []


def test_guest_transport_error_is_preserved(monkeypatch, tmp_path):
    original_error = FileNotFoundError("selected target transport unavailable")

    def fail_guest(**_arguments):
        raise original_error

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", fail_guest)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    with pytest.raises(FileNotFoundError) as captured:
        executor_registry.execute_t1005_real(CAMPAIGN_ID, CAMPAIGN_ID)

    assert captured.value is original_error
    assert list(tmp_path.iterdir()) == []


def test_nonzero_guest_collection_is_not_success(monkeypatch, tmp_path):
    def fail_guest(**_arguments):
        return subprocess.CompletedProcess(
            ["guest"], 19, stdout="partial", stderr="guest collection failed"
        )

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", fail_guest)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    with pytest.raises(subprocess.CalledProcessError) as captured:
        executor_registry.execute_t1005_real(CAMPAIGN_ID, CAMPAIGN_ID)

    assert captured.value.returncode == 19
    assert captured.value.stderr == "guest collection failed"
    assert list(tmp_path.iterdir()) == []
