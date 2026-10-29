"""Independent, scope-bound observations of CostaRicto guest file effects."""

import hashlib
import json
from pathlib import Path
import shlex
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from executors.lab_transport import run_bash_on_target_vm
from runners.capability_facts import FactScope, Identity, ImmutableRecord
from runners.capability_observations import PredicateObservation
from runners.lab_bootstrap_observer import GuestShellIdentity, _check_profile_principal
from runners.runtime_diagnostics import parse_guest_reply


_PROBE_PATH = (
    Path(__file__).resolve().parents[2] / "scripts/probe_costaricto_effects.py"
)
_PRODUCTS = {
    "local-service-listing": (
        1,
        "discovery:declared_guest_listeners_recorded",
        "measure_discovery",
    ),
    "benign-transfer": (2, "transfer:guest_loopback_verified", "measure_transfer"),
    "local-collection": (9, "collection:fixture_copy_verified", "measure_collection"),
}
_AUTHORITY_PREDICATES = {
    "costaricto-discovery": "local-service-listing",
    "costaricto-transfer": "benign-transfer",
    "costaricto-collection": "local-collection",
}


class CostaRictoEffectRequest(ImmutableRecord):
    """Bind one fixed predicate to the producer, run, guest and fresh challenge."""

    sut_profile_id: Literal["0.costaricto"]
    scope: FactScope
    nonce: Identity
    predicate_id: Literal[
        "local-service-listing", "benign-transfer", "local-collection"
    ]
    producer_occurrence: Annotated[int, Field(strict=True, gt=0)]

    @model_validator(mode="after")
    def validate_target(self) -> Self:
        if (
            self.scope.locus != "target"
            or self.scope.host_id != "target-linux-1"
            or self.scope.principal != "reconuser"
        ):
            raise ValueError("CostaRicto effect requires its declared non-root guest")
        if self.producer_occurrence != _PRODUCTS[self.predicate_id][0]:
            raise ValueError(
                "CostaRicto predicate differs from its producing occurrence"
            )
        return self


class GuestEffectReply(GuestShellIdentity):
    predicate_id: Identity
    passed: Annotated[bool, Field(strict=True)]
    measurements: dict[str, str | bool]


def costaricto_effect_request(
    authority_id: str,
    scope: FactScope,
    nonce: Identity,
    producer_occurrence: int,
) -> CostaRictoEffectRequest:
    """Construct only the fixed authority-to-predicate mapping."""
    if authority_id not in _AUTHORITY_PREDICATES:
        raise ValueError("Unknown CostaRicto observation authority")
    return CostaRictoEffectRequest(
        sut_profile_id="0.costaricto",
        scope=scope,
        nonce=nonce,
        predicate_id=_AUTHORITY_PREDICATES[authority_id],
        producer_occurrence=producer_occurrence,
    )


def _guest_script(request: CostaRictoEffectRequest, source: str) -> str:
    measure_name = _PRODUCTS[request.predicate_id][2]
    code = (
        "import json,os,pathlib,pwd,socket; "
        "module={'__name__':'costaricto_predicates'}; "
        f"exec({source!r},module); "
        f"measurements=module[{measure_name!r}](pathlib.Path('/')); "
        "print(json.dumps(dict(hostname=socket.gethostname(), "
        "principal=pwd.getpwuid(os.geteuid()).pw_name, "
        "boot_id=pathlib.Path('/proc/sys/kernel/random/boot_id').read_text().strip(), "
        f"nonce={request.nonce!r},predicate_id={request.predicate_id!r}, "
        "passed=measurements['passed'],measurements=measurements)))"
    )
    return f"python3 -c {shlex.quote(code)}"


def observe_costaricto_effect(
    request: CostaRictoEffectRequest,
) -> PredicateObservation:
    """Acquire a fresh guest measurement after the selected occurrence completes."""
    _check_profile_principal(
        request.sut_profile_id, request.scope.host_id, request.scope.principal
    )
    source_bytes = _PROBE_PATH.read_bytes()
    if len(source_bytes) > 65536:
        raise ValueError("Guest predicate source exceeds deployment bound")
    result = run_bash_on_target_vm(
        request.sut_profile_id,
        _guest_script(request, source_bytes.decode("utf-8")),
        execution_user=request.scope.principal,
        timeout=20,
    )
    details: dict[str, str | int | bool] = {
        "returncode": result.returncode,
        "stderr": result.stderr,
        "predicate_source_sha256": hashlib.sha256(source_bytes).hexdigest(),
    }
    passed = False
    content_sha256 = None
    if result.returncode == 0:
        acquired = parse_guest_reply(
            result,
            lambda content: GuestEffectReply.model_validate(json.loads(content)),
        )
        expected = GuestEffectReply(
            hostname=request.scope.host_id,
            principal=request.scope.principal,
            boot_id=request.scope.epoch,
            nonce=request.nonce,
            predicate_id=request.predicate_id,
            passed=True,
            measurements=acquired.measurements,
        )
        content_sha256 = acquired.measurements.get("content_sha256")
        passed = (
            acquired == expected
            and acquired.measurements.get("passed") is True
            and isinstance(content_sha256, str)
            and len(content_sha256) == 64
            and acquired.measurements.get("input_sha256") == content_sha256
        )
        details.update(acquired.measurements)
    return PredicateObservation(
        scope=request.scope,
        predicate_id=request.predicate_id,
        passed=passed,
        established_facts=(_PRODUCTS[request.predicate_id][1],) if passed else (),
        details=details,
        content_sha256=content_sha256 if passed else None,
        producer_occurrence=request.producer_occurrence,
    )
