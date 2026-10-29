"""Reviewed C0010 occurrence bindings and their controller/guest scopes."""

import os
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
    Path(__file__).resolve().parents[2] / "data/runtime_contracts/c0010.json"
)
_TARGET_OCCURRENCE = 9
_REVIEWED_OBSERVERS = {
    2: ("c0010-payload",),
    3: ("c0010-page",),
    4: ("c0010-http",),
    7: ("c0010-tool",),
    9: ("c0010-transfer",),
}
_REVIEWED_REQUIREMENTS = {
    4: ("controller:watering_hole_staged",),
    9: ("lab:shell",),
}


class C0010OccurrenceBinding(ImmutableRecord):
    occurrence: Annotated[int, Field(strict=True, gt=0)]
    plan_sequence: Annotated[int, Field(strict=True, gt=0)]
    technique_id: Identity
    mode: Literal["real_controlled", "naive_simulated"]
    locus: Literal["controller", "target"]
    executor_id: Identity
    executor_sha256: Digest
    requirements: tuple[Identity, ...]
    observers: tuple[Identity, ...]


class C0010ContractPopulation(ImmutableRecord):
    schema_version: Literal["c0010-runtime-contracts/v1"]
    campaign_id: Literal["0.c0010"]
    occurrences: tuple[C0010OccurrenceBinding, ...]


def load_c0010_runtime_contracts(
    guest_scope: FactScope,
    registry: ExecutorRegistry,
) -> tuple[RuntimeStepContract, ...]:
    """Bind reviewed rows to this run, with target authority only for T1105."""
    if (
        guest_scope.locus != "target"
        or guest_scope.host_id != "target-linux-1"
        or guest_scope.principal != "ubuntu"
    ):
        raise ValueError("C0010 requires its declared Linux target and principal")
    population = C0010ContractPopulation.model_validate_json(
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
    if actual != expected or len(actual) != 9:
        raise ValueError("C0010 contract inventory differs from the selected campaign")
    plan_sequences = tuple(row.plan_sequence for row in population.occurrences)
    if sorted(plan_sequences) != list(range(1, len(population.occurrences) + 1)):
        raise ValueError("C0010 contract plan sequences must form a permutation")
    controller_scope = FactScope(
        run_id=guest_scope.run_id,
        environment_id=guest_scope.environment_id,
        epoch=guest_scope.run_id,
        locus="controller",
        host_id="controller",
        principal=str(os.geteuid()),
    )
    contracts = []
    for row in population.occurrences:
        target_row = row.occurrence == _TARGET_OCCURRENCE
        if (row.locus == "target") != target_row:
            raise ValueError("C0010 contract changed the reviewed target locus")
        if row.observers != _REVIEWED_OBSERVERS.get(row.occurrence, ()):
            raise ValueError("C0010 contract changed reviewed observer authority")
        if row.requirements != _REVIEWED_REQUIREMENTS.get(row.occurrence, ()):
            raise ValueError("C0010 contract changed reviewed prerequisites")
        scope = guest_scope if target_row else controller_scope
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
                    scope=guest_scope if name == "lab:shell" else controller_scope,
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
            raise ValueError("C0010 contract has no matching selected executor")
        verify_executor_binding(contract, executor)
        contracts.append(contract)
    return tuple(contracts)
