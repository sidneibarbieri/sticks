"""Translate a lab stop request into an exception that permits scoped cleanup."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
import os
import signal
import subprocess


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
