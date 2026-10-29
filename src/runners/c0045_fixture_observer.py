"""Scope-bound retained-fixture observations; no initial-access claim."""

import hashlib
import shlex
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from executors.lab_transport import run_bash_on_target_vm
from runners.c0045_fixture_contract import (
    MAX_FIXTURE_BYTES,
    TOOLKIT_SHA256,
    TRANSFER_SHA256,
)
from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord
from runners.capability_observations import PredicateObservation
from runners.lab_bootstrap_observer import _check_profile_principal
from runners.runtime_diagnostics import parse_guest_reply

PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts/probe_shadowray_target.py"
MAX_PROBE_BYTES = 65536
TRANSPORT_TIMEOUT_SECONDS = 15


class C0045FixtureRequest(ImmutableRecord):
    sut_profile_id: Literal["0.shadowray"]
    predicate_id: Literal["toolkit-staged", "loopback-transfer"]
    producer_occurrence: Annotated[int, Field(strict=True, ge=5, le=6)]
    nonce: Identity
    scope: FactScope

    @model_validator(mode="after")
    def validate_target_occurrence(self) -> Self:
        if self.scope.locus != "target" or self.scope.principal in {None, "root"}:
            raise ValueError("Fixture observation requires an explicit non-root target")
        expected = 5 if self.predicate_id == "toolkit-staged" else 6
        if self.producer_occurrence != expected:
            raise ValueError("Fixture predicate belongs to a different occurrence")
        return self


class TransferMeasurement(ImmutableRecord):
    passed: StrictBool
    content_sha256: Digest
    input_sha256: Digest
    target_executable: StrictBool
    http_get_recorded: StrictBool
    owner: Identity


class FixtureFile(ImmutableRecord):
    name: Literal["port_scanner.py", "service_enum.sh", "sys_profiler.py"]
    sha256: Digest
    size: Annotated[int, Field(strict=True, gt=0, le=MAX_FIXTURE_BYTES)]
    owner: Identity
    mode: str = Field(pattern=r"^[0-7]{3,4}$")
    executable: StrictBool


class ToolkitMeasurement(ImmutableRecord):
    passed: StrictBool
    files: Annotated[tuple[FixtureFile, ...], Field(min_length=3, max_length=3)]

    @model_validator(mode="after")
    def validate_complete_files(self) -> Self:
        if {entry.name for entry in self.files} != set(TOOLKIT_SHA256):
            raise ValueError(
                "Toolkit observation requires three distinct declared files"
            )
        return self


class GuestFixtureResult(ImmutableRecord):
    hostname: Identity
    principal: Identity
    observer_uid: Annotated[int, Field(strict=True, gt=0)]
    boot_id: Identity
    nonce: Identity
    measurement: TransferMeasurement | ToolkitMeasurement


def measurement_matches(
    request: C0045FixtureRequest, result: GuestFixtureResult
) -> bool:
    measurement = result.measurement
    if request.predicate_id == "loopback-transfer":
        return isinstance(measurement, TransferMeasurement) and (
            measurement.passed
            and measurement.content_sha256 == TRANSFER_SHA256
            and measurement.input_sha256 == TRANSFER_SHA256
            and measurement.target_executable
            and measurement.http_get_recorded
            and measurement.owner == request.scope.principal
        )
    return (
        isinstance(measurement, ToolkitMeasurement)
        and measurement.passed
        and all(
            entry.sha256 == TOOLKIT_SHA256[entry.name]
            and entry.executable
            and entry.owner == request.scope.principal
            for entry in measurement.files
        )
    )


def observe_c0045_fixture(request: C0045FixtureRequest) -> PredicateObservation:
    scope = request.scope
    _check_profile_principal(request.sut_profile_id, scope.host_id, scope.principal)
    source = PROBE_PATH.read_bytes()
    if len(source) > MAX_PROBE_BYTES:
        raise ValueError("C0045 fixture probe exceeds its source bound")
    code = (
        "import json; module={'__name__':'c0045_fixture_probe'}; "
        f"exec({source.decode('utf-8')!r},module); "
        f"print(json.dumps(module['collect_fixture_observation']({request.predicate_id!r},"
        f"{request.nonce!r}),sort_keys=True))"
    )
    process = run_bash_on_target_vm(
        request.sut_profile_id,
        f"python3 -c {shlex.quote(code)}",
        execution_user=scope.principal,
        timeout=TRANSPORT_TIMEOUT_SECONDS,
    )
    process.check_returncode()
    acquired = parse_guest_reply(process, GuestFixtureResult.model_validate_json)
    identity_matched = (
        acquired.hostname == scope.host_id
        and acquired.principal == scope.principal
        and acquired.boot_id == scope.epoch
        and acquired.nonce == request.nonce
    )
    passed = identity_matched and measurement_matches(request, acquired)
    product = (
        "toolkit:declared_files_staged"
        if request.predicate_id == "toolkit-staged"
        else "transfer:guest_loopback_verified"
    )
    return PredicateObservation(
        scope=scope,
        predicate_id=request.predicate_id,
        passed=passed,
        producer_occurrence=request.producer_occurrence,
        established_facts=(product,) if passed else (),
        details={
            "probe_sha256": hashlib.sha256(source).hexdigest(),
            "identity_matched": identity_matched,
            "measurement_json": acquired.measurement.model_dump_json(),
            "scope": "Retained fixtures, not producer identity, initial access or cross-host ingress",
        },
    )
