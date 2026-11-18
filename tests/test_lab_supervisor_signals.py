"""A stopped supervisor must forward the request only to its owned child group."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from scripts.lab_shutdown import StopSignals, forward_stop_signals

ROOT = Path(__file__).resolve().parents[1]
CHILD = """
from pathlib import Path
import os,signal,sys
root=Path(sys.argv[1])
def stop(number,frame):
    (root/'child-stopped').write_text(str(number))
    raise SystemExit(0 if sys.argv[2]=='clean' else 128+number)
signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)
(root/'child-pid').write_text(str(os.getpid()))
print('READY',flush=True)
signal.pause()
"""
SUPERVISOR = """
from pathlib import Path
import os,sys
sys.path.insert(0,sys.argv[1])
from scripts.run_isolated_lab_campaign import run_logged_command
root=Path(sys.argv[2])
raise SystemExit(run_logged_command(
    [sys.executable,'-c',sys.argv[3],str(root),sys.argv[4]],
    workspace=Path(sys.argv[1]), environment=os.environ.copy(),
    log_path=root/'execution.log'))
"""


@pytest.mark.skipif(os.name != "posix", reason="POSIX lab process groups")
@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
@pytest.mark.parametrize("child_exit", ["clean", "signal"])
def test_parent_stop_is_forwarded_and_cannot_report_success(
    tmp_path: Path, stop_signal: signal.Signals, child_exit: str
) -> None:
    sentinel = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        start_new_session=True,
    )
    parent = subprocess.Popen(
        [sys.executable, "-c", SUPERVISOR, str(ROOT), str(tmp_path), CHILD, child_exit],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        deadline = time.monotonic() + 5
        marker = tmp_path / "child-pid"
        while (
            not marker.exists()
            and parent.poll() is None
            and time.monotonic() < deadline
        ):
            time.sleep(0.01)
        assert marker.exists(), "Owned fixture child did not become ready"
        os.kill(parent.pid, stop_signal)
        stdout, stderr = parent.communicate(timeout=5)
        assert parent.returncode == 128 + stop_signal, (stdout, stderr)
        assert (tmp_path / "child-stopped").read_text() == str(stop_signal.value)
        assert "READY" in (tmp_path / "execution.log").read_text()
        assert sentinel.poll() is None, "An unrelated process was stopped"
    finally:
        marker = tmp_path / "child-pid"
        if marker.exists():
            try:
                os.killpg(int(marker.read_text()), signal.SIGKILL)
            except ProcessLookupError:
                pass
        if parent.poll() is None:
            parent.kill()
        parent.communicate(timeout=5)
        if sentinel.poll() is None:
            sentinel.kill()
        sentinel.wait(timeout=5)


def test_signal_before_child_attachment_is_forwarded_after_attach(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent: list[tuple[int, int]] = []
    monkeypatch.setattr(os, "killpg", lambda pid, number: sent.append((pid, number)))
    stop = StopSignals()
    stop.request(signal.SIGTERM, None)
    assert sent == []
    stop.attach(SimpleNamespace(pid=123, returncode=None))
    assert sent == [(123, signal.SIGTERM)]


def test_exited_child_is_never_signaled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        os, "killpg", lambda *args: pytest.fail("signaled exited child")
    )
    stop = StopSignals(process=SimpleNamespace(pid=123, returncode=0))
    stop.request(signal.SIGTERM, None)
    assert stop.requested == [signal.SIGTERM]


def test_child_group_exit_race_is_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    def disappeared(pid: int, number: int) -> None:
        raise ProcessLookupError("child process group already exited")

    monkeypatch.setattr(os, "killpg", disappeared)
    stop = StopSignals(process=SimpleNamespace(pid=123, returncode=None))
    stop.request(signal.SIGTERM, None)
    assert stop.requested == [signal.SIGTERM]


def test_signal_permission_error_is_not_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    def denied(pid: int, number: int) -> None:
        raise PermissionError("cannot signal child process group")

    monkeypatch.setattr(os, "killpg", denied)
    stop = StopSignals(process=SimpleNamespace(pid=123, returncode=None))
    with pytest.raises(PermissionError, match="cannot signal"):
        stop.request(signal.SIGTERM, None)


@pytest.mark.parametrize("failed", [False, True])
def test_forwarding_restores_both_callers_signal_handlers(failed: bool) -> None:
    original = {
        number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)
    }
    if failed:
        with pytest.raises(ValueError), forward_stop_signals():
            raise ValueError("injected supervisor failure")
    else:
        with forward_stop_signals():
            pass
    assert {number: signal.getsignal(number) for number in original} == original
