"""Retain a two-sample CPU measurement without authorizing a campaign fact."""

import hashlib
import time
from pathlib import Path

from runners.capability_facts import FactScope, ImmutableRecord, ObservationReference
from runners.capability_observations import (
    PredicateObservation,
    retain_observation,
    verify_observation_reference,
)
from runners.target_compute_predicate import (
    TargetComputeVerdict,
    TargetProcessCpuSample,
    evaluate_target_cpu_delta,
)
from runners.target_process_cpu_transport import (
    GuestCpuReply,
    TargetCpuSampleRequest,
    _PROBE_PATH,
    acquire_guest_cpu_sample,
)


class RetainedCpuMeasurement(ImmutableRecord):
    """A threshold result and its retained, non-authorizing observation."""

    verdict: TargetComputeVerdict
    reference: ObservationReference


def measure_and_retain_target_cpu(
    request: TargetCpuSampleRequest,
    *,
    run_root: Path,
    minimum_cpu_ticks: int = 5,
    interval_seconds: float = 1.0,
) -> RetainedCpuMeasurement:
    """Acquire two guest replies and seal them, without assigning an effect fact."""
    if minimum_cpu_ticks <= 0 or interval_seconds <= 0:
        raise ValueError("CPU threshold and sampling interval must be positive")
    before = acquire_guest_cpu_sample(request)
    time.sleep(interval_seconds)
    after = acquire_guest_cpu_sample(request)
    if before.probe_source_sha256 != after.probe_source_sha256:
        raise ValueError("CPU probe source changed between samples")
    verdict = evaluate_target_cpu_delta(
        before.sample, after.sample, minimum_cpu_ticks=minimum_cpu_ticks
    )
    reply_bytes = before.reply_json.encode("utf-8") + b"\0" + after.reply_json.encode("utf-8")
    observation = PredicateObservation(
        scope=request.scope,
        predicate_id="target-cpu-delta-measurement",
        passed=verdict.passed,
        established_facts=(),
        details={
            "before_reply_json": before.reply_json,
            "after_reply_json": after.reply_json,
            "probe_source_sha256": before.probe_source_sha256,
            "cpu_ticks_delta": verdict.cpu_ticks_delta,
            "minimum_cpu_ticks": verdict.minimum_cpu_ticks,
            "process_id": request.process_id,
            "command_sha256": request.command_sha256,
            "nonce": request.nonce,
        },
        content_sha256=hashlib.sha256(reply_bytes).hexdigest(),
    )
    reference = retain_observation(
        observation, authority_id="cpu-measurement-only", run_root=run_root
    )
    return RetainedCpuMeasurement(verdict=verdict, reference=reference)


def _sample_from_reply(reply: GuestCpuReply, scope: FactScope) -> TargetProcessCpuSample:
    if (
        reply.boot_id != scope.epoch
        or reply.hostname != scope.host_id
        or reply.principal != scope.principal
    ):
        raise ValueError("Retained CPU reply differs from the target scope")
    return TargetProcessCpuSample(
        scope=scope,
        process_id=reply.process_id,
        process_start_ticks=reply.process_start_ticks,
        process_command_sha256=reply.process_command_sha256,
        monotonic_ns=reply.monotonic_ns,
        user_cpu_ticks=reply.user_cpu_ticks,
        system_cpu_ticks=reply.system_cpu_ticks,
    )


def verify_retained_cpu_measurement(
    reference: ObservationReference,
    *,
    run_root: Path,
    expected_scope: FactScope,
) -> TargetComputeVerdict:
    """Recompute a sealed measurement; never infer campaign causality."""
    observation = verify_observation_reference(
        reference,
        run_root=run_root,
        expected_scope=expected_scope,
        expected_predicate="target-cpu-delta-measurement",
    )
    if observation.established_facts or observation.producer_occurrence is not None:
        raise ValueError("CPU measurement receipt must not authorize a fact")
    details = observation.details
    before_json = details.get("before_reply_json")
    after_json = details.get("after_reply_json")
    source_digest = details.get("probe_source_sha256")
    threshold = details.get("minimum_cpu_ticks")
    if not isinstance(before_json, str) or not isinstance(after_json, str):
        raise ValueError("CPU measurement lacks retained guest replies")
    if source_digest != hashlib.sha256(_PROBE_PATH.read_bytes()).hexdigest():
        raise ValueError("CPU probe source differs from the retained receipt")
    if type(threshold) is not int or threshold <= 0:
        raise ValueError("CPU measurement threshold is invalid")
    reply_bytes = before_json.encode("utf-8") + b"\0" + after_json.encode("utf-8")
    if observation.content_sha256 != hashlib.sha256(reply_bytes).hexdigest():
        raise ValueError("Retained guest replies differ from the content digest")
    before_reply = GuestCpuReply.model_validate_json(before_json)
    after_reply = GuestCpuReply.model_validate_json(after_json)
    if (
        before_reply.nonce != after_reply.nonce
        or before_reply.nonce != details.get("nonce")
        or before_reply.process_id != details.get("process_id")
        or before_reply.process_command_sha256 != details.get("command_sha256")
    ):
        raise ValueError("Retained CPU replies differ from process selection")
    verdict = evaluate_target_cpu_delta(
        _sample_from_reply(before_reply, expected_scope),
        _sample_from_reply(after_reply, expected_scope),
        minimum_cpu_ticks=threshold,
    )
    if (
        verdict.passed != observation.passed
        or verdict.cpu_ticks_delta != details.get("cpu_ticks_delta")
    ):
        raise ValueError("Retained CPU verdict differs from guest measurements")
    return verdict
