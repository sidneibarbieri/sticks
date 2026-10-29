"""Retain and verify observations within a trusted controller run directory."""

import hashlib
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Iterator, Self
from uuid import uuid4

from pydantic import Field, model_validator

from runners.capability_facts import (
    FactScope,
    Identity,
    Digest,
    ImmutableRecord,
    ObservationReference,
)

_MAX_RECORD_BYTES = 1024 * 1024


class PredicateObservation(ImmutableRecord):
    """Report measured products independently of executor completion."""

    scope: FactScope
    predicate_id: Identity
    passed: Annotated[bool, Field(strict=True)]
    established_facts: tuple[Identity, ...]
    details: dict[str, str | int | bool]
    content_sha256: Digest | None = None
    producer_occurrence: Annotated[int, Field(strict=True, gt=0)] | None = None
    consumer_occurrence: Annotated[int, Field(strict=True, gt=0)] | None = None
    revalidated_reference: ObservationReference | None = None

    @model_validator(mode="after")
    def validate_products(self) -> Self:
        """Failed observations cannot establish capabilities."""
        if not self.passed and self.established_facts:
            raise ValueError("Failed observations cannot establish facts")
        if len(set(self.established_facts)) != len(self.established_facts):
            raise ValueError("Observation products must be unique")
        if (self.consumer_occurrence is None) != (self.revalidated_reference is None):
            raise ValueError(
                "Revalidation requires both consumer and original acquisition"
            )
        if self.consumer_occurrence is not None and (
            self.producer_occurrence is None
            or self.consumer_occurrence <= self.producer_occurrence
        ):
            raise ValueError(
                "Revalidation consumer must follow the producing occurrence"
            )
        return self


class RetainedObservation(ImmutableRecord):
    """Bind the observer identity to its acquired result."""

    authority_id: Identity
    observation: PredicateObservation


@contextmanager
def _directory(parent: int | None, path: str) -> Iterator[int]:
    descriptor = os.open(
        path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
    )
    try:
        yield descriptor
    finally:
        os.close(descriptor)


def _ensure_directory(parent: int, name: str) -> None:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
    except FileExistsError:
        # The subsequent no-follow open verifies the existing directory.
        pass


def _write_exclusive(directory: int, name: str, content: bytes) -> None:
    if len(content) > _MAX_RECORD_BYTES:
        raise ValueError("Observation record exceeds size limit")
    descriptor = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        mode=0o600,
        dir_fd=directory,
    )
    with os.fdopen(descriptor, "wb") as output:
        output.write(content)
        output.flush()
        os.fsync(output.fileno())


def _read_record(directory: int, name: str) -> bytes:
    descriptor = os.open(
        name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
    )
    with os.fdopen(descriptor, "rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_RECORD_BYTES:
            raise ValueError("Observation must be a bounded regular file")
        content = source.read(_MAX_RECORD_BYTES + 1)
    if len(content) > _MAX_RECORD_BYTES:
        raise ValueError("Observation record exceeds size limit")
    return content


def retain_observation(
    observation: PredicateObservation,
    *,
    authority_id: str,
    run_root: Path,
) -> ObservationReference:
    """Retain a new acquisition and receipt without overwriting prior records.

    This is controller storage, not observer authentication. The dispatcher must
    obtain results from registered adapters before calling this function.
    """
    snapshot = PredicateObservation.model_validate(
        observation.model_dump(mode="python", warnings=False), strict=True
    )
    retained = RetainedObservation(authority_id=authority_id, observation=snapshot)
    content = retained.model_dump_json().encode("utf-8")
    filename = f"{uuid4().hex}.json"
    reference = ObservationReference(
        authority_id=authority_id,
        predicate_id=observation.predicate_id,
        record_path=f"observations/{filename}",
        record_sha256=hashlib.sha256(content).hexdigest(),
    )
    with _directory(None, str(run_root)) as root:
        _ensure_directory(root, "observations")
        _ensure_directory(root, "observation_receipts")
        with _directory(root, "observations") as records:
            _write_exclusive(records, filename, content)
        with _directory(root, "observation_receipts") as receipts:
            _write_exclusive(
                receipts, filename, reference.model_dump_json().encode("utf-8")
            )
    return reference


def verify_observation_reference(
    reference: ObservationReference,
    *,
    run_root: Path,
    expected_scope: FactScope,
    expected_predicate: str,
) -> PredicateObservation:
    """Verify acquisition binding, bytes, observer fields and exact scope.

    Receipts detect changes relative to retained controller acquisitions. They
    are not signatures and do not protect a compromised controller directory.
    """
    components = reference.record_path.split("/")
    if len(components) != 2 or components[0] != "observations":
        raise ValueError(
            "Observation must belong to the retained acquisition directory"
        )
    filename = components[1]
    with _directory(None, str(run_root)) as root:
        with _directory(root, "observation_receipts") as receipts:
            acquired = ObservationReference.model_validate_json(
                _read_record(receipts, filename)
            )
        if acquired != reference:
            raise ValueError("Reference differs from the retained acquisition")
        with _directory(root, "observations") as records:
            content = _read_record(records, filename)
    if hashlib.sha256(content).hexdigest() != reference.record_sha256:
        raise ValueError("Observation digest differs from retained bytes")
    retained = RetainedObservation.model_validate_json(content)
    if retained.authority_id != reference.authority_id:
        raise ValueError("Observation authority differs from reference")
    result = retained.observation
    if (
        result.predicate_id != reference.predicate_id
        or result.predicate_id != expected_predicate
    ):
        raise ValueError("Observation predicate differs from requirement")
    if result.scope != expected_scope:
        raise ValueError("Observation scope differs from requirement")
    return result
