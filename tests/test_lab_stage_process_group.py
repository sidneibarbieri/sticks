"""An interrupted lab stage must not leave a grandchild (such as `vagrant up`) holding a machine lock."""

import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from scripts.lab_shutdown import run_owned_stage

ROOT = Path(__file__).resolve().parents[1]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _wait_for(predicate, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.1)
    return False


def _start_stage_driver(tmp_path: Path, stage_shell: str) -> tuple[subprocess.Popen, Path]:
    """Run run_owned_stage in a separate interpreter so a signal can interrupt it."""
    pid_file = tmp_path / "grandchild.pid"
    driver = tmp_path / "driver.py"
    driver.write_text(textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(ROOT)!r})
        from scripts.lab_shutdown import run_owned_stage
        run_owned_stage(["bash", "-c", {stage_shell!r}], {str(tmp_path)!r},
                        {{"PATH": "/usr/bin:/bin", "PID_FILE": {str(pid_file)!r}}},
                        grace_seconds=(1.0, 1.0, 5.0))
    """))
    process = subprocess.Popen([sys.executable, str(driver)], cwd=tmp_path, start_new_session=True,
                               env={"PATH": os.environ["PATH"], "PID_FILE": str(pid_file)})
    assert _wait_for(pid_file.exists, 10), "the stage never started its grandchild"
    return process, pid_file


def test_failed_stage_reports_its_exit_status(tmp_path):
    with pytest.raises(subprocess.CalledProcessError) as failure:
        run_owned_stage(["bash", "-c", "exit 3"], str(tmp_path), {"PATH": "/usr/bin:/bin"})
    assert failure.value.returncode == 3


def test_failed_stage_stops_its_remaining_descendant(tmp_path):
    marker = tmp_path / "descendant.pid"
    try:
        with pytest.raises(subprocess.CalledProcessError) as failure:
            run_owned_stage(
                ["bash", "-c", 'sleep 300 & echo $! > "$PID_FILE"; exit 3'],
                str(tmp_path),
                {"PATH": "/usr/bin:/bin", "PID_FILE": str(marker)},
                grace_seconds=(1.0, 1.0, 5.0),
            )
        assert failure.value.returncode == 3
        descendant_pid = int(marker.read_text())
        assert _wait_for(lambda: not _alive(descendant_pid), 5)
    finally:
        if marker.exists():
            try:
                group_id = os.getpgid(int(marker.read_text()))
                assert group_id != os.getpgrp()
                os.killpg(group_id, signal.SIGTERM)
            except ProcessLookupError:
                pass


def test_stage_and_cleanup_failures_are_both_preserved(tmp_path, monkeypatch):
    cleanup_error = RuntimeError("fixture cleanup failure")

    def fail_cleanup(process, grace_seconds):
        raise cleanup_error

    monkeypatch.setattr("scripts.lab_shutdown.stop_process_group", fail_cleanup)
    with pytest.raises(ExceptionGroup) as failure:
        run_owned_stage(["bash", "-c", "exit 3"], str(tmp_path), {"PATH": "/usr/bin:/bin"})
    stage_error, observed_cleanup_error = failure.value.exceptions
    assert isinstance(stage_error, subprocess.CalledProcessError)
    assert stage_error.returncode == 3
    assert observed_cleanup_error is cleanup_error


def test_interrupt_stops_the_grandchild_before_returning(tmp_path):
    process, pid_file = _start_stage_driver(
        tmp_path, 'sleep 300 & echo $! > "$PID_FILE"; wait')
    grandchild = int(pid_file.read_text())
    os.killpg(process.pid, signal.SIGINT)  # Ctrl+C reaches the runner's group only
    assert process.wait(timeout=30) != 0
    assert not _alive(grandchild), "the interrupted stage left its grandchild running"


def test_a_grandchild_ignoring_sigint_is_escalated(tmp_path):
    process, pid_file = _start_stage_driver(
        tmp_path, 'trap "" INT; (trap "" INT; sleep 300) & echo $! > "$PID_FILE"; wait')
    grandchild = int(pid_file.read_text())
    os.killpg(process.pid, signal.SIGINT)
    assert process.wait(timeout=30) != 0
    assert _wait_for(lambda: not _alive(grandchild), 5)
