"""Retained observation integrity and scope checks using real files."""

import hashlib

import pytest
from pydantic import ValidationError

from runners.capability_facts import FactScope, ObservationReference
from runners.capability_observations import (
    PredicateObservation,
    retain_observation,
    verify_observation_reference,
)


def observation(**changes):
    fields = dict(
        scope=FactScope(
            run_id="run-a",
            environment_id="lab-a",
            epoch="boot-a",
            locus="target",
            host_id="target-a",
            principal="ubuntu",
        ),
        predicate_id="shell-nonce",
        passed=True,
        established_facts=("lab:shell",),
        details={"nonce_matched": True},
    )
    return PredicateObservation(**(fields | changes))


def retain(tmp_path, acquired=None):
    return retain_observation(
        acquired or observation(), authority_id="lab-shell", run_root=tmp_path
    )


def verify(tmp_path, reference, acquired=None, **changes):
    expected = acquired or observation()
    fields = dict(
        run_root=tmp_path,
        expected_scope=expected.scope,
        expected_predicate=expected.predicate_id,
    )
    return verify_observation_reference(reference, **(fields | changes))


def test_retained_observation_round_trips_actual_bytes(tmp_path):
    acquired = observation()
    reference = retain(tmp_path, acquired)
    assert verify(tmp_path, reference) == acquired
    assert (
        hashlib.sha256((tmp_path / reference.record_path).read_bytes()).hexdigest()
        == reference.record_sha256
    )


def test_modified_record_is_refused(tmp_path):
    reference = retain(tmp_path)
    (tmp_path / reference.record_path).write_bytes(b"{}")
    with pytest.raises(ValueError):
        verify(tmp_path, reference)


def test_recomputed_digest_cannot_replace_retained_acquisition(tmp_path):
    reference = retain(tmp_path)
    changed = b"{}"
    (tmp_path / reference.record_path).write_bytes(changed)
    forged = ObservationReference(
        **(
            reference.model_dump()
            | {
                "record_sha256": hashlib.sha256(changed).hexdigest(),
            }
        )
    )
    with pytest.raises(ValueError):
        verify(tmp_path, forged)


def test_unissued_reference_is_refused(tmp_path):
    (tmp_path / "observations").mkdir()
    content = observation().model_dump_json().encode()
    (tmp_path / "observations" / "unissued.json").write_bytes(content)
    forged = ObservationReference(
        authority_id="lab-shell",
        predicate_id="shell-nonce",
        record_path="observations/unissued.json",
        record_sha256=hashlib.sha256(content).hexdigest(),
    )
    with pytest.raises((FileNotFoundError, ValueError)):
        verify(tmp_path, forged)


def test_missing_record_preserves_filesystem_failure(tmp_path):
    reference = retain(tmp_path)
    (tmp_path / reference.record_path).unlink()
    with pytest.raises(FileNotFoundError):
        verify(tmp_path, reference)


def test_symlink_record_is_refused(tmp_path):
    reference = retain(tmp_path)
    record = tmp_path / reference.record_path
    outside = tmp_path / "outside.json"
    record.rename(outside)
    record.symlink_to(outside)
    with pytest.raises(OSError):
        verify(tmp_path, reference)


def test_symlink_observation_directory_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "observations").symlink_to(outside, target_is_directory=True)
    with pytest.raises(OSError):
        retain(tmp_path)
    assert list(outside.iterdir()) == []


def test_wrong_boot_cannot_validate_record(tmp_path):
    reference = retain(tmp_path)
    changed_scope = FactScope(
        **(observation().scope.model_dump() | {"epoch": "boot-b"})
    )
    with pytest.raises(ValueError):
        verify(tmp_path, reference, expected_scope=changed_scope)


def test_wrong_predicate_is_refused(tmp_path):
    reference = retain(tmp_path)
    with pytest.raises(ValueError):
        verify(tmp_path, reference, expected_predicate="different-predicate")


def test_reference_authority_must_match_retained_acquisition(tmp_path):
    reference = retain(tmp_path)
    forged = ObservationReference(
        **(reference.model_dump() | {"authority_id": "executor"})
    )
    with pytest.raises(ValueError):
        verify(tmp_path, forged)


def test_failed_observation_cannot_establish_facts():
    with pytest.raises(ValidationError):
        observation(passed=False)


def test_failed_observation_without_products_is_retained(tmp_path):
    failed = observation(passed=False, established_facts=())
    reference = retain(tmp_path, failed)
    restored = verify(tmp_path, reference, failed)
    assert restored.passed is False
    assert restored.established_facts == ()


def test_repeated_acquisitions_preserve_both_records(tmp_path):
    first = retain(tmp_path)
    second = retain(tmp_path)
    assert first.record_path != second.record_path
    assert verify(tmp_path, first).passed
    assert verify(tmp_path, second).passed


@pytest.mark.parametrize("path", ["../outside.json", "/tmp/outside.json"])
def test_reference_cannot_escape_root(path):
    with pytest.raises(ValidationError):
        ObservationReference(
            authority_id="lab-shell",
            predicate_id="shell-nonce",
            record_path=path,
            record_sha256="a" * 64,
        )


def test_invalid_nested_mutation_is_refused_before_acquisition_write(tmp_path):
    acquired = observation()
    acquired.details["invalid"] = []
    with pytest.raises(ValidationError):
        retain(tmp_path, acquired)
    assert list(tmp_path.iterdir()) == []
