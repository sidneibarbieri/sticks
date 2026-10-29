"""Prospective C0045 process handoff and cleanup are fail-closed."""

import subprocess

import pytest

from executors.c0045_compute_command import build_c0045_compute_command
from executors.c0045_compute_executor import execute_c0045_compute_treatment


def test_treatment_hands_live_process_to_observer_and_cleans_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []
    observed = []

    def guest_command(profile, script, *, execution_user, timeout):
        calls.append((profile, script, execution_user, timeout))
        return subprocess.CompletedProcess(
            args=script, returncode=0,
            stdout="123\n" if len(calls) == 1 else "", stderr="",
        )

    monkeypatch.setattr(
        "executors.c0045_compute_executor.run_bash_on_target_vm", guest_command
    )

    def observer(selection):
        observed.append(selection)
        assert selection.process_id == 123
        assert selection.command_sha256 == build_c0045_compute_command(
            selection.nonce
        ).expected_command_sha256
        assert len(calls) == 1
        return False

    completed, stdout, stderr, artifacts = execute_c0045_compute_treatment(
        "0.shadowray", "0.shadowray", live_observer=observer,
    )
    assert completed is True
    assert "verdict retained separately" in stdout
    assert stderr == "" and artifacts == ()
    assert len(observed) == 1 and len(calls) == 2
    assert all(call[2] == "rayuser" for call in calls)
    assert observed[0].command_sha256 in calls[1][1]


def test_observer_failure_still_stops_selected_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def guest_command(profile, script, *, execution_user, timeout):
        calls.append(script)
        return subprocess.CompletedProcess(
            args=script, returncode=0,
            stdout="123\n" if len(calls) == 1 else "", stderr="",
        )

    monkeypatch.setattr(
        "executors.c0045_compute_executor.run_bash_on_target_vm", guest_command
    )

    def failing_observer(_selection):
        raise RuntimeError("observer failed")

    with pytest.raises(RuntimeError, match="observer failed"):
        execute_c0045_compute_treatment(
            "0.shadowray", "0.shadowray", live_observer=failing_observer,
        )
    assert len(calls) == 2


def test_observation_and_cleanup_failures_remain_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def guest_command(profile, script, *, execution_user, timeout):
        calls.append(script)
        return subprocess.CompletedProcess(
            args=script, returncode=0 if len(calls) == 1 else 7,
            stdout="123\n" if len(calls) == 1 else "", stderr="cleanup failed",
        )

    monkeypatch.setattr(
        "executors.c0045_compute_executor.run_bash_on_target_vm", guest_command
    )

    def failing_observer(_selection):
        raise RuntimeError("observer failed")

    with pytest.raises(ExceptionGroup) as failure:
        execute_c0045_compute_treatment(
            "0.shadowray", "0.shadowray", live_observer=failing_observer,
        )
    assert len(failure.value.exceptions) == 2
    assert isinstance(failure.value.exceptions[0], RuntimeError)
    assert isinstance(failure.value.exceptions[1], subprocess.CalledProcessError)


def test_launch_without_one_pid_does_not_call_observer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "executors.c0045_compute_executor.run_bash_on_target_vm",
        lambda profile, script, *, execution_user, timeout: subprocess.CompletedProcess(
            args=script, returncode=0, stdout="123\n456\n", stderr=""
        ),
    )

    with pytest.raises(ValueError, match="one process ID"):
        execute_c0045_compute_treatment(
            "0.shadowray", "0.shadowray",
            live_observer=lambda _selection: pytest.fail("observer must not run"),
        )
