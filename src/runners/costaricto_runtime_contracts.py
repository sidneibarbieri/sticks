"""Reviewed CostaRicto bindings without claiming unobserved discovery."""

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
    Path(__file__).resolve().parents[2] / "data/runtime_contracts/costaricto.json"
)
_CONTROLLED_OCCURRENCES = frozenset({1, 2, 9})
_REVIEWED_OBSERVERS = {
    1: ("costaricto-discovery",),
    2: ("costaricto-transfer",),
    9: ("costaricto-collection",),
}


class CostaRictoOccurrenceBinding(ImmutableRecord):
    occurrence: Annotated[int, Field(strict=True, gt=0)]
    technique_id: Identity
    mode: Literal["real_controlled", "naive_simulated"]
    executor_id: Identity
    executor_sha256: Digest
    requirements: tuple[Identity, ...]
    observers: tuple[Identity, ...]


class CostaRictoContractPopulation(ImmutableRecord):
    schema_version: Literal["costaricto-runtime-contracts/v1"]
    campaign_id: Literal["0.costaricto"]
    occurrences: tuple[CostaRictoOccurrenceBinding, ...]


def load_costaricto_runtime_contracts(
    guest_scope: FactScope,
    registry: ExecutorRegistry,
) -> tuple[RuntimeStepContract, ...]:
    """Bind the ten selected occurrences to bounded guest effects."""
    if (
        guest_scope.locus != "target"
        or guest_scope.host_id != "target-linux-1"
        or guest_scope.principal != "reconuser"
    ):
        raise ValueError("CostaRicto requires its declared Linux guest and principal")
    population = CostaRictoContractPopulation.model_validate_json(
        _CONTRACT_PATH.read_bytes()
    )
    campaign = load_campaign(population.campaign_id)
    actual = tuple(
        (row.occurrence, row.technique_id, row.mode) for row in population.occurrences
    )
    expected = tuple(
        (step.order, step.technique_id, step.expected_mode.value)
        for step in campaign.steps
    )
    if actual != expected or len(actual) != 10:
        raise ValueError("CostaRicto contract inventory differs from the campaign")

    contracts = []
    for row in population.occurrences:
        controlled = row.occurrence in _CONTROLLED_OCCURRENCES
        reviewed_requirements = ("lab:shell",) if controlled else ()
        if (
            row.requirements != reviewed_requirements
            or row.observers != _REVIEWED_OBSERVERS.get(row.occurrence, ())
        ):
            raise ValueError("CostaRicto authority differs from the reviewed boundary")
        scope = (
            guest_scope
            if controlled
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
            raise ValueError("CostaRicto has no selected executor for a reviewed row")
        verify_executor_binding(contract, executor)
        contracts.append(contract)
    return tuple(contracts)
