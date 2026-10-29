"""Registered, scope-bound observation of the synthetic Ray-like API."""

import hashlib
import shlex
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, model_validator

from executors.lab_transport import run_bash_on_target_vm
from runners.c0045_api_contract import MAX_RESPONSE_BYTES, responses_match
from runners.capability_facts import FactScope, Identity, ImmutableRecord
from runners.capability_observations import PredicateObservation
from runners.lab_bootstrap_observer import _check_profile_principal
from runners.runtime_diagnostics import parse_guest_reply

PROBE_PATH = Path(__file__).resolve().parents[2]/'scripts/probe_c0045_api.py'
MAX_PROBE_BYTES = 65536
TRANSPORT_TIMEOUT_SECONDS = 15


class C0045ApiRequest(ImmutableRecord):
    sut_profile_id: Literal['0.shadowray']
    nonce: Identity
    scope: FactScope
    producer_occurrence: Annotated[int, Field(strict=True, ge=1, le=1)]

    @model_validator(mode='after')
    def validate_target_scope(self) -> Self:
        if self.scope.locus != 'target' or self.scope.principal in {None,'root'}:
            raise ValueError('API observation requires an explicit non-root target')
        return self


class GuestApiResult(ImmutableRecord):
    hostname: Identity
    principal: Identity
    observer_uid: Annotated[int,Field(strict=True,gt=0)]
    boot_id: Identity
    nonce: Identity
    version_body: str = Field(max_length=MAX_RESPONSE_BYTES)
    jobs_body: str = Field(max_length=MAX_RESPONSE_BYTES)
    passed: StrictBool


def observe_c0045_api(request: C0045ApiRequest) -> PredicateObservation:
    """Observe fixture responses only; a passed service probe grants no access."""
    scope = request.scope
    _check_profile_principal(request.sut_profile_id,scope.host_id,scope.principal)
    source = PROBE_PATH.read_bytes()
    if len(source) > MAX_PROBE_BYTES:
        raise ValueError('C0045 API probe exceeds its source size bound')
    code = ("import json; module={'__name__':'c0045_api_probe'}; "
        f"exec({source.decode('utf-8')!r},module); "
        f"print(json.dumps(module['collect_observation']({request.nonce!r}),sort_keys=True))")
    result = run_bash_on_target_vm(request.sut_profile_id,f'python3 -c {shlex.quote(code)}',
        execution_user=scope.principal,timeout=TRANSPORT_TIMEOUT_SECONDS)
    result.check_returncode()
    acquired = parse_guest_reply(result,GuestApiResult.model_validate_json)
    identity_matched = (acquired.hostname == scope.host_id and acquired.principal == scope.principal
        and acquired.boot_id == scope.epoch and acquired.nonce == request.nonce)
    matched = responses_match(acquired.version_body,acquired.jobs_body)
    passed = identity_matched and matched
    return PredicateObservation(scope=scope,predicate_id='ray-fixture-api',passed=passed,
        established_facts=('service:ray_fixture_responses',) if passed else (),
        producer_occurrence=request.producer_occurrence,
        details={'probe_sha256':hashlib.sha256(source).hexdigest(),
            'identity_matched':identity_matched,'version_body':acquired.version_body,
            'jobs_body':acquired.jobs_body,'scope':'Fixture responses, not exploitation or initial access'})
