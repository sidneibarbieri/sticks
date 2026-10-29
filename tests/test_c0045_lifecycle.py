from pathlib import Path

import pytest

from runners.c0045_lifecycle import (
    C0045LifecycleEvent,
    lifecycle_events,
    retain_lifecycle_event,
    unfinished_attempts,
)


def event(attempt_id: str, event_name: str) -> C0045LifecycleEvent:
    return C0045LifecycleEvent(
        schema_version="c0045-series-lifecycle/v1",
        attempt_id=attempt_id,
        cell_id="b1-treatment",
        event=event_name,
    )


def test_lifecycle_retains_append_only_attempt_events(tmp_path: Path) -> None:
    retain_lifecycle_event(
        tmp_path,
        attempt_id="attempt-1",
        cell_id="b1-treatment",
        event="boot_started",
    )
    retain_lifecycle_event(
        tmp_path,
        attempt_id="attempt-1",
        cell_id="b1-treatment",
        event="teardown_completed",
    )

    assert unfinished_attempts(lifecycle_events(tmp_path)) == ()


def test_lifecycle_identifies_unclosed_boot() -> None:
    assert unfinished_attempts((event("attempt-1", "boot_started"),)) == (
        event("attempt-1", "boot_started"),
    )


def test_lifecycle_rejects_terminal_event_without_start() -> None:
    with pytest.raises(ValueError, match="lacks a start"):
        unfinished_attempts((event("attempt-1", "teardown_completed"),))
