"""Retain declared intent before one submission attempt, without implicit retry."""

import os
from pathlib import Path

from pydantic import BaseModel

from adapters.caldera_dispatch import (
    CalderaDispatchExpectation,
    CalderaDispatchIntent,
    command_digest,
)
from adapters.caldera_operations import CalderaCommand, CalderaOperations


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _retain(path: Path, record: BaseModel) -> None:
    with path.open("x", encoding="utf-8") as output:
        output.write(record.model_dump_json(indent=2) + "\n")
        output.flush()
        os.fsync(output.fileno())
    _sync_directory(path.parent)


def submit_recorded_command(
    client: CalderaOperations,
    intent: CalderaDispatchIntent,
    command: CalderaCommand,
    record_dir: Path,
) -> CalderaDispatchExpectation:
    """Keep intent on API failure; absence of an acknowledgment is inconclusive."""
    conditions = (
        ("agent_identity", command.agent_id == intent.agent_id),
        ("platform", command.platform == intent.platform),
        ("executor", command.executor == intent.executor),
        ("executor_timeout", command.timeout_seconds == intent.timeout_seconds),
        ("command_digest", command_digest(command.command) == intent.command_sha256),
    )
    failed = tuple(name for name, passed in conditions if not passed)
    if failed:
        raise ValueError("CALDERA submission conditions failed: " + ", ".join(failed))
    record_dir.mkdir(exist_ok=False)
    _sync_directory(record_dir.parent)
    _retain(record_dir / "dispatch-intent.json", intent)
    link_id = client.submit_command(intent.operation_id, command)
    expected = intent.bind_link(link_id)
    _retain(record_dir / "dispatch-submission.json", expected)
    return expected
