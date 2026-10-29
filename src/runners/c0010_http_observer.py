"""Code-owned authority for a live C0010 controller-loopback HTTP fetch."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord
from runners.capability_observations import PredicateObservation

_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts/probe_c0010_http.py"


@dataclass(frozen=True)
class HttpBodySpec:
    sha256: str
    size: int


_EXPECTED_BODIES = {
    "/index.html": HttpBodySpec(
        sha256="5796eda3761a4cf80e678cc0e128b004944067a6bef47db1f56b9eb28b4a60ab",
        size=93,
    ),
    "/exploit.js": HttpBodySpec(
        sha256="bb41e80403d21de048cfd23a2c00047853dad58896f8fead37aebf2c90605384",
        size=54,
    ),
}


class C0010HttpRequest(ImmutableRecord):
    sut_profile_id: Literal["0.c0010"]
    scope: FactScope
    nonce: Identity
    producer_occurrence: Literal[4]
    port: Annotated[int, Field(strict=True, gt=0, lt=65536)]

    @model_validator(mode="after")
    def validate_controller(self) -> Self:
        if (
            self.scope.locus != "controller"
            or self.scope.host_id != "controller"
            or self.scope.principal != str(os.geteuid())
            or self.scope.epoch != self.scope.run_id
        ):
            raise ValueError(
                "C0010 HTTP observation requires the live controller scope"
            )
        return self


class HttpResponse(ImmutableRecord):
    path: Identity
    status: Annotated[int, Field(strict=True)]
    body_sha256: Digest
    body_bytes: Annotated[int, Field(strict=True, ge=0, le=65537)]


class HttpProbeResult(ImmutableRecord):
    schema_version: Literal["c0010-loopback-http-probe/v1"] = Field(alias="schema")
    run_id: Identity
    nonce: Identity
    hostname: Identity
    uid: Annotated[int, Field(strict=True, ge=0)]
    port: Annotated[int, Field(strict=True, gt=0, lt=65536)]
    responses: tuple[HttpResponse, ...]
    passed: Annotated[bool, Field(strict=True)]


def _failed_checks(
    acquired: HttpProbeResult, request: C0010HttpRequest
) -> tuple[str, ...]:
    responses = {response.path: response for response in acquired.responses}
    checks = {
        "probe_passed": acquired.passed,
        "run": acquired.run_id == request.scope.run_id,
        "nonce": acquired.nonce == request.nonce,
        "hostname": acquired.hostname == socket.gethostname(),
        "principal": acquired.uid == os.geteuid(),
        "port": acquired.port == request.port,
        "paths": set(responses) == set(_EXPECTED_BODIES)
        and len(responses) == len(acquired.responses),
        "status": all(response.status == 200 for response in acquired.responses),
        "body_digest": all(
            responses[path].body_sha256 == specification.sha256
            for path, specification in _EXPECTED_BODIES.items()
            if path in responses
        ),
        "body_size": all(
            responses[path].body_bytes == specification.size
            for path, specification in _EXPECTED_BODIES.items()
            if path in responses
        ),
    }
    return tuple(name for name, passed in checks.items() if not passed)


def observe_c0010_http(request: C0010HttpRequest) -> PredicateObservation:
    """Probe only the live loopback server; never claim a target-browser visit."""
    source = _PROBE_PATH.read_bytes()
    if len(source) > 65536:
        raise ValueError("C0010 HTTP probe exceeds its source size bound")
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            str(_PROBE_PATH),
            "--port",
            str(request.port),
            "--run-id",
            request.scope.run_id,
            "--nonce",
            request.nonce,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    details: dict[str, str | int | bool] = {
        "returncode": result.returncode,
        "stderr": result.stderr[:8192],
        "probe_sha256": hashlib.sha256(source).hexdigest(),
        "port": request.port,
    }
    if result.returncode != 0:
        details["failed_checks"] = "probe_exit"
        return PredicateObservation(
            scope=request.scope,
            predicate_id="loopback-http-fetch",
            passed=False,
            established_facts=(),
            details=details,
            producer_occurrence=4,
        )
    acquired = HttpProbeResult.model_validate(json.loads(result.stdout))
    failed_checks = _failed_checks(acquired, request)
    passed = not failed_checks
    details["failed_checks"] = ",".join(failed_checks)
    details["response_count"] = len(acquired.responses)
    return PredicateObservation(
        scope=request.scope,
        predicate_id="loopback-http-fetch",
        passed=passed,
        established_facts=("controller:watering_hole_fetched",) if passed else (),
        details=details,
        producer_occurrence=4,
    )
