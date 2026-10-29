"""Controls retain target measurements but never grant campaign effects."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from executors.c0045_compute_executor import C0045ProcessSelection
from runners.c0045_control_replay import verify_c0045_control
from runners.c0045_control_run import (
    BUSY_CONTROL_CODE, C0045ControlRecord, ControllerCpuReply,
    _guest_command, _idle_guest_command, _launch_controller_control,
    _observe_control, run_c0045_control,
)
from runners.capability_authority import LabShellRequest, acquire_registered_observation
from runners.capability_facts import FactScope
from runners.capability_observations import PredicateObservation, retain_observation
from runners.lab_runtime_bootstrap import LabBootstrapOutcome
from runners.target_compute_predicate import TargetProcessCpuSample
from runners.target_process_cpu_transport import GuestCpuAcquisition, _PROBE_PATH


NONCE = "controlnonce12345"


def _fake_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    def bootstrap(*, sut_profile_id, expected_host_id, principal, run_id,
                  environment_id, run_root, store):
        scope = FactScope(
            run_id=run_id, environment_id=environment_id, epoch="test-boot",
            locus="target", host_id=expected_host_id, principal=principal,
        )
        discovery = PredicateObservation(
            scope=scope, predicate_id="lifecycle-identity", passed=True,
            established_facts=(), details={},
        )
        discovery_reference = retain_observation(
            discovery, authority_id="lab-lifecycle", run_root=run_root
        )

        def shell(**_kwargs):
            return PredicateObservation(
                scope=scope, predicate_id="shell-nonce", passed=True,
                established_facts=("lab:shell",), details={},
            )

        monkeypatch.setattr("runners.capability_authority.observe_lab_shell", shell)
        shell_reference = acquire_registered_observation(
            "lab-shell",
            LabShellRequest(
                sut_profile_id=sut_profile_id, scope=scope, nonce="shellnonce01"
            ),
            run_root=run_root,
        )
        facts = store.add_observed(
            shell_reference, run_root=run_root, expected_scope=scope,
            expected_predicate="shell-nonce",
        )
        return LabBootstrapOutcome(
            scope=scope, discovery_reference=discovery_reference,
            reference=shell_reference, facts=facts,
        )

    monkeypatch.setattr(
        "runners.c0045_control_run.bootstrap_lab_authority", bootstrap
    )


def _fake_cpu_samples(monkeypatch: pytest.MonkeyPatch, ticks_after: int) -> None:
    calls = 0

    def acquire(request):
        nonlocal calls
        calls += 1
        ticks = 10 if calls == 1 else ticks_after
        sample = TargetProcessCpuSample(
            scope=request.scope, process_id=request.process_id,
            process_start_ticks=400, process_command_sha256=request.command_sha256,
            monotonic_ns=1000 * calls, user_cpu_ticks=ticks,
            system_cpu_ticks=2,
        )
        reply = {
            "nonce": request.nonce, "boot_id": request.scope.epoch,
            "hostname": request.scope.host_id,
            "principal": request.scope.principal,
            "process_id": request.process_id,
            "process_start_ticks": 400,
            "process_command_sha256": request.command_sha256,
            "monotonic_ns": sample.monotonic_ns,
            "user_cpu_ticks": ticks, "system_cpu_ticks": 2,
        }
        return GuestCpuAcquisition(
            sample=sample, reply_json=json.dumps(reply),
            probe_source_sha256=hashlib.sha256(_PROBE_PATH.read_bytes()).hexdigest(),
        )

    monkeypatch.setattr("runners.target_cpu_measurement.acquire_guest_cpu_sample", acquire)
    monkeypatch.setattr("runners.target_cpu_measurement.time.sleep", lambda _: None)


@pytest.mark.parametrize(
    ("cell_id", "ticks_after", "expected_pass"),
    [
        ("b1-busy", 20, True),
        ("b1-idle", 10, False),
        ("b1-controller_only", 10, False),
    ],
)
def test_control_cell_replays_without_campaign_fact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    cell_id: str, ticks_after: int, expected_pass: bool,
) -> None:
    monkeypatch.setattr(
        "runners.c0045_control_run.detect_lab_infrastructure", lambda _profile: "qemu"
    )
    _fake_bootstrap(monkeypatch)
    _fake_cpu_samples(monkeypatch, ticks_after)
    kind = cell_id.split("-", 1)[1]
    command_sha256 = (
        _guest_command(BUSY_CONTROL_CODE, NONCE, 15)[1]
        if kind == "busy" else _idle_guest_command(NONCE, 15)[1]
    )
    selected = C0045ProcessSelection(
        process_id=123, nonce=NONCE, command_sha256=command_sha256
    )
    monkeypatch.setattr(
        "runners.c0045_control_run._launch_guest_control", lambda _kind: selected
    )
    stopped = []
    monkeypatch.setattr(
        "runners.c0045_control_run._stop_selected_process",
        lambda _profile, selection: stopped.append(selection),
    )
    if kind == "controller_only":
        class FakeController:
            returncode = 0

            def communicate(self, timeout):
                assert timeout == 20
                return json.dumps({"nonce": NONCE, "cpu_seconds": 0.8}), ""

            def poll(self):
                return 0

        monkeypatch.setattr(
            "runners.c0045_control_run._launch_controller_control",
            lambda _nonce, _duration: FakeController(),
        )
    record, run_root = run_c0045_control(cell_id, tmp_path / "output")
    assert record.status == "measured"
    assert record.threshold_passed is expected_pass
    assert stopped == [selected]
    assert verify_c0045_control(run_root) == record
    measurement_dir = run_root / "observations"
    assert measurement_dir.is_dir()
    assert "compute:bounded_guest_cpu" not in record.model_dump_json()
    if kind == "busy":
        receipt = run_root / record.measurement_reference.record_path
        receipt.write_bytes(receipt.read_bytes() + b" ")
        with pytest.raises(ValueError, match="differ"):
            verify_c0045_control(run_root)


def test_absent_guest_retains_error_and_replay_refuses_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "runners.c0045_control_run.detect_lab_infrastructure", lambda _profile: ""
    )
    with pytest.raises(RuntimeError, match="reachable target guest"):
        run_c0045_control("b2-idle", tmp_path / "output")
    run_root = next((tmp_path / "output/c0045-control-series/b2-idle").iterdir())
    plan = C0045ControlRecord.model_validate_json((run_root / "plan.json").read_bytes())
    summary = C0045ControlRecord.model_validate_json((run_root / "summary.json").read_bytes())
    assert plan.status == "planned" and summary.status == "error"
    with pytest.raises(ValueError, match="no completed measurement"):
        verify_c0045_control(run_root)


def test_treatment_cell_cannot_run_through_control_path(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="typed treatment runner"):
        run_c0045_control("b1-treatment", tmp_path)


def test_controller_workload_reports_local_cpu_without_guest_effect() -> None:
    process = _launch_controller_control(NONCE, 1)
    stdout, stderr = process.communicate(timeout=5)
    assert process.returncode == 0 and stderr == ""
    reply = ControllerCpuReply.model_validate_json(stdout)
    assert reply.nonce == NONCE and reply.cpu_seconds > 0


def test_controller_launch_failure_still_cleans_selected_guest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected = C0045ProcessSelection(
        process_id=123, nonce=NONCE,
        command_sha256=_idle_guest_command(NONCE, 15)[1],
    )
    monkeypatch.setattr(
        "runners.c0045_control_run._launch_controller_control",
        lambda _nonce, _duration: (_ for _ in ()).throw(RuntimeError("launch failed")),
    )
    stopped = []
    monkeypatch.setattr(
        "runners.c0045_control_run._stop_selected_process",
        lambda _profile, selection: stopped.append(selection),
    )
    with pytest.raises(RuntimeError, match="launch failed"):
        _observe_control(
            "controller_only", selected,
            SimpleNamespace(scope=FactScope(
                run_id="run", environment_id="lab", epoch="boot",
                locus="target", host_id="target-linux-1", principal="rayuser",
            )),
            tmp_path,
        )
    assert stopped == [selected]
