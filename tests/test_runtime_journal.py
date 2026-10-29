"""Append-only runtime records preserve completion without certifying effects."""

import hashlib
import json

import pytest
from pydantic import ValidationError

from runners.capability_facts import FactScope
from runners.runtime_invocation import RuntimeInvocationOutcome
from runners.runtime_step_contracts import RuntimeStepContract
from runners.runtime_journal import RuntimeJournalRecord, retain_runtime_record


def record():
    scope = FactScope(
        run_id="run-a",
        environment_id="lab-a",
        epoch="boot-a",
        locus="target",
        host_id="target-a",
        principal="ubuntu",
    )
    contract = RuntimeStepContract(
        campaign_id="test-campaign",
        occurrence=1,
        technique_id="T1005",
        executor_id="selected.execute",
        executor_sha256="a" * 64,
        mode="real_controlled",
        scope=scope,
        requirements=(),
        observers=(),
    )
    invocation = RuntimeInvocationOutcome(
        executor_id="selected.execute",
        executor_completed=True,
        stdout="completed",
        stderr="",
        artifacts=(),
        declared_products=("claimed",),
    )
    return RuntimeJournalRecord(
        schema_version="runtime-occurrence/v2",
        phase="executor_completed",
        contract=contract,
        invocation=invocation,
        observation_references=(),
        authorizing_facts=(),
        error_type=None,
        error_message=None,
    )


def test_retained_record_binds_actual_bytes_and_explicit_schema(tmp_path):
    reference = retain_runtime_record(record(), run_root=tmp_path)
    content = (tmp_path / reference.record_path).read_bytes()
    assert hashlib.sha256(content).hexdigest() == reference.record_sha256
    decoded = json.loads(content)
    assert decoded["schema_version"] == "runtime-occurrence/v2"
    assert decoded["invocation"]["executor_completed"] is True
    assert decoded["authorizing_facts"] == []


def test_repeated_checkpoints_do_not_overwrite_prior_record(tmp_path):
    first = retain_runtime_record(record(), run_root=tmp_path)
    original = (tmp_path / first.record_path).read_bytes()
    second = retain_runtime_record(record(), run_root=tmp_path)
    assert first.record_path != second.record_path
    assert (tmp_path / first.record_path).read_bytes() == original


def test_symlink_journal_directory_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "runtime_journal").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        retain_runtime_record(record(), run_root=tmp_path)
    assert list(outside.iterdir()) == []


@pytest.mark.parametrize(
    "changes",
    [
        {"phase": "executor_completed", "invocation": None},
        {"phase": "observed"},
        {"phase": "error"},
        {"phase": "started"},
    ],
)
def test_incoherent_checkpoint_cannot_be_serialized_as_valid_record(changes):
    with pytest.raises(ValidationError):
        RuntimeJournalRecord.model_validate(record().model_dump() | changes)
