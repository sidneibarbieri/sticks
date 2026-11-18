"""Translate a lab stop request into an exception that permits scoped cleanup."""

from collections.abc import Iterator
from contextlib import contextmanager
import signal


def _request_shutdown(signal_number: int, _frame: object) -> None:
    raise SystemExit(128 + signal_number)


@contextmanager
def termination_as_exit() -> Iterator[None]:
    previous_handler = signal.signal(signal.SIGTERM, _request_shutdown)
    try:
        yield
    finally:
        signal.signal(signal.SIGTERM, previous_handler)
