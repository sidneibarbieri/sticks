"""Persist C0045 lab lifecycle events so abrupt interruption remains visible."""

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Literal
from uuid import uuid4

from runners.capability_facts import Identity, ImmutableRecord
from runners.capability_observations import _directory, _ensure_directory, _read_record, _write_exclusive


LIFECYCLE_DIRECTORY = "c0045-series-lifecycle"


class C0045LifecycleEvent(ImmutableRecord):
    """An immutable event in one fresh-lab attempt's lifecycle."""

    schema_version: Literal["c0045-series-lifecycle/v1"]
    attempt_id: Identity
    cell_id: Identity
    event: Literal["boot_started", "teardown_completed", "recovered_after_interruption"]


def _event_directory(output_dir: Path) -> Path:
    """Return the private controller-side lifecycle directory."""
    return output_dir / LIFECYCLE_DIRECTORY


def retain_lifecycle_event(
    output_dir: Path, *, attempt_id: str, cell_id: str,
    event: Literal["boot_started", "teardown_completed", "recovered_after_interruption"],
) -> C0045LifecycleEvent:
    """Append a no-overwrite lifecycle event before or after lab ownership."""
    record = C0045LifecycleEvent(
        schema_version="c0045-series-lifecycle/v1",
        attempt_id=attempt_id,
        cell_id=cell_id,
        event=event,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    with _directory(None, str(output_dir)) as root:
        _ensure_directory(root, LIFECYCLE_DIRECTORY)
        with _directory(root, LIFECYCLE_DIRECTORY) as events:
            _write_exclusive(events, f"{uuid4().hex}.json", record.model_dump_json().encode())
    return record


def lifecycle_events(output_dir: Path) -> tuple[C0045LifecycleEvent, ...]:
    """Read every retained lifecycle event in a stable filename order."""
    directory_path = _event_directory(output_dir)
    if not directory_path.exists():
        return ()
    with _directory(None, str(directory_path)) as directory:
        filenames = sorted(os.listdir(directory))
        return tuple(
            C0045LifecycleEvent.model_validate_json(_read_record(directory, filename))
            for filename in filenames
        )


def unfinished_attempts(
    events: Iterable[C0045LifecycleEvent],
) -> tuple[C0045LifecycleEvent, ...]:
    """Return started attempts that have no terminal teardown event."""
    starts: dict[str, C0045LifecycleEvent] = {}
    finished: set[str] = set()
    for record in events:
        if record.event == "boot_started":
            if record.attempt_id in starts:
                raise ValueError("C0045 lifecycle attempt started more than once")
            starts[record.attempt_id] = record
            continue
        if record.attempt_id in finished:
            raise ValueError("C0045 lifecycle attempt ended more than once")
        finished.add(record.attempt_id)
    unknown_finished = finished.difference(starts)
    if unknown_finished:
        raise ValueError("C0045 lifecycle terminal event lacks a start")
    return tuple(record for attempt_id, record in starts.items() if attempt_id not in finished)
