"""Run one scheduled C0045 calibration control without granting a campaign fact."""

import hashlib
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Literal, Self
from uuid import uuid4

from pydantic import Field, model_validator

from executors.c0045_compute_executor import C0045ProcessSelection, _stop_selected_process
from executors.lab_transport import detect_lab_infrastructure, run_bash_on_target_vm
from runners.c0045_compute_study import STUDY_PATH, load_c0045_compute_study
from runners.c0045_effect_series import (
    SERIES_PATH, c0045_series_sha256, load_c0045_effect_series,
)
from runners.capability_facts import Digest, Identity, ImmutableRecord, ObservationReference
from runners.capability_observations import _directory, _write_exclusive
from runners.capability_store import CapabilityStore
from runners.lab_runtime_bootstrap import LabBootstrapOutcome, bootstrap_lab_authority
from runners.target_cpu_measurement import measure_and_retain_target_cpu
from runners.target_process_cpu_transport import TargetCpuSampleRequest


BUSY_CONTROL_CODE = """import hashlib
import sys
import time

deadline = time.monotonic() + int(sys.argv[2])
counter = 0
while time.monotonic() < deadline:
    hashlib.blake2b(str(counter).encode(), digest_size=16).digest()
    counter += 1
"""
IDLE_WORKLOAD_CODE = """import sys
import time

time.sleep(int(sys.argv[2]))
"""
CONTROLLER_WORKLOAD_CODE = """import hashlib
import json
import sys
import time

started = time.process_time()
deadline = time.monotonic() + int(sys.argv[2])
counter = 0
while time.monotonic() < deadline:
    hashlib.sha256(str(counter).encode()).digest()
    counter += 1
print(json.dumps({"nonce": sys.argv[1], "cpu_seconds": time.process_time() - started}))
"""
CONTROL_SOURCE_PATH = Path(__file__).resolve()
ControlKind = Literal["busy", "idle", "controller_only"]


class ControllerCpuReply(ImmutableRecord):
    nonce: Identity
    cpu_seconds: float = Field(strict=True, gt=0)


class C0045ControlRecord(ImmutableRecord):
    """One selected boot/cell; a measurement cannot authorize a campaign effect."""

    schema_version: Literal["c0045-compute-control/v1"]
    cell_id: Identity
    control_kind: ControlKind
    run_id: Identity
    source_study_sha256: Digest
    series_sha256: Digest
    control_source_sha256: Digest
    infrastructure_provider: str
    bootstrap: LabBootstrapOutcome | None
    process_id: int | None
    nonce: Identity | None
    command_sha256: Digest | None
    measurement_reference: ObservationReference | None
    cpu_ticks_delta: int | None
    threshold_passed: bool | None
    controller_reply_json: str | None
    status: Literal["planned", "measured", "error"]
    error_type: str | None = None
    error_message: str | None = None

    @model_validator(mode="after")
    def validate_boundary(self) -> Self:
        if self.status == "planned" and any(
            value is not None for value in (
                self.bootstrap, self.process_id, self.nonce, self.command_sha256,
                self.measurement_reference, self.cpu_ticks_delta,
                self.threshold_passed, self.controller_reply_json,
            )
        ):
            raise ValueError("Planned control cannot contain acquired guest evidence")
        if self.status == "measured" and (
            self.bootstrap is None or self.process_id is None or self.nonce is None
            or self.command_sha256 is None or self.measurement_reference is None
            or self.cpu_ticks_delta is None or self.threshold_passed is None
        ):
            raise ValueError("Measured control requires selected guest and CPU receipt")
        if self.status == "measured" and (
            (self.control_kind == "controller_only") != (self.controller_reply_json is not None)
        ):
            raise ValueError("Controller-only control requires a controller CPU reply")
        if self.status == "error" and (self.error_type is None or self.error_message is None):
            raise ValueError("Failed control must retain its diagnostic")
        if self.status != "error" and (self.error_type is not None or self.error_message is not None):
            raise ValueError("Only a failed control can retain an error")
        return self


def _guest_command(code: str, nonce: str, duration_seconds: int) -> tuple[str, Digest]:
    argv = ("python3", "-c", code, nonce, str(duration_seconds))
    command_bytes = b"\0".join(argument.encode("utf-8") for argument in argv) + b"\0"
    script = (
        f"setsid python3 -c {shlex.quote(code)} "
        f"{shlex.quote(nonce)} {duration_seconds} "
        ">/dev/null 2>&1 </dev/null & echo $!"
    )
    return script, hashlib.sha256(command_bytes).hexdigest()


def _idle_guest_command(nonce: str, duration_seconds: int) -> tuple[str, Digest]:
    return _guest_command(IDLE_WORKLOAD_CODE, nonce, duration_seconds)


def _launch_guest_control(kind: ControlKind) -> C0045ProcessSelection:
    study = load_c0045_compute_study()
    nonce = uuid4().hex
    if kind == "busy":
        script, command_sha256 = _guest_command(
            BUSY_CONTROL_CODE, nonce, study.workload_duration_seconds
        )
    else:
        script, command_sha256 = _idle_guest_command(nonce, study.workload_duration_seconds)
    result = run_bash_on_target_vm(
        study.campaign_id, script,
        execution_user=study.target_principal, timeout=20,
    )
    result.check_returncode()
    if re.fullmatch(r"[1-9][0-9]*\n?", result.stdout) is None:
        raise ValueError("C0045 control launch did not return one guest PID")
    return C0045ProcessSelection(
        process_id=int(result.stdout.strip()), nonce=nonce,
        command_sha256=command_sha256,
    )


def _launch_controller_control(nonce: str, duration_seconds: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "-c", CONTROLLER_WORKLOAD_CODE, nonce, str(duration_seconds)],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, start_new_session=True,
    )


def _observe_control(
    kind: ControlKind,
    selected: C0045ProcessSelection,
    bootstrap: LabBootstrapOutcome,
    run_root: Path,
) -> tuple[ObservationReference, int, bool, str | None]:
    study = load_c0045_compute_study()
    controller = None
    measurement = None
    reply_json = None
    observation_error = None
    try:
        if kind == "controller_only":
            controller = _launch_controller_control(
                selected.nonce, study.workload_duration_seconds
            )
        measurement = measure_and_retain_target_cpu(
            TargetCpuSampleRequest(
                sut_profile_id=study.campaign_id, scope=bootstrap.scope,
                process_id=selected.process_id, nonce=selected.nonce,
                command_sha256=selected.command_sha256,
            ),
            run_root=run_root, minimum_cpu_ticks=study.minimum_cpu_ticks,
            interval_seconds=study.sampling_interval_seconds,
        )
        if controller is not None:
            stdout, _stderr = controller.communicate(timeout=study.workload_duration_seconds + 5)
            if controller.returncode != 0:
                raise RuntimeError("Controller-only workload failed")
            reply = ControllerCpuReply.model_validate_json(stdout)
            if reply.nonce != selected.nonce:
                raise ValueError("Controller-only reply differs from its selected nonce")
            reply_json = stdout
    except Exception as error:
        observation_error = error
    cleanup_errors = []
    if controller is not None and controller.poll() is None:
        try:
            controller.terminate()
            controller.communicate(timeout=5)
        except Exception as error:
            cleanup_errors.append(error)
    try:
        _stop_selected_process(study.campaign_id, selected)
    except Exception as error:
        cleanup_errors.append(error)
    if observation_error is not None and cleanup_errors:
        raise ExceptionGroup("C0045 control observation and cleanup failed", [observation_error, *cleanup_errors])
    if observation_error is not None:
        raise observation_error
    if cleanup_errors:
        raise ExceptionGroup("C0045 control cleanup failed", cleanup_errors)
    if measurement is None:
        raise RuntimeError("C0045 control produced no CPU measurement")
    return (
        measurement.reference, measurement.verdict.cpu_ticks_delta,
        measurement.verdict.passed, reply_json,
    )


def _retain(record: C0045ControlRecord, run_root: Path, filename: str) -> None:
    with _directory(None, str(run_root)) as directory:
        _write_exclusive(directory, filename, record.model_dump_json().encode("utf-8"))


def run_c0045_control(
    cell_id: str, output_dir: Path, series_path: Path = SERIES_PATH
) -> tuple[C0045ControlRecord, Path]:
    """Measure only a selected control; treatment uses its separate typed runner."""
    series = load_c0045_effect_series(series_path)
    kind = series.arm_for(cell_id)
    if kind == "treatment":
        raise ValueError("C0045 treatment must use the typed treatment runner")
    study = load_c0045_compute_study()
    run_id = uuid4().hex
    run_root = output_dir / "c0045-control-series" / cell_id / run_id
    run_root.parent.mkdir(parents=True, exist_ok=True)
    run_root.mkdir(exist_ok=False)
    shared = {
        "schema_version": "c0045-compute-control/v1",
        "cell_id": cell_id, "control_kind": kind, "run_id": run_id,
        "source_study_sha256": hashlib.sha256(STUDY_PATH.read_bytes()).hexdigest(),
        "series_sha256": c0045_series_sha256(series_path),
        "control_source_sha256": hashlib.sha256(CONTROL_SOURCE_PATH.read_bytes()).hexdigest(),
    }
    _retain(C0045ControlRecord(
        **shared, infrastructure_provider="", bootstrap=None,
        process_id=None, nonce=None, command_sha256=None,
        measurement_reference=None, cpu_ticks_delta=None,
        threshold_passed=None, controller_reply_json=None, status="planned",
    ), run_root, "plan.json")
    provider = ""
    bootstrap = None
    selected = None
    try:
        provider = detect_lab_infrastructure(study.campaign_id)
        if not provider:
            raise RuntimeError("C0045 control requires a reachable target guest")
        bootstrap = bootstrap_lab_authority(
            sut_profile_id=study.campaign_id, expected_host_id=study.target_host_id,
            principal=study.target_principal, run_id=run_id,
            environment_id=f"lab-{run_id}", run_root=run_root,
            store=CapabilityStore(),
        )
        selected = _launch_guest_control(kind)
        reference, ticks, passed, controller_reply = _observe_control(
            kind, selected, bootstrap, run_root
        )
        record = C0045ControlRecord(
            **shared, infrastructure_provider=provider, bootstrap=bootstrap,
            process_id=selected.process_id, nonce=selected.nonce,
            command_sha256=selected.command_sha256,
            measurement_reference=reference, cpu_ticks_delta=ticks,
            threshold_passed=passed, controller_reply_json=controller_reply,
            status="measured",
        )
        _retain(record, run_root, "summary.json")
        return record, run_root
    except Exception as error:
        try:
            _retain(C0045ControlRecord(
                **shared, infrastructure_provider=provider, bootstrap=bootstrap,
                process_id=selected.process_id if selected else None,
                nonce=selected.nonce if selected else None,
                command_sha256=selected.command_sha256 if selected else None,
                measurement_reference=None, cpu_ticks_delta=None,
                threshold_passed=None, controller_reply_json=None,
                status="error", error_type=type(error).__name__,
                error_message=str(error),
            ), run_root, "summary.json")
        except Exception as retention_error:
            raise ExceptionGroup(
                "C0045 control and summary retention both failed", [error, retention_error]
            ) from None
        raise
