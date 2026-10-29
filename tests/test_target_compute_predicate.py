"""Positive, negative, and identity controls for the target CPU predicate."""

import pytest
from pydantic import ValidationError

from runners.capability_facts import FactScope
from runners.target_compute_predicate import (
    TargetProcessCpuSample,
    evaluate_target_cpu_delta,
)


def sample(**changes: object) -> TargetProcessCpuSample:
    values = {
        "scope": FactScope(
            run_id="run-1",
            environment_id="environment-1",
            epoch="boot-1",
            locus="target",
            host_id="target-1",
            principal="rayuser",
        ),
        "process_id": 123,
        "process_start_ticks": 400,
        "process_command_sha256": "a" * 64,
        "monotonic_ns": 1_000,
        "user_cpu_ticks": 20,
        "system_cpu_ticks": 5,
    }
    values.update(changes)
    return TargetProcessCpuSample.model_validate(values)


def test_positive_control_requires_measured_cpu_progress() -> None:
    verdict = evaluate_target_cpu_delta(
        sample(),
        sample(monotonic_ns=2_000, user_cpu_ticks=28, system_cpu_ticks=7),
        minimum_cpu_ticks=10,
    )

    assert verdict.passed
    assert verdict.cpu_ticks_delta == 10


def test_negative_control_does_not_count_elapsed_time_as_cpu() -> None:
    verdict = evaluate_target_cpu_delta(
        sample(), sample(monotonic_ns=2_000), minimum_cpu_ticks=1
    )

    assert not verdict.passed
    assert verdict.cpu_ticks_delta == 0


@pytest.mark.parametrize(
    "change",
    (
        {"process_id": 124},
        {"process_start_ticks": 401},
        {"process_command_sha256": "b" * 64},
        {"scope": FactScope(
            run_id="run-2", environment_id="environment-1", epoch="boot-1",
            locus="target", host_id="target-1", principal="rayuser"
        )},
        {"scope": FactScope(
            run_id="run-1", environment_id="environment-1", epoch="boot-2",
            locus="target", host_id="target-1", principal="rayuser"
        )},
    ),
)
def test_identity_change_is_not_an_effect(change: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="same target run and boot|same process"):
        evaluate_target_cpu_delta(
            sample(), sample(monotonic_ns=2_000, user_cpu_ticks=40, **change),
            minimum_cpu_ticks=1,
        )


def test_clock_or_counter_rollback_fails_closed() -> None:
    with pytest.raises(ValueError, match="ordered"):
        evaluate_target_cpu_delta(sample(), sample(), minimum_cpu_ticks=1)
    with pytest.raises(ValueError, match="must not decrease"):
        evaluate_target_cpu_delta(
            sample(), sample(monotonic_ns=2_000, user_cpu_ticks=19),
            minimum_cpu_ticks=1,
        )


def test_non_target_sample_and_nonpositive_threshold_are_rejected() -> None:
    controller_scope = FactScope(
        run_id="run-1", environment_id="environment-1", epoch="boot-1",
        locus="controller", host_id="controller-1", principal="rayuser"
    )
    with pytest.raises(ValidationError, match="target"):
        sample(scope=controller_scope)
    with pytest.raises(ValidationError):
        evaluate_target_cpu_delta(
            sample(), sample(monotonic_ns=2_000), minimum_cpu_ticks=0
        )
