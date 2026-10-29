"""Append-only versioned checkpoints for runtime execution and authority."""

import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from runners.capability_facts import (
    CapabilityFact,
    Digest,
    ImmutableRecord,
    ObservationReference,
)
from runners.capability_observations import (
    _directory,
    _ensure_directory,
    _write_exclusive,
)
from runners.runtime_invocation import RuntimeInvocationOutcome
from runners.runtime_step_contracts import RuntimeStepContract
from runners.runtime_diagnostics import ProcessFailure


class RuntimeJournalRecord(ImmutableRecord):
    """Preserve an explicit checkpoint without rewriting previous outcomes."""

    schema_version: Literal["runtime-occurrence/v2"]
    phase: Literal["started", "executor_completed", "observed", "simulated", "error"]
    contract: RuntimeStepContract
    invocation: RuntimeInvocationOutcome | None
    observation_references: tuple[ObservationReference, ...]
    authorizing_facts: tuple[CapabilityFact, ...]
    simulated_facts: tuple[CapabilityFact, ...] = ()
    consumed_references: tuple[ObservationReference, ...] = ()
    revalidation_references: tuple[ObservationReference, ...] = ()
    error_type: str | None
    error_message: str | None
    process_failure: ProcessFailure | None = None
    recorded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_checkpoint(self) -> Self:
        if self.process_failure is not None and self.phase != "error":
            raise ValueError("Process failure diagnostics require an error checkpoint")
        if self.phase == "started" and (
            self.invocation is not None
            or self.observation_references
            or self.authorizing_facts
            or self.simulated_facts
        ):
            raise ValueError("A started checkpoint cannot contain later outcomes")
        if (
            self.phase in {"executor_completed", "observed", "simulated"}
            and self.invocation is None
        ):
            raise ValueError(
                "An execution checkpoint requires its original invocation outcome"
            )
        if self.phase == "observed" and not self.observation_references:
            raise ValueError(
                "An observed checkpoint requires retained observation references"
            )
        if (self.phase == "error") != (
            self.error_type is not None and self.error_message is not None
        ):
            raise ValueError("Error fields must identify an error checkpoint")
        for fact in self.authorizing_facts:
            if (
                fact.origin != "observed"
                or fact.observation not in self.observation_references
                or self.invocation is None
                or not self.invocation.executor_completed
            ):
                raise ValueError(
                    "Granted facts must belong to retained observations after completed execution"
                )
        for fact in self.simulated_facts:
            if (
                fact.origin != "simulation"
                or fact.scope != self.contract.scope
                or self.contract.mode != "naive_simulated"
                or self.invocation is None
                or not self.invocation.executor_completed
            ):
                raise ValueError(
                    "Simulated products must retain the selected simulation scope"
                )
        if self.phase == "simulated" and (
            self.contract.mode != "naive_simulated" or self.authorizing_facts
        ):
            raise ValueError("A simulation checkpoint cannot grant observed authority")
        return self


class RuntimeJournalReference(ImmutableRecord):
    record_path: str
    record_sha256: Digest


def retain_runtime_record(
    record: RuntimeJournalRecord, *, run_root: Path
) -> RuntimeJournalReference:
    """Retain validated bytes in a new bounded no-follow journal file."""
    snapshot = RuntimeJournalRecord.model_validate(
        record.model_dump(mode="python"), strict=True
    )
    content = snapshot.model_dump_json().encode("utf-8")
    filename = f"{snapshot.contract.occurrence:04d}-{uuid4().hex}.json"
    with _directory(None, str(run_root)) as root:
        _ensure_directory(root, "runtime_journal")
        with _directory(root, "runtime_journal") as directory:
            _write_exclusive(directory, filename, content)
    return RuntimeJournalReference(
        record_path=f"runtime_journal/{filename}",
        record_sha256=hashlib.sha256(content).hexdigest(),
    )
