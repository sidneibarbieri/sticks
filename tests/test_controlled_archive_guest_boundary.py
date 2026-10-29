"""Controlled archiving and chunking cannot succeed on the controller."""

import subprocess

import pytest

from executors import executor_registry


CAMPAIGN_ID = "0.apt41_dust"
CONTROLLED_EXECUTORS = (
    (executor_registry.execute_t1560_001_real, "target-vm:/tmp/sticks_collected_data.tar.gz"),
    (executor_registry.execute_t1030_real, "target-vm:/tmp/sticks_chunk.aa"),
)


@pytest.mark.parametrize("execute,expected_artifact", CONTROLLED_EXECUTORS)
def test_success_reports_guest_artifact(monkeypatch, tmp_path, execute, expected_artifact):
    def run_guest(**arguments):
        assert arguments["sut_profile_id"] == CAMPAIGN_ID
        output = "/tmp/sticks_chunk.aa\n" if "chunk" in expected_artifact else "archive"
        return subprocess.CompletedProcess(["guest"], 0, stdout=output, stderr="")

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", run_guest)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    success, stdout, stderr, artifacts = execute(CAMPAIGN_ID, CAMPAIGN_ID)

    assert success is True
    assert stdout
    assert stderr == ""
    assert expected_artifact in artifacts
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("execute,_expected_artifact", CONTROLLED_EXECUTORS)
def test_transport_error_is_preserved(monkeypatch, tmp_path, execute, _expected_artifact):
    original_error = FileNotFoundError("selected guest transport unavailable")

    def fail_guest(**_arguments):
        raise original_error

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", fail_guest)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    with pytest.raises(FileNotFoundError) as captured:
        execute(CAMPAIGN_ID, CAMPAIGN_ID)

    assert captured.value is original_error
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("execute,_expected_artifact", CONTROLLED_EXECUTORS)
def test_nonzero_guest_process_is_not_success(
    monkeypatch, tmp_path, execute, _expected_artifact
):
    def fail_guest(**_arguments):
        return subprocess.CompletedProcess(
            ["guest"], 23, stdout="partial", stderr="guest operation failed"
        )

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", fail_guest)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    with pytest.raises(subprocess.CalledProcessError) as captured:
        execute(CAMPAIGN_ID, CAMPAIGN_ID)

    assert captured.value.returncode == 23
    assert captured.value.stderr == "guest operation failed"
    assert list(tmp_path.iterdir()) == []


def test_chunking_without_a_reported_guest_chunk_is_not_success(monkeypatch):
    def run_guest(**_arguments):
        return subprocess.CompletedProcess(["guest"], 0, stdout="", stderr="")

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", run_guest)

    with pytest.raises(ValueError, match="no target-VM chunks"):
        executor_registry.execute_t1030_real(CAMPAIGN_ID, CAMPAIGN_ID)
