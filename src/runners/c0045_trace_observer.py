"""Registered acquisition of trusted, scope-bound C0045 kernel traces."""

import hashlib
import shlex
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from executors.c0045_readonly_commands import TraceKind, TraceNonce, command_spec
from executors.lab_transport import run_bash_on_target_vm
from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord
from runners.capability_observations import PredicateObservation
from runners.guest_execution_trace import MAX_TRACE_BYTES, assess_execution_trace
from runners.lab_bootstrap_observer import _check_profile_principal
from runners.runtime_diagnostics import parse_guest_reply

PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts/probe_shadowray_target.py"
MAX_PROBE_BYTES = 65536
TRANSPORT_TIMEOUT_SECONDS = 15
# A trace is bounded before it crosses the guest boundary.  JSON escaping can
# expand a UTF-8 trace, so the reply limit must not reuse the raw-trace limit.
MAX_GUEST_TRACE_REPLY_BYTES = (MAX_TRACE_BYTES * 6) + 8192


class C0045TraceRequest(ImmutableRecord):
    sut_profile_id: Literal["0.shadowray"]
    kind: TraceKind
    nonce: TraceNonce
    scope: FactScope
    producer_occurrence: Annotated[int, Field(strict=True, ge=7, le=8)]

    @property
    def predicate_id(self) -> str:
        return command_spec(self.kind).predicate_id

    @model_validator(mode="after")
    def validate_occurrence(self) -> Self:
        if self.producer_occurrence != command_spec(self.kind).occurrence:
            raise ValueError("Trace request belongs to a different occurrence")
        if self.scope.locus != "target" or self.scope.principal in {None, "root"}:
            raise ValueError("Trace requires an explicit non-root target principal")
        return self


class GuestTraceResult(ImmutableRecord):
    hostname: Identity
    principal: Identity
    observer_uid: Annotated[int, Field(strict=True, gt=0)]
    boot_id: Identity
    nonce: TraceNonce
    owner: Identity
    trace: str = Field(min_length=1, max_length=MAX_TRACE_BYTES)
    trace_sha256: Digest


def observe_c0045_trace(request: C0045TraceRequest) -> PredicateObservation:
    scope = request.scope
    _check_profile_principal(request.sut_profile_id, scope.host_id, scope.principal)
    source = PROBE_PATH.read_bytes()
    if len(source) > MAX_PROBE_BYTES:
        raise ValueError("Execution trace probe exceeds its source bound")
    code = (
        "import json; module={'__name__':'execution_trace_probe'}; "
        f"exec({source.decode('utf-8')!r},module); "
        f"print(json.dumps(module['collect_execution_trace']({request.nonce!r}),sort_keys=True))"
    )
    process = run_bash_on_target_vm(
        request.sut_profile_id,
        f"python3 -c {shlex.quote(code)}",
        execution_user=scope.principal,
        timeout=TRANSPORT_TIMEOUT_SECONDS,
    )
    process.check_returncode()
    acquired = parse_guest_reply(
        process,
        GuestTraceResult.model_validate_json,
        maximum_bytes=MAX_GUEST_TRACE_REPLY_BYTES,
    )
    spec = command_spec(request.kind)
    digest = hashlib.sha256(acquired.trace.encode()).hexdigest()
    identity_matched = (
        acquired.hostname == scope.host_id
        and acquired.principal == scope.principal
        and acquired.owner == scope.principal
        and acquired.boot_id == scope.epoch
        and acquired.nonce == request.nonce
    )
    assessment = assess_execution_trace(
        acquired.trace, expected_script=spec.script, kind=request.kind
    )
    passed = (
        identity_matched and digest == acquired.trace_sha256 and assessment.accepted
    )
    return PredicateObservation(
        scope=scope,
        predicate_id=spec.predicate_id,
        passed=passed,
        producer_occurrence=request.producer_occurrence,
        content_sha256=digest,
        established_facts=(spec.product,) if passed else (),
        details={
            "trace": acquired.trace,
            "nonce": request.nonce,
            "guest_nonce": acquired.nonce,
            "guest_hostname": acquired.hostname,
            "guest_principal": acquired.principal,
            "guest_owner": acquired.owner,
            "guest_boot_id": acquired.boot_id,
            "guest_observer_uid": acquired.observer_uid,
            "identity_matched": identity_matched,
            "trace_sha256": acquired.trace_sha256,
            "command_sha256": hashlib.sha256(spec.script.encode()).hexdigest(),
            "probe_sha256": hashlib.sha256(source).hexdigest(),
            "assessment_json": assessment.model_dump_json(),
            "scope": "Trusted tracer replay, not adversarial guest attestation or historical fidelity",
        },
    )


def verify_c0045_trace_observation(
    observation: PredicateObservation, *, run_root: Path
) -> None:
    """Recompute the stored verdict from its raw trace and scoped guest identity."""
    kinds = [
        kind
        for kind in ("python", "network")
        if command_spec(kind).predicate_id == observation.predicate_id
    ]
    if len(kinds) != 1:
        raise ValueError("Retained trace has an unknown predicate")
    details = observation.details
    request = C0045TraceRequest(
        sut_profile_id="0.shadowray",
        kind=kinds[0],
        nonce=details["nonce"],
        scope=observation.scope,
        producer_occurrence=observation.producer_occurrence,
    )
    acquired = GuestTraceResult.model_validate(
        {
            "hostname": details["guest_hostname"],
            "principal": details["guest_principal"],
            "observer_uid": details["guest_observer_uid"],
            "boot_id": details["guest_boot_id"],
            "nonce": details["guest_nonce"],
            "owner": details["guest_owner"],
            "trace": details["trace"],
            "trace_sha256": details["trace_sha256"],
        }
    )
    spec = command_spec(request.kind)
    digest = hashlib.sha256(acquired.trace.encode()).hexdigest()
    scope = request.scope
    identity_matched = (
        acquired.hostname == scope.host_id
        and acquired.principal == scope.principal
        and acquired.owner == scope.principal
        and acquired.boot_id == scope.epoch
        and acquired.nonce == request.nonce
    )
    assessment = assess_execution_trace(
        acquired.trace, expected_script=spec.script, kind=request.kind
    )
    passed = (
        identity_matched and digest == acquired.trace_sha256 and assessment.accepted
    )
    if (
        observation.passed != passed
        or observation.content_sha256 != digest
        or observation.established_facts != ((spec.product,) if passed else ())
        or details["identity_matched"] != identity_matched
        or details["assessment_json"] != assessment.model_dump_json()
        or details["command_sha256"] != hashlib.sha256(spec.script.encode()).hexdigest()
    ):
        raise ValueError("Retained trace verdict differs from its raw acquisition")
