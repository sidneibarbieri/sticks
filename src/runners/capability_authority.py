"""Literal observer dispatch and trusted-controller acquisition bindings."""

import hashlib
import inspect
import json
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Self

from pydantic import model_validator

from runners.capability_facts import (
    FactScope,
    Identity,
    ImmutableRecord,
    ObservationReference,
)
from runners.capability_observations import (
    PredicateObservation,
    _directory,
    _ensure_directory,
    _read_record,
    _write_exclusive,
    retain_observation,
    verify_observation_reference,
)
from runners.lab_bootstrap_observer import observe_lab_shell
from runners.c0010_controller_observers import (
    C0010ControllerRequest,
    observe_c0010_controller,
)
from runners.c0010_guest_observer import C0010TransferRequest, observe_c0010_transfer
from runners.c0010_http_observer import C0010HttpRequest, observe_c0010_http
from runners.c0026_capability_observers import C0026EffectRequest, observe_c0026_effect
from runners.costaricto_capability_observers import (
    CostaRictoEffectRequest,
    observe_costaricto_effect,
)
from runners.c0045_compute_observer import (
    C0045ComputeRequest,
    observe_c0045_compute,
    verify_c0045_compute_observation,
)
from runners.c0045_api_observer import C0045ApiRequest, observe_c0045_api
from runners.c0045_fixture_observer import C0045FixtureRequest, observe_c0045_fixture
from runners.c0045_trace_observer import C0045TraceRequest, observe_c0045_trace, verify_c0045_trace_observation
from executors.c0045_readonly_commands import command_spec


class LabShellRequest(ImmutableRecord):
    """Bind the expected guest scope and fresh bootstrap challenge."""

    sut_profile_id: Identity
    scope: FactScope
    nonce: Identity

    @model_validator(mode="after")
    def validate_target_scope(self) -> Self:
        if self.scope.locus != "target" or self.scope.principal in {None, "root"}:
            raise ValueError(
                "Lab shell observation requires an explicit non-root target principal"
            )
        return self


def _observe_shell(request: LabShellRequest) -> PredicateObservation:
    scope = request.scope
    return observe_lab_shell(
        sut_profile_id=request.sut_profile_id,
        expected_host_id=scope.host_id,
        principal=scope.principal,
        run_id=scope.run_id,
        environment_id=scope.environment_id,
        epoch=scope.epoch,
        nonce=request.nonce,
    )


@dataclass(frozen=True)
class ObserverRegistration:
    """Code-owned observer identity, predicate and permitted products."""

    predicate_id: str
    products: frozenset[str]
    acquire: Callable[..., PredicateObservation]
    request_model: type[ImmutableRecord] = LabShellRequest
    requires_run_root: bool = False
    verify_acquisition: Callable[..., None] | None = None
    supplemental_sources: tuple[str, ...] = ()


_OBSERVERS = MappingProxyType(
    {
        "lab-shell": ObserverRegistration(
            "shell-nonce", frozenset({"lab:shell"}), _observe_shell
        ),
        "c0010-payload": ObserverRegistration(
            "payload-staged",
            frozenset({"controller:payload_staged"}),
            observe_c0010_controller,
            C0010ControllerRequest,
            supplemental_sources=("scripts/probe_c0010_controller.py", "data/observer_specs/c0010_controller.json"),
        ),
        "c0010-page": ObserverRegistration(
            "watering-hole-staged",
            frozenset({"controller:watering_hole_staged"}),
            observe_c0010_controller,
            C0010ControllerRequest,
            supplemental_sources=("scripts/probe_c0010_controller.py", "data/observer_specs/c0010_controller.json"),
        ),
        "c0010-tool": ObserverRegistration(
            "tool-staged",
            frozenset({"controller:tool_staged"}),
            observe_c0010_controller,
            C0010ControllerRequest,
            supplemental_sources=("scripts/probe_c0010_controller.py", "data/observer_specs/c0010_controller.json"),
        ),
        "c0010-transfer": ObserverRegistration(
            "benign-transfer",
            frozenset({"target:benign_payload_transferred"}),
            observe_c0010_transfer,
            C0010TransferRequest,
            supplemental_sources=("scripts/probe_c0010_target.py",),
        ),
        "c0010-http": ObserverRegistration(
            "loopback-http-fetch",
            frozenset({"controller:watering_hole_fetched"}),
            observe_c0010_http,
            C0010HttpRequest,
            supplemental_sources=("scripts/probe_c0010_http.py",),
        ),
        "c0026-collection": ObserverRegistration(
            "collection-bytes",
            frozenset({"collection:verified"}),
            observe_c0026_effect,
            C0026EffectRequest,
            supplemental_sources=("scripts/probe_c0026_target.py",),
        ),
        "c0026-archive": ObserverRegistration(
            "archive-member",
            frozenset({"archive:verified"}),
            observe_c0026_effect,
            C0026EffectRequest,
            supplemental_sources=("scripts/probe_c0026_target.py",),
        ),
        "c0026-chunks": ObserverRegistration(
            "archive-chunks",
            frozenset({"chunks:verified"}),
            observe_c0026_effect,
            C0026EffectRequest,
            supplemental_sources=("scripts/probe_c0026_target.py",),
        ),
        "c0026-payload": ObserverRegistration(
            "benign-payload",
            frozenset({"payload:verified"}),
            observe_c0026_effect,
            C0026EffectRequest,
            supplemental_sources=("scripts/probe_c0026_target.py",),
        ),
        "c0026-resolution": ObserverRegistration(
            "files-resolution",
            frozenset({"resolution:files_verified"}),
            observe_c0026_effect,
            C0026EffectRequest,
            supplemental_sources=("scripts/probe_c0026_target.py",),
        ),
        "costaricto-transfer": ObserverRegistration(
            "benign-transfer",
            frozenset({"transfer:guest_loopback_verified"}),
            observe_costaricto_effect,
            CostaRictoEffectRequest,
            supplemental_sources=("scripts/probe_costaricto_effects.py",),
        ),
        "costaricto-discovery": ObserverRegistration(
            "local-service-listing",
            frozenset({"discovery:declared_guest_listeners_recorded"}),
            observe_costaricto_effect,
            CostaRictoEffectRequest,
            supplemental_sources=("scripts/probe_costaricto_effects.py",),
        ),
        "costaricto-collection": ObserverRegistration(
            "local-collection",
            frozenset({"collection:fixture_copy_verified"}),
            observe_costaricto_effect,
            CostaRictoEffectRequest,
            supplemental_sources=("scripts/probe_costaricto_effects.py",),
        ),
        "c0045-python": ObserverRegistration(
            command_spec("python").predicate_id, frozenset({command_spec("python").product}),
            observe_c0045_trace, C0045TraceRequest,
            verify_acquisition=verify_c0045_trace_observation,
            supplemental_sources=("scripts/probe_shadowray_target.py", "src/executors/c0045_readonly_commands.py", "src/runners/guest_execution_trace.py"),
        ),
        "c0045-network": ObserverRegistration(
            command_spec("network").predicate_id, frozenset({command_spec("network").product}),
            observe_c0045_trace, C0045TraceRequest,
            verify_acquisition=verify_c0045_trace_observation,
            supplemental_sources=("scripts/probe_shadowray_target.py", "src/executors/c0045_readonly_commands.py", "src/runners/guest_execution_trace.py"),
        ),
        "c0045-toolkit": ObserverRegistration(
            "toolkit-staged", frozenset({"toolkit:declared_files_staged"}),
            observe_c0045_fixture, C0045FixtureRequest,
            supplemental_sources=("scripts/probe_shadowray_target.py",),
        ),
        "c0045-transfer": ObserverRegistration(
            "loopback-transfer", frozenset({"transfer:guest_loopback_verified"}),
            observe_c0045_fixture, C0045FixtureRequest,
            supplemental_sources=("scripts/probe_shadowray_target.py",),
        ),
        "c0045-api": ObserverRegistration(
            "ray-fixture-api",
            frozenset({"service:ray_fixture_responses"}),
            observe_c0045_api,
            C0045ApiRequest,
            supplemental_sources=("scripts/probe_c0045_api.py",),
        ),
        "c0045-compute": ObserverRegistration(
            "bounded-guest-cpu",
            frozenset({"compute:bounded_guest_cpu"}),
            observe_c0045_compute,
            C0045ComputeRequest,
            requires_run_root=True,
            verify_acquisition=verify_c0045_compute_observation,
        ),
    }
)


def _registration(authority_id: str) -> ObserverRegistration:
    if authority_id not in _OBSERVERS:
        raise ValueError("Observation authority is not registered")
    return _OBSERVERS[authority_id]


def validate_registered_authority(authority_id: str) -> None:
    """Reject contract observer identifiers not owned by the literal registry."""
    _registration(authority_id)


def validate_registered_predicate(authority_id: str, predicate_id: str) -> None:
    """Require one predicate to belong to the named registered authority."""
    if _registration(authority_id).predicate_id != predicate_id:
        raise ValueError("predicate is not registered for the observation authority")


def registered_authority_revision(authority_ids: set[str]) -> str:
    """Hash the registered observer contracts and their implementation files."""
    if not authority_ids:
        raise ValueError("observer revision requires at least one registered authority")
    records = []
    for authority_id in sorted(authority_ids):
        registration = _registration(authority_id)
        callables = [registration.acquire]
        if registration.verify_acquisition is not None:
            callables.append(registration.verify_acquisition)
        implementations = []
        for observer_callable in callables:
            source_path = inspect.getsourcefile(observer_callable)
            if source_path is None:
                raise ValueError("registered observer has no inspectable source file")
            implementations.append(
                {
                    "identity": (
                        f"{observer_callable.__module__}."
                        f"{observer_callable.__qualname__}"
                    ),
                    "source_sha256": hashlib.sha256(
                        Path(source_path).read_bytes()
                    ).hexdigest(),
                }
            )
        records.append(
            {
                "revision_schema": 2,
                "authority_id": authority_id,
                "predicate_id": registration.predicate_id,
                "products": sorted(registration.products),
                "implementations": implementations,
                "supplemental_sources": {
                    relative_path: hashlib.sha256(
                        (Path(__file__).resolve().parents[2] / relative_path).read_bytes()
                    ).hexdigest()
                    for relative_path in registration.supplemental_sources
                },
            }
        )
    encoded = json.dumps(
        records, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def registered_products() -> frozenset[str]:
    """Every terminal fact some registered observer can independently establish."""
    return frozenset(
        product
        for registration in _OBSERVERS.values()
        for product in registration.products
    )


def _check_result(
    result: PredicateObservation,
    registration: ObserverRegistration,
    expected_scope: FactScope,
) -> None:
    if (
        result.scope != expected_scope
        or result.predicate_id != registration.predicate_id
    ):
        raise ValueError("Observer returned an incompatible scope or predicate")
    if not set(result.established_facts) <= registration.products:
        raise ValueError("Observer returned products outside its registered contract")


def acquire_registered_observation(
    authority_id: str,
    request: LabShellRequest
    | C0010ControllerRequest
    | C0010TransferRequest
    | C0010HttpRequest
    | C0026EffectRequest
    | CostaRictoEffectRequest
    | C0045ComputeRequest
    | C0045ApiRequest
    | C0045FixtureRequest
    | C0045TraceRequest,
    *,
    run_root: Path,
) -> ObservationReference:
    """Run a code-owned adapter, then retain its acquisition and dispatch receipt."""
    registration = _registration(authority_id)
    snapshot = registration.request_model.model_validate(
        request.model_dump(mode="python"), strict=True
    )
    if (
        isinstance(
            snapshot,
            (C0010ControllerRequest, C0026EffectRequest, CostaRictoEffectRequest, C0045FixtureRequest, C0045TraceRequest),
        )
        and snapshot.predicate_id != registration.predicate_id
    ):
        raise ValueError("Request predicate differs from the registered authority")
    result = (
        registration.acquire(snapshot, run_root=run_root)
        if registration.requires_run_root
        else registration.acquire(snapshot)
    )
    _check_result(result, registration, snapshot.scope)
    reference = retain_observation(result, authority_id=authority_id, run_root=run_root)
    with _directory(None, str(run_root)) as root:
        _ensure_directory(root, "authority_receipts")
        with _directory(root, "authority_receipts") as receipts:
            _write_exclusive(
                receipts,
                reference.record_path.split("/")[1],
                reference.model_dump_json().encode("utf-8"),
            )
    return reference


def verify_registered_observation(
    reference: ObservationReference,
    *,
    run_root: Path,
    expected_scope: FactScope,
    expected_predicate: str,
) -> PredicateObservation:
    """Verify code-owned dispatch and storage binding within the trusted controller.

    These receipts are not signatures. A party controlling the trusted controller
    directory can forge its state; guest/proposer outputs do not own that state.
    """
    registration = _registration(reference.authority_id)
    if expected_predicate != registration.predicate_id:
        raise ValueError("Predicate is not registered for the observation authority")
    parts = reference.record_path.split("/")
    if len(parts) != 2 or parts[0] != "observations":
        raise ValueError("Reference does not identify a retained acquisition")
    with _directory(None, str(run_root)) as root:
        with _directory(root, "authority_receipts") as receipts:
            dispatched = ObservationReference.model_validate_json(
                _read_record(receipts, parts[1])
            )
    if dispatched != reference:
        raise ValueError("Reference differs from the registered adapter acquisition")
    result = verify_observation_reference(
        reference,
        run_root=run_root,
        expected_scope=expected_scope,
        expected_predicate=expected_predicate,
    )
    _check_result(result, registration, expected_scope)
    if registration.verify_acquisition is not None:
        registration.verify_acquisition(result, run_root=run_root)
    return result
