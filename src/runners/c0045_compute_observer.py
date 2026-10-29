"""Bind a bounded guest CPU measurement to the prospective C0045 occurrence."""

from pathlib import Path
from typing import Literal, Self

from pydantic import Field, model_validator

from executors.c0045_compute_command import build_c0045_compute_command
from runners.c0045_compute_study import load_c0045_compute_study
from runners.capability_facts import Digest, FactScope, Identity, ImmutableRecord, ObservationReference
from runners.capability_observations import PredicateObservation, verify_observation_reference
from runners.target_cpu_measurement import (
    measure_and_retain_target_cpu,
    verify_retained_cpu_measurement,
)
from runners.target_process_cpu_transport import TargetCpuSampleRequest


class C0045ComputeRequest(ImmutableRecord):
    """Select the reviewed workload process while its typed executor is live."""

    sut_profile_id: Literal["0.shadowray"]
    scope: FactScope
    nonce: Identity
    producer_occurrence: Literal[10]
    process_id: int = Field(strict=True, gt=0)
    command_sha256: Digest

    @model_validator(mode="after")
    def validate_study_binding(self) -> Self:
        study = load_c0045_compute_study()
        if (
            self.scope.locus != "target"
            or self.scope.host_id != study.target_host_id
            or self.scope.principal != study.target_principal
            or self.command_sha256
            != build_c0045_compute_command(self.nonce).expected_command_sha256
        ):
            raise ValueError("C0045 process selection differs from the frozen study")
        return self


def observe_c0045_compute(
    request: C0045ComputeRequest, *, run_root: Path
) -> PredicateObservation:
    """Measure the selected guest process; executor completion grants nothing."""
    study = load_c0045_compute_study()
    measurement = measure_and_retain_target_cpu(
        TargetCpuSampleRequest(
            sut_profile_id=request.sut_profile_id,
            scope=request.scope,
            process_id=request.process_id,
            nonce=request.nonce,
            command_sha256=request.command_sha256,
        ),
        run_root=run_root,
        minimum_cpu_ticks=study.minimum_cpu_ticks,
        interval_seconds=study.sampling_interval_seconds,
    )
    return PredicateObservation(
        scope=request.scope,
        predicate_id="bounded-guest-cpu",
        passed=measurement.verdict.passed,
        established_facts=("compute:bounded_guest_cpu",) if measurement.verdict.passed else (),
        producer_occurrence=request.producer_occurrence,
        content_sha256=measurement.reference.record_sha256,
        details={
            "measurement_reference": measurement.reference.model_dump_json(),
            "process_id": request.process_id,
            "nonce": request.nonce,
            "command_sha256": request.command_sha256,
            "cpu_ticks_delta": measurement.verdict.cpu_ticks_delta,
            "minimum_cpu_ticks": measurement.verdict.minimum_cpu_ticks,
        },
    )


def verify_c0045_compute_observation(
    observation: PredicateObservation, *, run_root: Path
) -> None:
    """Replay the nested guest replies before accepting an observed product."""
    if observation.producer_occurrence != 10:
        raise ValueError("C0045 observation has the wrong producer occurrence")
    details = observation.details
    serialized_reference = details.get("measurement_reference")
    nonce = details.get("nonce")
    if not isinstance(serialized_reference, str) or not isinstance(nonce, str):
        raise ValueError("C0045 observation lacks its measurement binding")
    selection = build_c0045_compute_command(nonce)
    if selection.expected_command_sha256 != details.get("command_sha256"):
        raise ValueError("C0045 observation differs from the selected workload")
    reference = ObservationReference.model_validate_json(serialized_reference)
    if observation.content_sha256 != reference.record_sha256:
        raise ValueError("C0045 observation differs from its CPU measurement digest")
    measurement = verify_observation_reference(
        reference, run_root=run_root, expected_scope=observation.scope,
        expected_predicate="target-cpu-delta-measurement",
    )
    study = load_c0045_compute_study()
    if (
        measurement.details.get("process_id") != details.get("process_id")
        or measurement.details.get("nonce") != nonce
        or measurement.details.get("command_sha256") != details.get("command_sha256")
        or measurement.details.get("minimum_cpu_ticks") != study.minimum_cpu_ticks
    ):
        raise ValueError("C0045 observation differs from its selected guest process")
    verdict = verify_retained_cpu_measurement(
        reference, run_root=run_root, expected_scope=observation.scope
    )
    if (
        verdict.passed != observation.passed
        or verdict.cpu_ticks_delta != details.get("cpu_ticks_delta")
        or verdict.minimum_cpu_ticks != details.get("minimum_cpu_ticks")
        or ("compute:bounded_guest_cpu" in observation.established_facts) != verdict.passed
    ):
        raise ValueError("C0045 observation differs from replayed guest CPU counters")
