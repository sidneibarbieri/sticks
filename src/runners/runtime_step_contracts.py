"""Selected occurrence contracts and non-mutating readiness assessment."""

import hashlib
import inspect
from pathlib import Path
from typing import Annotated, Callable, Literal, Self

from pydantic import Field, model_validator

from runners.capability_authority import validate_registered_authority
from runners.capability_facts import (
    CapabilityRequirement,
    Digest,
    FactScope,
    Identity,
    ImmutableRecord,
)
from runners.capability_store import CapabilityStore


class RuntimeStepContract(ImmutableRecord):
    """Bind a selected occurrence to implementation identity and authority scope."""

    campaign_id: Identity
    occurrence: Annotated[int, Field(strict=True, gt=0)]
    technique_id: Identity
    executor_id: Identity
    executor_sha256: Digest
    mode: Literal["real_controlled", "naive_simulated", "state_bridge"]
    scope: FactScope
    requirements: tuple[CapabilityRequirement, ...]
    observers: tuple[Identity, ...]

    @model_validator(mode="after")
    def validate_assurance(self) -> Self:
        """Prevent weak origins from enabling controlled execution."""
        for requirement in self.requirements:
            if (
                self.mode != "naive_simulated"
                and requirement.accepted_origins != frozenset({"observed"})
            ):
                raise ValueError(
                    "Controlled requirements must accept only observed facts"
                )
            if (
                requirement.scope.run_id != self.scope.run_id
                or requirement.scope.environment_id != self.scope.environment_id
            ):
                raise ValueError(
                    "Requirements must belong to the selected run and environment"
                )
        if len(set(self.observers)) != len(self.observers):
            raise ValueError("Observer identifiers must be unique")
        for authority_id in self.observers:
            validate_registered_authority(authority_id)
        keys = [(item.name, item.scope) for item in self.requirements]
        if len(set(keys)) != len(keys):
            raise ValueError("Requirements must be unique by name and scope")
        return self


def unmet_requirements(
    contract: RuntimeStepContract,
    store: CapabilityStore,
) -> tuple[CapabilityRequirement, ...]:
    """Return unmet typed prerequisites without changing facts or executing a step."""
    return tuple(
        requirement
        for requirement in contract.requirements
        if store.match(requirement) is None
    )


def verify_executor_binding(contract: RuntimeStepContract, executor: Callable) -> None:
    """Check the registry-selected function identity and current source bytes.

    The callable must come from the trusted code registry, not a contract-supplied
    import path. This checks revision binding, not behavioral fidelity.
    """
    identity = f"{executor.__module__}.{executor.__qualname__}"
    if identity != contract.executor_id:
        raise ValueError("Selected executor identity differs from occurrence contract")
    source_path = inspect.getsourcefile(executor)
    if source_path is None:
        raise ValueError("Selected executor has no inspectable source file")
    source_digest = hashlib.sha256(Path(source_path).read_bytes()).hexdigest()
    if source_digest != contract.executor_sha256:
        raise ValueError("Selected executor source differs from occurrence contract")
