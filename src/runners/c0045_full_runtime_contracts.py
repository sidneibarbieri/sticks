"""Bind every original C0045 occurrence without upgrading simulated rows."""

from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from executors.executor_registry import ExecutorRegistry
from loaders.campaign_loader import load_campaign
from runners.capability_facts import (
    CapabilityRequirement,
    Digest,
    FactScope,
    Identity,
    ImmutableRecord,
)
from runners.runtime_step_contracts import RuntimeStepContract, verify_executor_binding

CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "data/runtime_contracts/c0045_v2.json"
)
_OBSERVERS = {
    1: ("c0045-api",),
    5: ("c0045-toolkit",),
    6: ("c0045-transfer",),
    7: ("c0045-python",),
    8: ("c0045-network",),
}


class C0045OccurrenceBinding(ImmutableRecord):
    occurrence: Annotated[int, Field(strict=True, gt=0)]
    plan_sequence: Annotated[int, Field(strict=True, gt=0)]
    caldera_dispatch: Literal["native_target", "controller_simulation"]
    technique_id: Identity
    mode: Literal["real_controlled", "naive_simulated"]
    executor_id: Identity
    executor_sha256: Digest
    requirements: tuple[Identity, ...]
    observers: tuple[Identity, ...]


class C0045ContractPopulation(ImmutableRecord):
    schema_version: Literal["c0045-runtime-contracts/v2"]
    campaign_id: Literal["0.shadowray"]
    occurrences: tuple[C0045OccurrenceBinding, ...]


def load_c0045_full_runtime_contracts(
    guest_scope: FactScope, registry: ExecutorRegistry
) -> tuple[RuntimeStepContract, ...]:
    """Load all ten rows after pinning campaign inventory and executor bytes."""
    if (
        guest_scope.locus != "target"
        or guest_scope.host_id != "target-linux-1"
        or guest_scope.principal != "rayuser"
    ):
        raise ValueError("C0045 requires its declared Linux target and principal")
    population = C0045ContractPopulation.model_validate_json(CONTRACT_PATH.read_bytes())
    campaign = load_campaign(population.campaign_id)
    actual = tuple(
        (row.occurrence, row.technique_id, row.mode) for row in population.occurrences
    )
    expected = tuple(
        (step.order, step.technique_id, step.expected_mode.value)
        for step in campaign.steps
    )
    if actual != expected or len(actual) != 10:
        raise ValueError("C0045 contract inventory differs from the selected campaign")
    plan_sequences = tuple(row.plan_sequence for row in population.occurrences)
    if sorted(plan_sequences) != list(range(1, len(population.occurrences) + 1)):
        raise ValueError("C0045 contract plan sequences must form a permutation")
    contracts = []
    for row in population.occurrences:
        if row.mode == "real_controlled" and row.caldera_dispatch != "native_target":
            raise ValueError("Controlled C0045 occurrence requires native target dispatch")
        if row.observers != _OBSERVERS.get(row.occurrence, ()):
            raise ValueError("C0045 contract changed reviewed observer authority")
        if row.requirements != ("lab:shell",):
            raise ValueError("C0045 contract changed the guest lifecycle prerequisite")
        contract = RuntimeStepContract(
            campaign_id=population.campaign_id,
            occurrence=row.occurrence,
            technique_id=row.technique_id,
            executor_id=row.executor_id,
            executor_sha256=row.executor_sha256,
            mode=row.mode,
            scope=guest_scope,
            requirements=(
                CapabilityRequirement(
                    name="lab:shell",
                    scope=guest_scope,
                    accepted_origins=frozenset({"observed"}),
                ),
            ),
            observers=row.observers,
        )
        executor = registry.get_executor(row.technique_id, population.campaign_id)
        metadata = registry.get_metadata(row.technique_id, population.campaign_id)
        if (
            executor is None
            or metadata is None
            or metadata.execution_mode.value != row.mode
        ):
            raise ValueError("C0045 contract has no matching selected executor")
        verify_executor_binding(contract, executor)
        contracts.append(contract)
    return tuple(contracts)


def c0045_native_occurrences() -> frozenset[int]:
    population = C0045ContractPopulation.model_validate_json(CONTRACT_PATH.read_bytes())
    return frozenset(
        row.occurrence for row in population.occurrences
        if row.caldera_dispatch == "native_target"
    )
