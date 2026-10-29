"""Pure runtime fact contracts; observation authority is verified separately."""

from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

FactOrigin = Literal["profile_declaration", "simulation", "observed"]
Identity = Annotated[str, StringConstraints(strict=True, min_length=1, pattern=r"\S")]
Digest = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{64}$")]


class ImmutableRecord(BaseModel):
    """Reject undeclared fields and changes to validated records."""

    model_config = ConfigDict(extra="forbid", frozen=True)


class FactScope(ImmutableRecord):
    """Identify the run, environment lifetime, host and execution principal."""

    run_id: Identity
    environment_id: Identity
    epoch: Identity
    locus: Literal["controller", "attacker", "target"]
    host_id: Identity
    principal: Identity | None


class ObservationReference(ImmutableRecord):
    """Bind a retained observation without asserting its truth."""

    authority_id: Identity
    predicate_id: Identity
    record_path: Identity
    record_sha256: Digest

    @field_validator("record_path")
    @classmethod
    def validate_record_path(cls, value: str) -> str:
        """Require a canonical relative POSIX path without traversal."""
        if (
            "\\" in value
            or ":" in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
        ):
            raise ValueError("Observation path must be relative POSIX syntax")
        if any(part in {"", ".", ".."} for part in value.split("/")):
            raise ValueError("Observation path must contain only canonical components")
        return value


class CapabilityFact(ImmutableRecord):
    """Retain a capability's source and scope without upgrading its assurance."""

    name: Identity
    origin: FactOrigin
    scope: FactScope
    producer_occurrence: Annotated[int, Field(strict=True, gt=0)] | None
    observation: ObservationReference | None
    content_sha256: Digest | None = None

    @model_validator(mode="after")
    def validate_observation_origin(self) -> Self:
        """Require an observation reference exactly for observed-origin facts."""
        if (self.origin == "observed") != (self.observation is not None):
            raise ValueError("Observation references belong only to observed facts")
        return self


class CapabilityRequirement(ImmutableRecord):
    """Declare exact scope and explicitly permitted origins."""

    name: Identity
    scope: FactScope
    accepted_origins: Annotated[frozenset[FactOrigin], Field(min_length=1)]


def match_requirement(
    requirement: CapabilityRequirement,
    facts: tuple[CapabilityFact, ...],
) -> CapabilityFact | None:
    """Return the first exact name, origin and scope match, or None."""
    for candidate in facts:
        if (
            candidate.name == requirement.name
            and candidate.origin in requirement.accepted_origins
            and candidate.scope == requirement.scope
        ):
            return candidate
    return None
