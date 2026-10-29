from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from evaluation.effort_trial import Condition, EffortTrial, EventKind, TrialEvent, active_seconds


def _event(kind: EventKind, seconds: int) -> TrialEvent:
    start = datetime(2026, 8, 27, tzinfo=timezone.utc)
    return TrialEvent(kind=kind, at_utc=start + timedelta(seconds=seconds))


def test_active_time_excludes_pauses() -> None:
    events = [
        _event(EventKind.START, 0),
        _event(EventKind.PAUSE, 10),
        _event(EventKind.RESUME, 40),
        _event(EventKind.FINISH, 55),
    ]
    assert active_seconds(events) == 25.0


def test_finished_trial_requires_hashes_counts_and_duration() -> None:
    with pytest.raises(ValidationError):
        EffortTrial(
            trial_id="T01",
            operator_code="P01",
            condition=Condition.RAW_MANUAL,
            campaign_id="C0010",
            input_path="input.json",
            input_sha256="a" * 64,
            events=[_event(EventKind.START, 0), _event(EventKind.FINISH, 10)],
        )


def test_operator_identifier_must_be_pseudonymous() -> None:
    with pytest.raises(ValidationError):
        EffortTrial(
            trial_id="T01",
            operator_code="analyst@example.org",
            condition=Condition.STICKS_ASSISTED,
            campaign_id="C0010",
            input_path="input.json",
            input_sha256="a" * 64,
            events=[_event(EventKind.START, 0)],
        )
