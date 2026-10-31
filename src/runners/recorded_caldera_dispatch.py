"""Retain declared intent before one submission attempt, without implicit retry."""

import os
from pathlib import Path

from pydantic import BaseModel

from adapters.caldera_command_result import CalderaCommandResult

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
    *, occurrence_binding: BaseModel | None = None,
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
    if occurrence_binding is not None:
        _retain(record_dir / "occurrence-binding.json", occurrence_binding)
    link_id = client.submit_command(intent.operation_id, command)
    expected = intent.bind_link(link_id)
    _retain(record_dir / "dispatch-submission.json", expected)
    return expected


def retain_completed_command(
    client: CalderaOperations, record_dir: Path,
) -> CalderaCommandResult:
    """Validate the native result against durable submission before retaining it."""
    result_path = record_dir / "command-result.json"
    if result_path.exists():
        raise FileExistsError(result_path)
    intent = CalderaDispatchIntent.model_validate_json(
        (record_dir / "dispatch-intent.json").read_bytes()
    )
    expected = CalderaDispatchExpectation.model_validate_json(
        (record_dir / "dispatch-submission.json").read_bytes()
    )
    if expected != intent.bind_link(expected.link_id):
        raise ValueError("CALDERA acknowledgment differs from durable intent")
    result = client.completed_command(expected)
    _retain(result_path, result)
    return result


def replay_completed_command(record_dir: Path) -> CalderaCommandResult:
    """Check retained identity consistency; this cannot recreate the native server ledger."""
    intent = CalderaDispatchIntent.model_validate_json(
        (record_dir / "dispatch-intent.json").read_bytes()
    )
    expected = CalderaDispatchExpectation.model_validate_json(
        (record_dir / "dispatch-submission.json").read_bytes()
    )
    result = CalderaCommandResult.model_validate_json(
        (record_dir / "command-result.json").read_bytes()
    )
    if expected != intent.bind_link(expected.link_id):
        raise ValueError("Retained acknowledgment differs from dispatch intent")
    if result.dispatch != result.dispatch.__class__(
        **expected.model_dump(), finished_at=result.dispatch.finished_at
    ):
        raise ValueError("Retained result differs from acknowledged dispatch")
    if result.process_exit_code != 0:
        raise ValueError("Retained command lacks explicit successful exit")
    return result
