"""Translate a lab stop request into an exception that permits scoped cleanup."""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
import os
import signal
import subprocess
import time

# Grace after SIGINT lets an interrupted `vagrant up` finish its own cleanup and
# release its machine lock; SIGTERM and SIGKILL follow if the group outlives it.
STOP_GRACE_SECONDS = (120.0, 30.0, 10.0)
STOP_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)
GROUP_POLL_SECONDS = 0.2


def run_owned_stage(
    command: Sequence[str],
    cwd: str,
    environment: dict[str, str],
    grace_seconds: tuple[float, float, float] = STOP_GRACE_SECONDS,
) -> None:
    """Run one stage in its own process group and never leave that group running.

    An interruption stops every process of the stage, grandchildren included,
    before it propagates, so teardown never races a provider that still holds a
    machine lock.
    """
    process = subprocess.Popen(list(command), cwd=cwd, env=environment, start_new_session=True)
    try:
        return_code = process.wait()
    except BaseException:
        stop_process_group(process, grace_seconds)
        raise
    if return_code:
        raise subprocess.CalledProcessError(return_code, process.args)


def stop_process_group(
    process: subprocess.Popen[bytes], grace_seconds: tuple[float, float, float]
) -> None:
    group_id = process.pid
    for signal_number, grace in zip(STOP_SIGNALS, grace_seconds, strict=True):
        if not _group_alive(process, group_id):
            return
        _signal_group(group_id, signal_number)
        if _wait_for_group_exit(process, group_id, grace):
            return
    raise RuntimeError(f"stage process group {group_id} survived SIGKILL")


def _wait_for_group_exit(
    process: subprocess.Popen[bytes], group_id: int, timeout_seconds: float
) -> bool:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if not _group_alive(process, group_id):
                return True
            time.sleep(GROUP_POLL_SECONDS)
        except KeyboardInterrupt:
            return False  # a repeated Ctrl+C escalates to the next signal now
    return not _group_alive(process, group_id)


def _group_alive(process: subprocess.Popen[bytes], group_id: int) -> bool:
    process.poll()  # reap the leader so a zombie does not keep the group visible
    try:
        os.killpg(group_id, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _signal_group(group_id: int, signal_number: int) -> None:
    try:
        os.killpg(group_id, signal_number)
    except ProcessLookupError:
        pass


def _request_shutdown(signal_number: int, _frame: object) -> None:
    raise SystemExit(128 + signal_number)


@contextmanager
def termination_as_exit() -> Iterator[None]:
    previous_handler = signal.signal(signal.SIGTERM, _request_shutdown)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous_handler)


@dataclass
class StopSignals:
    """Forward stop requests only to the child session owned by this supervisor."""

    requested: list[int] = field(default_factory=list)
    process: subprocess.Popen[bytes] | None = None

    def attach(self, process: subprocess.Popen[bytes]) -> None:
        self.process = process
        for signal_number in self.requested:
            self._send(signal_number)

    def request(self, signal_number: int, _frame: object) -> None:
        self.requested.append(signal_number)
        self._send(signal_number)

    def _send(self, signal_number: int) -> None:
        if self.process is None or self.process.returncode is not None:
            return
        try:
            os.killpg(self.process.pid, signal_number)
        except ProcessLookupError:
            pass


@contextmanager
def forward_stop_signals() -> Iterator[StopSignals]:
    stop = StopSignals()
    previous = {
        signal_number: signal.signal(signal_number, stop.request)
        for signal_number in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        yield stop
    finally:
        for signal_number, handler in previous.items():
            signal.signal(signal_number, handler)
