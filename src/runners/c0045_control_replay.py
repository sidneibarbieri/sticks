"""Replay a C0045 calibration cell without promoting it to a campaign effect."""

import hashlib
from pathlib import Path

from runners.c0045_compute_study import STUDY_PATH, load_c0045_compute_study
from runners.c0045_control_run import (
    BUSY_CONTROL_CODE, CONTROL_SOURCE_PATH, C0045ControlRecord,
    ControllerCpuReply, _guest_command, _idle_guest_command,
)
from runners.c0045_effect_series import (
    SERIES_PATH, c0045_series_sha256, load_c0045_effect_series,
)
from runners.capability_authority import verify_registered_observation
from runners.capability_observations import (
    _directory, _read_record, verify_observation_reference,
)
from runners.target_cpu_measurement import verify_retained_cpu_measurement


def _read_root_record(run_root: Path, filename: str) -> bytes:
    with _directory(None, str(run_root)) as directory:
        return _read_record(directory, filename)


def verify_c0045_control(
    run_root: Path, series_path: Path = SERIES_PATH
) -> C0045ControlRecord:
    """Recompute the target measurement and check that the control grants no fact."""
    series = load_c0045_effect_series(series_path)
    study = load_c0045_compute_study()
    plan = C0045ControlRecord.model_validate_json(
        _read_root_record(run_root, "plan.json")
    )
    summary = C0045ControlRecord.model_validate_json(
        _read_root_record(run_root, "summary.json")
    )
    if plan.status != "planned" or plan.bootstrap is not None:
        raise ValueError("C0045 control plan was not sealed before guest acquisition")
    if summary.status != "measured" or summary.bootstrap is None:
        raise ValueError("C0045 control has no completed measurement")
    if (
        plan.cell_id != summary.cell_id or plan.control_kind != summary.control_kind
        or plan.run_id != summary.run_id
        or plan.source_study_sha256 != summary.source_study_sha256
        or plan.series_sha256 != summary.series_sha256
        or plan.control_source_sha256 != summary.control_source_sha256
    ):
        raise ValueError("C0045 control plan and measurement select different cells")
    if (
        summary.source_study_sha256 != hashlib.sha256(STUDY_PATH.read_bytes()).hexdigest()
        or summary.series_sha256 != c0045_series_sha256(series_path)
        or summary.control_source_sha256
        != hashlib.sha256(CONTROL_SOURCE_PATH.read_bytes()).hexdigest()
    ):
        raise ValueError("C0045 control differs from its frozen sources")
    if series.arm_for(summary.cell_id) != summary.control_kind:
        raise ValueError("C0045 control arm differs from its frozen cell")
    if summary.infrastructure_provider == "":
        raise ValueError("C0045 control lacks a lab provider")
    bootstrap = summary.bootstrap
    scope = bootstrap.scope
    if (
        scope.run_id != summary.run_id or scope.locus != "target"
        or scope.host_id != study.target_host_id
        or scope.principal != study.target_principal
    ):
        raise ValueError("C0045 control bootstrap differs from its guest selection")
    discovery = verify_observation_reference(
        bootstrap.discovery_reference, run_root=run_root,
        expected_scope=scope, expected_predicate="lifecycle-identity",
    )
    shell = verify_registered_observation(
        bootstrap.reference, run_root=run_root,
        expected_scope=scope, expected_predicate="shell-nonce",
    )
    if (
        not discovery.passed or not shell.passed
        or tuple(fact.name for fact in bootstrap.facts) != ("lab:shell",)
        or bootstrap.facts[0].observation != bootstrap.reference
    ):
        raise ValueError("C0045 control lacks observed guest-shell authority")
    if summary.control_kind == "busy":
        _, command_sha256 = _guest_command(
            BUSY_CONTROL_CODE, summary.nonce, study.workload_duration_seconds
        )
    else:
        _, command_sha256 = _idle_guest_command(
            summary.nonce, study.workload_duration_seconds
        )
    if summary.command_sha256 != command_sha256:
        raise ValueError("C0045 control guest process differs from selected workload")
    observation = verify_observation_reference(
        summary.measurement_reference, run_root=run_root,
        expected_scope=scope, expected_predicate="target-cpu-delta-measurement",
    )
    if (
        observation.details.get("process_id") != summary.process_id
        or observation.details.get("nonce") != summary.nonce
        or observation.details.get("command_sha256") != summary.command_sha256
        or observation.details.get("minimum_cpu_ticks") != study.minimum_cpu_ticks
    ):
        raise ValueError("C0045 control measurement differs from guest selection")
    verdict = verify_retained_cpu_measurement(
        summary.measurement_reference, run_root=run_root, expected_scope=scope
    )
    if (
        verdict.cpu_ticks_delta != summary.cpu_ticks_delta
        or verdict.passed != summary.threshold_passed
    ):
        raise ValueError("C0045 control differs from replayed guest counters")
    if summary.control_kind == "controller_only":
        reply = ControllerCpuReply.model_validate_json(summary.controller_reply_json)
        if reply.nonce != summary.nonce:
            raise ValueError("C0045 controller workload differs from selected nonce")
    return summary
