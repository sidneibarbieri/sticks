"""Scope-bound C0010 observation of the benign target transfer."""

from __future__ import annotations

import hashlib
import json
import shlex
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from executors.lab_transport import run_bash_on_target_vm
from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord
from runners.capability_observations import PredicateObservation
from runners.lab_bootstrap_observer import _check_profile_principal
from runners.runtime_diagnostics import parse_guest_reply

_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts/probe_c0010_target.py"
_PAYLOAD_SHA256 = "b088ddaef2625e7f19f1ef1031b8af0617d4e849134d367bde139c77b7ad7be9"
_CHECKS = frozenset(
    {
        "declared_notice_present",
        "declared_page_present",
        "transfer_matches_source",
        "http_get_recorded",
        "download_executable",
    }
)
_MAX_PROBE_BYTES = 65536
_PROBE_TIMEOUT_SECONDS = 20


class C0010FixtureReadiness(ImmutableRecord):
    hostname: Identity
    principal: Identity
    observer_uid: Annotated[int, Field(strict=True, gt=0)]
    boot_id: Identity
    nonce: Identity
    notice_matches: StrictBool
    page_matches: StrictBool


def require_c0010_fixture_readiness(scope: FactScope, nonce: str) -> C0010FixtureReadiness:
    """Fail before campaign actions; this check grants no runtime capabilities."""
    if scope.locus != "target":
        raise ValueError("C0010 readiness requires target scope")
    _check_profile_principal("0.c0010", scope.host_id, scope.principal)
    source = _PROBE_PATH.read_bytes()
    if len(source) > _MAX_PROBE_BYTES:
        raise ValueError("C0010 readiness probe exceeds its size bound")
    code = (
        "import json,pathlib,pwd,os,socket; module={'__name__':'c0010_preflight'}; "
        f"exec({source.decode('utf-8')!r},module); "
        "result=module['collect_fixture_readiness'](pathlib.Path('/')); "
        "result.update(hostname=socket.gethostname(),principal=pwd.getpwuid(os.geteuid()).pw_name,"
        "observer_uid=os.geteuid(),boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(),"
        f"nonce={nonce!r}); print(json.dumps(result,sort_keys=True))"
    )
    result = run_bash_on_target_vm("0.c0010", f"python3 -c {shlex.quote(code)}",
        execution_user=scope.principal, timeout=_PROBE_TIMEOUT_SECONDS)
    result.check_returncode()
    readiness = parse_guest_reply(result, C0010FixtureReadiness.model_validate_json)
    if (readiness.hostname != scope.host_id or readiness.principal != scope.principal
            or readiness.boot_id != scope.epoch or readiness.nonce != nonce
            or not readiness.notice_matches or not readiness.page_matches):
        raise ValueError("C0010 readiness failed: guest identity or declared fixture mismatch")
    return readiness


class C0010TransferRequest(ImmutableRecord):
    """Bind the transfer predicate to the declared guest and ninth occurrence."""

    sut_profile_id: Literal["0.c0010"]
    scope: FactScope
    nonce: Identity
    producer_occurrence: Literal[9]

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if self.scope.locus != "target" or self.scope.principal in {None, "root"}:
            raise ValueError("C0010 transfer requires a non-root target scope")
        return self


class GuestTransferResult(ImmutableRecord):
    schema_version: Literal["c0010-target-transfer-observation/v1"] = Field(
        alias="schema"
    )
    hostname: Identity
    principal: Identity
    observer_uid: Annotated[int, Field(strict=True, gt=0)]
    boot_id: Identity
    nonce: Identity
    payload_sha256: Digest
    checks: dict[str, StrictBool]
    passed: Annotated[bool, Field(strict=True)]
    scope_note: str = Field(alias="scope")


def _guest_script(nonce: str, source: str) -> str:
    code = (
        "import json,pathlib,pwd,os; "
        "module={'__name__':'c0010_probe'}; "
        f"exec({source!r},module); "
        "observation=module['collect_observation'](pathlib.Path('/')); "
        "observation['principal']=pwd.getpwuid(os.geteuid()).pw_name; "
        f"observation['nonce']={nonce!r}; "
        "print(json.dumps(observation,sort_keys=True))"
    )
    return f"python3 -c {shlex.quote(code)}"


def observe_c0010_transfer(request: C0010TransferRequest) -> PredicateObservation:
    """Grant only the bounded guest transfer after an independent probe."""
    scope = request.scope
    _check_profile_principal(request.sut_profile_id, scope.host_id, scope.principal)
    source = _PROBE_PATH.read_bytes()
    if len(source) > _MAX_PROBE_BYTES:
        raise ValueError("C0010 guest probe exceeds its source size bound")
    result = run_bash_on_target_vm(
        request.sut_profile_id,
        _guest_script(request.nonce, source.decode("utf-8")),
        execution_user=scope.principal,
        timeout=_PROBE_TIMEOUT_SECONDS,
    )
    details: dict[str, str | int | bool] = {
        "returncode": result.returncode,
        "stderr": result.stderr,
        "probe_sha256": hashlib.sha256(source).hexdigest(),
    }
    if result.returncode != 0:
        return PredicateObservation(
            scope=scope,
            predicate_id="benign-transfer",
            passed=False,
            established_facts=(),
            details=details,
            producer_occurrence=9,
        )
    acquired = parse_guest_reply(
        result, lambda content: GuestTransferResult.model_validate(json.loads(content))
    )
    passed = (
        acquired.passed
        and acquired.hostname == scope.host_id
        and acquired.principal == scope.principal
        and acquired.boot_id == scope.epoch
        and acquired.nonce == request.nonce
        and acquired.payload_sha256 == _PAYLOAD_SHA256
        and set(acquired.checks) == _CHECKS
        and all(acquired.checks.values())
    )
    details.update({f"check_{name}": value for name, value in acquired.checks.items()})
    details["identity_matched"] = (
        acquired.hostname == scope.host_id
        and acquired.principal == scope.principal
        and acquired.boot_id == scope.epoch
        and acquired.nonce == request.nonce
    )
    return PredicateObservation(
        scope=scope,
        predicate_id="benign-transfer",
        passed=passed,
        established_facts=("target:benign_payload_transferred",) if passed else (),
        details=details,
        content_sha256=acquired.payload_sha256 if passed else None,
        producer_occurrence=9,
    )
