"""Bind trusted lab lifecycle scope before admitting granted shell authority."""

from pathlib import Path
from uuid import uuid4

from executors.lab_transport import (
    detect_vagrant_provider,
    normalize_vm_name,
    probe_vm_identity,
    run_bash_on_target_vm,
)
from loaders.campaign_loader import load_sut_profile
from runners.capability_authority import (
    LabShellRequest,
    acquire_registered_observation,
    verify_registered_observation,
)
from runners.capability_facts import (
    CapabilityFact,
    FactScope,
    ImmutableRecord,
    ObservationReference,
)
from runners.capability_observations import PredicateObservation, retain_observation
from runners.capability_store import CapabilityStore
from runners.runtime_diagnostics import parse_guest_reply
from runners.lab_bootstrap_observer import (
    GuestShellIdentity,
    _check_profile_principal,
    _probe_script,
)


class LabBootstrapOutcome(ImmutableRecord):
    """Record discovery separately from the registered authority acquisition."""

    scope: FactScope
    discovery_reference: ObservationReference
    reference: ObservationReference
    facts: tuple[CapabilityFact, ...]


class LabTopologyMember(ImmutableRecord):
    """One read-only response from a source-declared laboratory VM."""

    vm_name: str
    hostname: str
    boot_id: str


class LabTopologyWitness(ImmutableRecord):
    """Record that every declared VM was reachable for this run.

    This is a topology precondition, not evidence that campaign occurrences
    ran on every member.
    """

    schema_version: str = "lab-topology/v1"
    sut_profile_id: str
    provider: str
    nonce: str
    members: tuple[LabTopologyMember, ...]


def qualify_declared_lab_topology(sut_profile_id: str) -> LabTopologyWitness:
    """Probe each source-declared VM and reject partial laboratory topologies."""
    profile = load_sut_profile(sut_profile_id)
    required_vms = tuple(
        dict.fromkeys(normalize_vm_name(vm_name) for vm_name in profile.required_vms)
    )
    if not required_vms:
        raise ValueError(f"SUT profile declares no required VMs: {sut_profile_id}")
    provider = detect_vagrant_provider()
    nonce = uuid4().hex
    members = []
    for vm_name in required_vms:
        result = probe_vm_identity(vm_name, nonce, provider=provider)
        result.check_returncode()
        fields = result.stdout.strip().split("\t")
        if len(fields) != 3:
            raise ValueError(f"Topology probe returned malformed identity: {vm_name}")
        response_nonce, hostname, boot_id = fields
        if response_nonce != nonce or not hostname or not boot_id:
            raise ValueError(f"Topology probe identity mismatch: {vm_name}")
        members.append(
            LabTopologyMember(
                vm_name=vm_name,
                hostname=hostname,
                boot_id=boot_id,
            )
        )
    return LabTopologyWitness(
        sut_profile_id=sut_profile_id,
        provider=provider,
        nonce=nonce,
        members=tuple(members),
    )


def _discover_scope(
    *,
    sut_profile_id: str,
    expected_host_id: str,
    principal: str,
    run_id: str,
    environment_id: str,
) -> tuple[FactScope, PredicateObservation]:
    _check_profile_principal(sut_profile_id, expected_host_id, principal)
    nonce = uuid4().hex
    result = run_bash_on_target_vm(
        sut_profile_id,
        _probe_script(nonce),
        execution_user=principal,
        timeout=15,
    )
    result.check_returncode()
    discovered = parse_guest_reply(result, GuestShellIdentity.model_validate_json)
    if (
        discovered.hostname != expected_host_id
        or discovered.principal != principal
        or discovered.nonce != nonce
    ):
        raise ValueError(
            "Lifecycle discovery differs from the declared guest or challenge"
        )
    scope = FactScope(
        run_id=run_id,
        environment_id=environment_id,
        epoch=discovered.boot_id,
        locus="target",
        host_id=expected_host_id,
        principal=principal,
    )
    observation = PredicateObservation(
        scope=scope,
        predicate_id="lifecycle-identity",
        passed=True,
        established_facts=(),
        details={
            "returncode": result.returncode,
            "stderr": result.stderr,
            "nonce": nonce,
        },
    )
    return scope, observation


def bootstrap_lab_authority(
    *,
    sut_profile_id: str,
    expected_host_id: str,
    principal: str,
    run_id: str,
    environment_id: str,
    run_root: Path,
    store: CapabilityStore,
) -> LabBootstrapOutcome:
    """Discover actual boot identity, then require a fresh registered shell probe.

    Discovery records cannot authorize a controlled action. This grants lab access
    through the declared transport, without claiming adversarial access acquisition.
    """
    scope, discovered = _discover_scope(
        sut_profile_id=sut_profile_id,
        expected_host_id=expected_host_id,
        principal=principal,
        run_id=run_id,
        environment_id=environment_id,
    )
    discovery_reference = retain_observation(
        discovered, authority_id="lab-lifecycle", run_root=run_root
    )
    request = LabShellRequest(
        sut_profile_id=sut_profile_id, scope=scope, nonce=uuid4().hex
    )
    reference = acquire_registered_observation("lab-shell", request, run_root=run_root)
    measured = verify_registered_observation(
        reference,
        run_root=run_root,
        expected_scope=scope,
        expected_predicate="shell-nonce",
    )
    if not measured.passed:
        raise ValueError(
            "Lab changed scope or failed during registered bootstrap; retained observations explain the refusal"
        )
    facts = store.add_observed(
        reference,
        run_root=run_root,
        expected_scope=scope,
        expected_predicate="shell-nonce",
    )
    return LabBootstrapOutcome(
        scope=scope,
        discovery_reference=discovery_reference,
        reference=reference,
        facts=facts,
    )
