"""Expose the admitted occurrence to execution adapters without changing probes."""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from runners.runtime_step_contracts import RuntimeStepContract

_occurrence: ContextVar[RuntimeStepContract | None] = ContextVar(
    "runtime_dispatch_occurrence", default=None
)


@contextmanager
def runtime_dispatch_scope(contract: RuntimeStepContract) -> Iterator[None]:
    token = _occurrence.set(contract)
    try:
        yield
    finally:
        _occurrence.reset(token)


def current_dispatch_contract() -> RuntimeStepContract | None:
    return _occurrence.get()
