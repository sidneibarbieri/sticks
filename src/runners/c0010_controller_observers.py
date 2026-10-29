"""Code-owned controller observers for C0010's bounded staging effects."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord
from runners.capability_observations import PredicateObservation


_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_PROBE_PATH = _PROJECT_ROOT / "scripts/probe_c0010_controller.py"
_SPEC_PATH = _PROJECT_ROOT / "data/observer_specs/c0010_controller.json"
_SPEC_SHA256 = "c7df0ee24812edcc736835e99fb2558b85e675c345ea13d4899451ed7c210e73"
_MAX_SOURCE_BYTES = 65536
_PROBE_TIMEOUT_SECONDS = 20


class ExpectedControllerFile(ImmutableRecord):
    path: Identity
    utf8: str


class C0010PredicateDefinition(ImmutableRecord):
    predicate_id: Identity
    authority_id: Identity
    product: Identity
    occurrence: Annotated[int, Field(strict=True, gt=0)]
    files: tuple[ExpectedControllerFile, ...]


class C0010ControllerSpecification(ImmutableRecord):
    schema_version: Literal["c0010-controller-spec/v1"]
    predicates: tuple[C0010PredicateDefinition, ...]


@dataclass(frozen=True)
class ControllerPredicateSpec:
    authority_id: str
    product: str
    occurrence: int
    paths: frozenset[str]


def _load_predicates() -> MappingProxyType:
    source = _SPEC_PATH.read_bytes()
    if hashlib.sha256(source).hexdigest() != _SPEC_SHA256:
        raise ValueError("C0010 controller specification differs from reviewed bytes")
    document = C0010ControllerSpecification.model_validate_json(source)
    predicates = {}
    for entry in document.predicates:
        paths = frozenset(file.path for file in entry.files)
        if (
            entry.predicate_id in predicates
            or not paths
            or len(paths) != len(entry.files)
            or any(
                not path.startswith("data/artifacts/")
                or any(part in {"", ".", ".."} for part in path.split("/"))
                for path in paths
            )
        ):
            raise ValueError("Invalid C0010 controller predicate or path")
        predicates[entry.predicate_id] = ControllerPredicateSpec(
            authority_id=entry.authority_id,
            product=entry.product,
            occurrence=entry.occurrence,
            paths=paths,
        )
    if len(predicates) != 3:
        raise ValueError("C0010 controller predicate inventory changed")
    return MappingProxyType(predicates)


_PREDICATES = _load_predicates()


class C0010ControllerRequest(ImmutableRecord):
    """Bind one reviewed controller predicate to an occurrence and run scope."""

    sut_profile_id: Literal["0.c0010"]
    scope: FactScope
    nonce: Identity
    predicate_id: Identity
    producer_occurrence: Annotated[int, Field(strict=True, gt=0)]

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if (
            self.scope.locus != "controller"
            or self.scope.host_id != "controller"
            or self.scope.principal != str(os.geteuid())
            or self.scope.epoch != self.scope.run_id
        ):
            raise ValueError(
                "C0010 controller observation requires the live controller scope"
            )
        if self.predicate_id not in _PREDICATES:
            raise ValueError("Unknown C0010 controller predicate")
        if self.producer_occurrence != _PREDICATES[self.predicate_id].occurrence:
            raise ValueError("C0010 predicate does not match campaign occurrence")
        return self


class FileDigest(ImmutableRecord):
    path: Identity
    sha256: Digest


class ControllerProbeResult(ImmutableRecord):
    schema_version: Literal["c0010-controller-probe/v1"] = Field(alias="schema")
    predicate_id: Identity
    run_id: Identity
    nonce: Identity
    hostname: Identity
    uid: Annotated[int, Field(strict=True, ge=0)]
    passed: Annotated[bool, Field(strict=True)]
    content_sha256: Digest
    file_sha256: tuple[FileDigest, ...]


def controller_request(
    authority_id: str,
    scope: FactScope,
    nonce: str,
    occurrence: int,
) -> C0010ControllerRequest:
    for predicate_id, specification in _PREDICATES.items():
        if specification.authority_id == authority_id:
            return C0010ControllerRequest(
                sut_profile_id="0.c0010",
                scope=scope,
                nonce=nonce,
                predicate_id=predicate_id,
                producer_occurrence=occurrence,
            )
    raise ValueError("Unknown C0010 controller observation authority")


def _run_probe(
    request: C0010ControllerRequest,
) -> tuple[subprocess.CompletedProcess[str], Digest]:
    source = _PROBE_PATH.read_bytes()
    if len(source) > _MAX_SOURCE_BYTES:
        raise ValueError("C0010 controller probe exceeds its source size bound")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(_PROBE_PATH),
            "--root",
            str(_PROJECT_ROOT),
            "--predicate",
            request.predicate_id,
            "--spec-sha256",
            _SPEC_SHA256,
            "--run-id",
            request.scope.run_id,
            "--nonce",
            request.nonce,
        ],
        cwd=_PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=_PROBE_TIMEOUT_SECONDS,
    )
    return result, hashlib.sha256(source).hexdigest()


def _failed_checks(
    acquired: ControllerProbeResult,
    request: C0010ControllerRequest,
    specification: ControllerPredicateSpec,
) -> tuple[str, ...]:
    digests = {item.path: item.sha256 for item in acquired.file_sha256}
    encoded = json.dumps(digests, sort_keys=True, separators=(",", ":")).encode()
    checks = {
        "probe_passed": acquired.passed,
        "predicate": acquired.predicate_id == request.predicate_id,
        "run": acquired.run_id == request.scope.run_id,
        "nonce": acquired.nonce == request.nonce,
        "hostname": acquired.hostname == socket.gethostname(),
        "principal": acquired.uid == os.geteuid(),
        "paths": set(digests) == specification.paths
        and len(digests) == len(acquired.file_sha256),
        "content_digest": hashlib.sha256(encoded).hexdigest()
        == acquired.content_sha256,
    }
    return tuple(name for name, passed in checks.items() if not passed)


def observe_c0010_controller(request: C0010ControllerRequest) -> PredicateObservation:
    """Run a separate allowlisted probe; executor return values grant nothing."""
    specification = _PREDICATES[request.predicate_id]
    result, source_digest = _run_probe(request)
    details: dict[str, str | int | bool] = {
        "returncode": result.returncode,
        "stderr": result.stderr[:8192],
        "stderr_sha256": hashlib.sha256(result.stderr.encode()).hexdigest(),
        "probe_sha256": source_digest,
        "spec_sha256": _SPEC_SHA256,
    }
    if result.returncode != 0:
        details["failed_checks"] = "probe_exit"
        return PredicateObservation(
            scope=request.scope,
            predicate_id=request.predicate_id,
            passed=False,
            established_facts=(),
            details=details,
            producer_occurrence=request.producer_occurrence,
        )
    acquired = ControllerProbeResult.model_validate(json.loads(result.stdout))
    failed_checks = _failed_checks(acquired, request, specification)
    passed = not failed_checks
    details["failed_checks"] = ",".join(failed_checks)
    details["file_count"] = len(acquired.file_sha256)
    return PredicateObservation(
        scope=request.scope,
        predicate_id=request.predicate_id,
        passed=passed,
        established_facts=(specification.product,) if passed else (),
        details=details,
        content_sha256=acquired.content_sha256 if passed else None,
        producer_occurrence=request.producer_occurrence,
    )
