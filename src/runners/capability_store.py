"""Runtime capability state with explicit origin and verified acquisition."""

from pathlib import Path

from runners.capability_authority import verify_registered_observation
from runners.capability_facts import (
    CapabilityFact,
    CapabilityRequirement,
    FactScope,
    ObservationReference,
    match_requirement,
)


class CapabilityStore:
    """Retain provenance without accepting executor assertions as authority."""

    def __init__(self) -> None:
        self._facts: list[CapabilityFact] = []

    def _add_nonobserved(self, fact: CapabilityFact, origin: str) -> None:
        validated = CapabilityFact.model_validate(
            fact.model_dump(mode="python"), strict=True
        )
        if validated.origin != origin:
            raise ValueError("Fact origin differs from the ingestion method")
        if validated not in self._facts:
            self._facts.append(validated)

    def add_declaration(self, fact: CapabilityFact) -> None:
        """Retain a profile declaration without operational authority."""
        self._add_nonobserved(fact, "profile_declaration")

    def add_simulation(self, fact: CapabilityFact) -> None:
        """Retain simulated state without observed-origin promotion."""
        self._add_nonobserved(fact, "simulation")

    def add_observed(
        self,
        reference: ObservationReference,
        *,
        run_root: Path,
        expected_scope: FactScope,
        expected_predicate: str,
    ) -> tuple[CapabilityFact, ...]:
        """Construct facts only from verified registered-adapter acquisitions."""
        observed = verify_registered_observation(
            reference,
            run_root=run_root,
            expected_scope=expected_scope,
            expected_predicate=expected_predicate,
        )
        established = tuple(
            CapabilityFact(
                name=name,
                origin="observed",
                scope=observed.scope,
                producer_occurrence=observed.producer_occurrence,
                observation=reference,
                content_sha256=observed.content_sha256,
            )
            for name in observed.established_facts
        )
        for fact in established:
            if fact not in self._facts:
                self._facts.append(fact)
        return established

    def match(self, requirement: CapabilityRequirement) -> CapabilityFact | None:
        """Match an exact capability contract without changing its origin."""
        return match_requirement(requirement, tuple(reversed(self.snapshot())))

    def invalidate_requirement(self, requirement: CapabilityRequirement) -> None:
        """Invalidate one mutable product without erasing unrelated shell facts."""
        self._facts = [
            fact
            for fact in self._facts
            if not (fact.name == requirement.name and fact.scope == requirement.scope)
        ]

    def invalidate(self, scope: FactScope) -> None:
        """Remove facts at the affected scope while preserving unrelated hosts."""
        self._facts = [fact for fact in self._facts if fact.scope != scope]

    def snapshot(self) -> tuple[CapabilityFact, ...]:
        """Return immutable fact records without exposing the internal collection."""
        return tuple(self._facts)
