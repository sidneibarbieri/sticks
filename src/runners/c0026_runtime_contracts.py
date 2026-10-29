"""Load fixed occurrence bindings without blessing the current source dynamically."""

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

_CONTRACT_PATH = (
    Path(__file__).resolve().parents[2] / "data/runtime_contracts/c0026.json"
)


class C0026OccurrenceBinding(ImmutableRecord):
    occurrence: Annotated[int, Field(strict=True, gt=0)]
    technique_id: Identity
    mode: Literal["real_controlled", "naive_simulated"]
    executor_id: Identity
    executor_sha256: Digest
    requirements: tuple[Identity, ...]
    observers: tuple[Identity, ...]


class C0026ContractPopulation(ImmutableRecord):
    schema_version: Literal["c0026-runtime-contracts/v1"]
    campaign_id: Literal["0.c0026"]
    occurrences: tuple[C0026OccurrenceBinding, ...]


def load_c0026_runtime_contracts(
    guest_scope: FactScope,
    registry: ExecutorRegistry,
) -> tuple[RuntimeStepContract, ...]:
    """Bind fixed reviewed rows to one observed lifecycle scope and selected code."""
    if (
        guest_scope.locus != "target"
        or guest_scope.host_id != "target-linux-1"
        or guest_scope.principal != "ubuntu"
    ):
        raise ValueError("C0026 runtime requires its declared target and principal")
    population = C0026ContractPopulation.model_validate_json(
        _CONTRACT_PATH.read_bytes()
    )
    campaign = load_campaign(population.campaign_id)
    actual = [
        (row.occurrence, row.technique_id, row.mode) for row in population.occurrences
    ]
    expected = [
        (step.order, step.technique_id, step.expected_mode.value)
        for step in campaign.steps
    ]
    if actual != expected or len(actual) != 6:
        raise ValueError("C0026 contract inventory differs from the selected campaign")
    contracts = []
    for row in population.occurrences:
        scope = (
            guest_scope
            if row.mode == "real_controlled"
            else FactScope(
                run_id=guest_scope.run_id,
                environment_id=guest_scope.environment_id,
                epoch=guest_scope.run_id,
                locus="controller",
                host_id="controller",
                principal=None,
            )
        )
        contract = RuntimeStepContract(
            campaign_id=population.campaign_id,
            occurrence=row.occurrence,
            technique_id=row.technique_id,
            executor_id=row.executor_id,
            executor_sha256=row.executor_sha256,
            mode=row.mode,
            scope=scope,
            requirements=tuple(
                CapabilityRequirement(
                    name=name,
                    scope=guest_scope,
                    accepted_origins=frozenset({"observed"}),
                )
                for name in row.requirements
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
            raise ValueError("C0026 contract has no matching selected executor")
        verify_executor_binding(contract, executor)
        contracts.append(contract)
    return tuple(contracts)
