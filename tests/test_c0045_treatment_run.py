"""A C0045 run records its boundary even when no target guest is available."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from runners.c0045_treatment_run import C0045TreatmentRecord, run_c0045_treatment
from runners.c0045_treatment_replay import verify_c0045_treatment
from runners.capability_authority import LabShellRequest, acquire_registered_observation
from runners.capability_facts import FactScope
from runners.capability_observations import PredicateObservation, retain_observation
from runners.lab_runtime_bootstrap import LabBootstrapOutcome
from runners.target_compute_predicate import TargetProcessCpuSample
from runners.target_process_cpu_transport import GuestCpuAcquisition, _PROBE_PATH


def test_absent_guest_retains_plan_and_error_without_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "runners.c0045_treatment_run.detect_lab_infrastructure", lambda _profile: ""
    )
    with pytest.raises(RuntimeError, match="reachable target guest"):
        run_c0045_treatment(tmp_path / "output")

    run_roots = tuple((tmp_path / "output/c0045-prospective").iterdir())
    assert len(run_roots) == 1
    plan = C0045TreatmentRecord.model_validate_json(
        (run_roots[0] / "plan.json").read_bytes()
    )
    summary = C0045TreatmentRecord.model_validate_json(
        (run_roots[0] / "summary.json").read_bytes()
    )
    assert plan.status == "planned" and plan.outcome is None
    assert summary.status == "error" and summary.outcome is None
    assert summary.error_type == "RuntimeError"
    assert summary.uncollected_controls == ("busy", "idle", "controller_only")
    assert summary.source_mode == "naive_simulated"
    assert summary.treatment_mode == "real_controlled"
    with pytest.raises(ValueError, match="no completed target observation"):
        verify_c0045_treatment(run_roots[0])


def test_fake_guest_treatment_replays_and_detects_journal_tampering(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "runners.c0045_treatment_run.detect_lab_infrastructure",
        lambda _profile: "qemu",
    )

    def fake_bootstrap(*, sut_profile_id, expected_host_id, principal, run_id,
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

        def fake_shell(**_kwargs):
            return PredicateObservation(
                scope=scope, predicate_id="shell-nonce", passed=True,
                established_facts=("lab:shell",), details={},
            )

        monkeypatch.setattr("runners.capability_authority.observe_lab_shell", fake_shell)
        shell_reference = acquire_registered_observation(
            "lab-shell",
            LabShellRequest(sut_profile_id=sut_profile_id, scope=scope, nonce="shellnonce01"),
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
        "runners.c0045_treatment_run.bootstrap_lab_authority", fake_bootstrap
    )
    guest_calls = []

    def fake_guest(profile, script, *, execution_user, timeout):
        guest_calls.append(script)
        return subprocess.CompletedProcess(
            args=script, returncode=0,
            stdout="123\n" if len(guest_calls) == 1 else "", stderr="",
        )

    monkeypatch.setattr(
        "executors.c0045_compute_executor.run_bash_on_target_vm", fake_guest
    )
    sample_count = 0

    def fake_sample(request):
        nonlocal sample_count
        sample_count += 1
        ticks = 10 if sample_count == 1 else 20
        sample = TargetProcessCpuSample(
            scope=request.scope, process_id=request.process_id,
            process_start_ticks=400, process_command_sha256=request.command_sha256,
            monotonic_ns=1000 * sample_count, user_cpu_ticks=ticks,
            system_cpu_ticks=2,
        )
        reply = {
            "nonce": request.nonce, "boot_id": request.scope.epoch,
            "hostname": request.scope.host_id, "principal": request.scope.principal,
            "process_id": request.process_id,
            "process_start_ticks": sample.process_start_ticks,
            "process_command_sha256": request.command_sha256,
            "monotonic_ns": sample.monotonic_ns,
            "user_cpu_ticks": ticks, "system_cpu_ticks": 2,
        }
        return GuestCpuAcquisition(
            sample=sample, reply_json=json.dumps(reply),
            probe_source_sha256=hashlib.sha256(_PROBE_PATH.read_bytes()).hexdigest(),
        )

    monkeypatch.setattr(
        "runners.target_cpu_measurement.acquire_guest_cpu_sample", fake_sample
    )
    monkeypatch.setattr("runners.target_cpu_measurement.time.sleep", lambda _: None)

    record, run_root = run_c0045_treatment(tmp_path / "output")
    assert record.status == "observed"
    assert sample_count == 2 and len(guest_calls) == 2
    assert verify_c0045_treatment(run_root) == record

    journal = run_root / record.journal_references[-1].record_path
    journal.write_bytes(journal.read_bytes() + b" ")
    with pytest.raises(ValueError, match="journal bytes differ"):
        verify_c0045_treatment(run_root)
