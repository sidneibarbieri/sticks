"""Tamper-evident timing records for the preregistered analyst-effort study."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROTOCOL_VERSION = "sticks-analyst-effort/v1"
_OPERATOR_CODE = re.compile(r"^P[0-9]{2,3}$")


class Condition(str, Enum):
    RAW_MANUAL = "raw_manual"
    STICKS_ASSISTED = "sticks_assisted"


class EventKind(str, Enum):
    START = "start"
    PAUSE = "pause"
    RESUME = "resume"
    FINISH = "finish"


class TrialEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: EventKind
    at_utc: datetime

    @model_validator(mode="after")
    def _timestamp_is_utc(self) -> "TrialEvent":
        if self.at_utc.tzinfo is None or self.at_utc.utcoffset() != timezone.utc.utcoffset(None):
            raise ValueError("event timestamps must be timezone-aware UTC")
        return self


class EffortTrial(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_version: str = PROTOCOL_VERSION
    trial_id: str
    operator_code: str
    condition: Condition
    campaign_id: str
    input_path: str
    input_sha256: str
    events: list[TrialEvent]
    output_path: str | None = None
    output_sha256: str | None = None
    completed_steps: int | None = Field(default=None, ge=0)
    unresolved_steps: int | None = Field(default=None, ge=0)
    active_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _record_is_consistent(self) -> "EffortTrial":
        if not _OPERATOR_CODE.fullmatch(self.operator_code):
            raise ValueError("operator_code must be pseudonymous (P followed by 2-3 digits)")
        kinds = [event.kind for event in self.events]
        if not kinds or kinds[0] is not EventKind.START:
            raise ValueError("the first event must be start")
        if kinds.count(EventKind.START) != 1 or kinds.count(EventKind.FINISH) > 1:
            raise ValueError("a trial has exactly one start and at most one finish")
        if any(b.at_utc < a.at_utc for a, b in zip(self.events, self.events[1:])):
            raise ValueError("event timestamps must be monotonic")
        state = "active"
        for kind in kinds[1:]:
            allowed = {
                "active": {EventKind.PAUSE, EventKind.FINISH},
                "paused": {EventKind.RESUME},
                "finished": set(),
            }
            if kind not in allowed[state]:
                raise ValueError(f"invalid {kind.value} event while trial is {state}")
            state = {
                EventKind.PAUSE: "paused",
                EventKind.RESUME: "active",
                EventKind.FINISH: "finished",
            }[kind]
        completed = state == "finished"
        result_fields = (
            self.output_path,
            self.output_sha256,
            self.completed_steps,
            self.unresolved_steps,
            self.active_seconds,
        )
        if completed != all(value is not None for value in result_fields):
            raise ValueError("finished trials require output hash, step counts, and active_seconds")
        return self


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def active_seconds(events: list[TrialEvent]) -> float:
    total = 0.0
    active_since: datetime | None = None
    for event in events:
        if event.kind in {EventKind.START, EventKind.RESUME}:
            active_since = event.at_utc
        elif event.kind in {EventKind.PAUSE, EventKind.FINISH}:
            if active_since is None:
                raise ValueError("cannot stop an inactive trial")
            total += (event.at_utc - active_since).total_seconds()
            active_since = None
    return round(total, 3)


def write_trial(path: Path, trial: EffortTrial) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(trial.model_dump_json(indent=2) + "\n", encoding="utf-8")


def read_trial(path: Path) -> EffortTrial:
    return EffortTrial.model_validate_json(path.read_text(encoding="utf-8"))
