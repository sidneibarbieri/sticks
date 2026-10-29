"""A controlled transfer cannot be replaced by a controller-local download."""

import subprocess

import pytest

from executors import executor_registry


CONTROLLED_CAMPAIGNS = (
    "0.apt41_dust",
    "0.costaricto",
    "0.operation_midnighteclipse",
    "0.outer_space",
)


def reject_legacy_fallback(**_arguments):
    pytest.fail("controlled T1105 used the legacy guest-to-controller fallback")


@pytest.mark.parametrize("campaign_id", CONTROLLED_CAMPAIGNS)
def test_success_reports_only_the_selected_guest(monkeypatch, tmp_path, campaign_id):
    def run_guest(**arguments):
        assert arguments["sut_profile_id"] == campaign_id
        assert arguments["execution_user"] is None
        return subprocess.CompletedProcess(["guest"], 0, stdout="guest digest", stderr="")

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", run_guest)
    monkeypatch.setattr(executor_registry, "_try_run_on_target_vm", reject_legacy_fallback)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    success, stdout, stderr, artifacts = executor_registry.execute_t1105_real(
        campaign_id, campaign_id
    )

    assert success is True
    assert "guest digest" in stdout
    assert stderr == ""
    assert artifacts == ["target-vm:/tmp/sticks_downloaded_payload.sh"]
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("campaign_id", CONTROLLED_CAMPAIGNS)
def test_guest_transport_failure_preserves_original_error(monkeypatch, tmp_path, campaign_id):
    original_error = FileNotFoundError("selected target transport unavailable")

    def fail_guest(**arguments):
        assert arguments["sut_profile_id"] == campaign_id
        raise original_error

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", fail_guest)
    monkeypatch.setattr(executor_registry, "_try_run_on_target_vm", reject_legacy_fallback)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    with pytest.raises(FileNotFoundError) as captured:
        executor_registry.execute_t1105_real(campaign_id, campaign_id)

    assert captured.value is original_error
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("campaign_id", CONTROLLED_CAMPAIGNS)
def test_nonzero_guest_transfer_is_not_a_success(monkeypatch, tmp_path, campaign_id):
    def fail_guest(**arguments):
        assert arguments["sut_profile_id"] == campaign_id
        return subprocess.CompletedProcess(
            ["guest"], 17, stdout="partial", stderr="guest transfer failed"
        )

    monkeypatch.setattr(executor_registry, "run_bash_on_target_vm", fail_guest)
    monkeypatch.setattr(executor_registry, "_try_run_on_target_vm", reject_legacy_fallback)
    monkeypatch.setattr(executor_registry, "ARTIFACTS_DIR", tmp_path)

    with pytest.raises(subprocess.CalledProcessError) as captured:
        executor_registry.execute_t1105_real(campaign_id, campaign_id)

    assert captured.value.returncode == 17
    assert captured.value.stderr == "guest transfer failed"
    assert list(tmp_path.iterdir()) == []
