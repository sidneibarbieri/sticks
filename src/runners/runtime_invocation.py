"""Invoke a registry-selected executor after exact typed readiness checks."""

from pathlib import Path
from typing import Annotated, Callable

from pydantic import Field

from executors.executor_registry import ExecutorRegistry
from executors.lab_transport import target_executor_dispatch
from executors.c0045_compute_executor import C0045ProcessSelection
from executors.c0045_trace_executor import C0045TraceSelection
from runners.capability_facts import (
    CapabilityFact,
    Identity,
    ImmutableRecord,
    ObservationReference,
)
from runners.capability_observations import PredicateObservation
from runners.capability_store import CapabilityStore
from runners.runtime_step_contracts import (
    RuntimeStepContract,
    unmet_requirements,
    verify_executor_binding,
)


class RuntimeReadinessError(ValueError):
    """A scoped runtime prerequisite is unavailable for controlled execution."""


class RuntimeInvocationOutcome(ImmutableRecord):
    """Executor outcome and declarations, without effect certification."""

    executor_id: Identity
    executor_completed: Annotated[bool, Field(strict=True)]
    stdout: str
    stderr: str
    artifacts: tuple[str, ...]
    declared_products: tuple[str, ...]


class RuntimeOccurrenceOutcome(ImmutableRecord):
    """Keep completion, measured postconditions and granted facts distinct."""

    invocation: RuntimeInvocationOutcome
    observations: tuple[PredicateObservation, ...]
    observation_references: tuple[ObservationReference, ...]
    authorizing_facts: tuple[CapabilityFact, ...]
    simulated_facts: tuple[CapabilityFact, ...] = ()
    consumed_references: tuple[ObservationReference, ...] = ()


def portable_invocation_text(value: str, artifact_root: Path) -> str:
    """Keep host-specific workspace paths out of retained invocation records."""
    portable = value.replace(str(artifact_root.resolve()), ".")
    if str(Path.home()) in portable:
        raise ValueError(
            "Executor output contains a host home path outside the artifact"
        )
    return portable


def invoke_runtime_step(
    contract: RuntimeStepContract,
    store: CapabilityStore,
    registry: ExecutorRegistry,
    *,
    sut_profile_id: str,
    live_observer: Callable[[int | C0045ProcessSelection | C0045TraceSelection], bool] | None = None,
) -> RuntimeInvocationOutcome:
    """Execute only the trusted registry binding after all typed prerequisites.

    No available-capability strings are passed to the legacy resolver. Exceptions
    propagate to the evidence-owning runner; returned products remain declarations.
    """
    validated = RuntimeStepContract.model_validate(
        contract.model_dump(mode="python"), strict=True
    )
    missing = unmet_requirements(validated, store)
    if missing:
        raise RuntimeReadinessError(
            "Selected runtime occurrence has unmet typed prerequisites"
        )
    executor = registry.get_executor(validated.technique_id, validated.campaign_id)
    metadata = registry.get_metadata(validated.technique_id, validated.campaign_id)
    if executor is None or metadata is None:
        raise ValueError("Selected runtime occurrence lacks a registered executor")
    verify_executor_binding(validated, executor)
    if (
        metadata.technique_id != validated.technique_id
        or metadata.execution_mode.value != validated.mode
    ):
        raise ValueError("Selected executor metadata differs from occurrence contract")
    with target_executor_dispatch():
        if live_observer is None:
            completed, stdout, stderr, artifacts = executor(
                validated.campaign_id, sut_profile_id
            )
        else:
            completed, stdout, stderr, artifacts = executor(
                validated.campaign_id, sut_profile_id, live_observer=live_observer
            )
    artifact_root = Path(__file__).resolve().parents[2]
    return RuntimeInvocationOutcome(
        executor_id=validated.executor_id,
        executor_completed=completed,
        stdout=portable_invocation_text(stdout, artifact_root),
        stderr=portable_invocation_text(stderr, artifact_root),
        artifacts=tuple(
            portable_invocation_text(artifact, artifact_root) for artifact in artifacts
        ),
        declared_products=tuple(metadata.produces),
    )
