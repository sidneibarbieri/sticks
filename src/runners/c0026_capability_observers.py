"""Scope-bound C0026 guest observations using the shared standalone predicates."""

import hashlib
import json
import shlex
from pathlib import Path
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from executors.lab_transport import run_bash_on_target_vm
from runners.capability_facts import (
    Digest,
    FactScope,
    Identity,
    ImmutableRecord,
    ObservationReference,
)
from runners.capability_observations import PredicateObservation
from runners.runtime_diagnostics import parse_guest_reply
from runners.lab_bootstrap_observer import GuestShellIdentity, _check_profile_principal

_PREDICATES = MappingProxyType(
    {
        "collection-bytes": ("observe_collection", "collection:verified"),
        "archive-member": ("observe_archive", "archive:verified"),
        "archive-chunks": ("observe_chunks", "chunks:verified"),
        "benign-payload": ("observe_payload", "payload:verified"),
        "files-resolution": ("observe_files_resolution", "resolution:files_verified"),
    }
)
_PROBE_PATH = Path(__file__).resolve().parents[2] / "scripts/probe_c0026_target.py"
_AUTHORITIES = MappingProxyType(
    {
        "c0026-resolution": "files-resolution",
        "c0026-payload": "benign-payload",
        "c0026-collection": "collection-bytes",
        "c0026-archive": "archive-member",
        "c0026-chunks": "archive-chunks",
    }
)


class C0026EffectRequest(ImmutableRecord):
    """Select a literal guest predicate and expected acquisition scope."""

    sut_profile_id: Literal["0.c0026"]
    nonce: Identity
    scope: FactScope
    predicate_id: Literal[
        "collection-bytes",
        "archive-member",
        "archive-chunks",
        "benign-payload",
        "files-resolution",
    ]
    producer_occurrence: Annotated[int, Field(strict=True, gt=0)] | None = None
    expected_input_sha256: Digest | None = None
    consumer_occurrence: Annotated[int, Field(strict=True, gt=0)] | None = None
    revalidated_reference: ObservationReference | None = None

    @model_validator(mode="after")
    def validate_scope(self) -> Self:
        if (self.consumer_occurrence is None) != (self.revalidated_reference is None):
            raise ValueError(
                "Revalidation request requires consumer and original acquisition"
            )
        if self.consumer_occurrence is not None and (
            self.producer_occurrence is None
            or self.consumer_occurrence <= self.producer_occurrence
        ):
            raise ValueError("Revalidation consumer must follow its producer")
        if self.scope.locus != "target" or self.scope.principal in {None, "root"}:
            raise ValueError(
                "Effect observation requires an explicit non-root target principal"
            )
        return self


class GuestEffectIdentity(GuestShellIdentity):
    predicate_id: Identity
    passed: Annotated[bool, Field(strict=True)]
    measurements: dict[str, str | int | bool] = Field(default_factory=dict)


def effect_request(
    authority_id: str,
    scope: FactScope,
    nonce: str,
    producer_occurrence: int | None,
    expected_input_sha256: str | None = None,
    *,
    consumer_occurrence: int | None = None,
    revalidated_reference: ObservationReference | None = None,
) -> C0026EffectRequest:
    if authority_id not in _AUTHORITIES:
        raise ValueError("Unknown C0026 observation authority")
    return C0026EffectRequest(
        sut_profile_id="0.c0026",
        scope=scope,
        nonce=nonce,
        predicate_id=_AUTHORITIES[authority_id],
        producer_occurrence=producer_occurrence,
        expected_input_sha256=expected_input_sha256,
        consumer_occurrence=consumer_occurrence,
        revalidated_reference=revalidated_reference,
    )


def _guest_script(request: C0026EffectRequest, source: str) -> str:
    predicate, _ = _PREDICATES[request.predicate_id]
    measurement_code = (
        f"measurements=module['measure_files_resolution'](pathlib.Path('/'),{request.nonce!r}); "
        "passed=measurements['passed']; "
        if request.predicate_id == "files-resolution"
        else f"measurements=module[{predicate.replace('observe_', 'measure_')!r}](pathlib.Path('/')); passed=measurements['passed']; "
    )
    code = (
        "import json,os,pathlib,pwd,socket; "
        "module={'__name__':'c0026_predicates'}; "
        f"exec({source!r},module); "
        f"{measurement_code}"
        "print(json.dumps(dict(hostname=socket.gethostname(), "
        "principal=pwd.getpwuid(os.geteuid()).pw_name, "
        "boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(), "
        f"nonce={request.nonce!r},predicate_id={request.predicate_id!r},passed=passed,measurements=measurements)))"
    )
    return f"python3 -c {shlex.quote(code)}"


def _resolution_proof_matches(measurements: dict, nonce: str) -> bool:
    positive = measurements.get("positive_stdout")
    if not isinstance(positive, str):
        return False
    rows = [line.split() for line in positive.splitlines()]
    expected_absent = (
        f"absent-{hashlib.sha256(nonce.encode()).hexdigest()[:20]}.invalid"
    )
    return (
        measurements.get("hosts_mapping") is True
        and measurements.get("passed") is True
        and type(measurements.get("positive_returncode")) is int
        and measurements["positive_returncode"] == 0
        and bool(rows)
        and all(row[0] == "127.0.0.1" and "c2.dynamic.local" in row[1:] for row in rows)
        and type(measurements.get("negative_returncode")) is int
        and measurements["negative_returncode"] == 2
        and measurements.get("negative_name") == expected_absent
        and measurements.get("negative_stdout") == ""
        and measurements.get("negative_stderr") == ""
        and measurements.get("positive_stderr") == ""
    )


def observe_c0026_effect(request: C0026EffectRequest) -> PredicateObservation:
    """Observe one bounded fixture effect, with no external-transfer claim."""
    scope = request.scope
    _check_profile_principal(request.sut_profile_id, scope.host_id, scope.principal)
    source_bytes = _PROBE_PATH.read_bytes()
    if len(source_bytes) > 65536:
        raise ValueError("Shared guest predicate source exceeds its deployment bound")
    result = run_bash_on_target_vm(
        request.sut_profile_id,
        _guest_script(request, source_bytes.decode("utf-8")),
        execution_user=scope.principal,
        timeout=20,
    )
    details = {
        "returncode": result.returncode,
        "stderr": result.stderr,
        "predicate_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    passed = False
    if result.returncode == 0:
        acquired = parse_guest_reply(
            result,
            lambda content: GuestEffectIdentity.model_validate(json.loads(content)),
        )
        expected = GuestEffectIdentity(
            hostname=scope.host_id,
            principal=scope.principal,
            boot_id=scope.epoch,
            nonce=request.nonce,
            predicate_id=request.predicate_id,
            passed=True,
            measurements=acquired.measurements,
        )
        passed = acquired == expected
        if request.predicate_id == "files-resolution":
            passed = passed and _resolution_proof_matches(
                acquired.measurements, request.nonce
            )
        elif request.producer_occurrence is not None:
            content_digest = acquired.measurements.get("content_sha256")
            passed = (
                passed and isinstance(content_digest, str) and len(content_digest) == 64
            )
        if request.expected_input_sha256 is not None:
            passed = (
                passed
                and acquired.measurements.get("input_sha256")
                == request.expected_input_sha256
            )
        details.update(
            {f"nss_{name}": value for name, value in acquired.measurements.items()}
        )
    return PredicateObservation(
        scope=scope,
        predicate_id=request.predicate_id,
        passed=passed,
        established_facts=(_PREDICATES[request.predicate_id][1],) if passed else (),
        details=details,
        content_sha256=acquired.measurements.get("content_sha256")
        if result.returncode == 0
        else None,
        producer_occurrence=request.producer_occurrence,
        consumer_occurrence=request.consumer_occurrence,
        revalidated_reference=request.revalidated_reference,
    )
