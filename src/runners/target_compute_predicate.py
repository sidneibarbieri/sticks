"""Evaluate bounded target CPU use from separately collected procfs samples.

This predicate does not attest that samples came from a guest, that the
campaign caused the process, or that any historical exploit occurred. The
transport and process-selection authority must be verified by its caller.
"""

from typing import Annotated, Self

from pydantic import Field, model_validator

from runners.capability_facts import Digest, FactScope, ImmutableRecord


PositiveTicks = Annotated[int, Field(strict=True, gt=0)]
NonnegativeTicks = Annotated[int, Field(strict=True, ge=0)]


class TargetProcessCpuSample(ImmutableRecord):
    """One observer-collected process sample bound to a target run and boot."""

    scope: FactScope
    process_id: PositiveTicks
    process_start_ticks: NonnegativeTicks
    process_command_sha256: Digest
    monotonic_ns: PositiveTicks
    user_cpu_ticks: NonnegativeTicks
    system_cpu_ticks: NonnegativeTicks

    @model_validator(mode="after")
    def require_target_scope(self) -> Self:
        if self.scope.locus != "target":
            raise ValueError("CPU effect samples must come from the target")
        return self


class TargetComputeVerdict(ImmutableRecord):
    """Measured process CPU delta; not a claim of unauthorized resource use."""

    passed: bool
    cpu_ticks_delta: NonnegativeTicks
    minimum_cpu_ticks: PositiveTicks


def evaluate_target_cpu_delta(
    before: TargetProcessCpuSample,
    after: TargetProcessCpuSample,
    *,
    minimum_cpu_ticks: int,
) -> TargetComputeVerdict:
    """Reject identity drift and evaluate a preregistered positive CPU delta."""
    if before.scope != after.scope:
        raise ValueError("CPU samples must belong to the same target run and boot")
    if (
        before.process_id != after.process_id
        or before.process_start_ticks != after.process_start_ticks
        or before.process_command_sha256 != after.process_command_sha256
    ):
        raise ValueError("CPU samples must describe the same process")
    if after.monotonic_ns <= before.monotonic_ns:
        raise ValueError("CPU samples must be ordered in guest monotonic time")
    before_ticks = before.user_cpu_ticks + before.system_cpu_ticks
    after_ticks = after.user_cpu_ticks + after.system_cpu_ticks
    if after_ticks < before_ticks:
        raise ValueError("Process CPU counters must not decrease")
    cpu_ticks_delta = after_ticks - before_ticks
    return TargetComputeVerdict(
        passed=cpu_ticks_delta >= minimum_cpu_ticks,
        cpu_ticks_delta=cpu_ticks_delta,
        minimum_cpu_ticks=minimum_cpu_ticks,
    )
