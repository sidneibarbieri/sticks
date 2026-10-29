"""Regression checks for the post-observation isolated-run seal."""

import json
import hashlib
import sys
from pathlib import Path

import pytest

from scripts import finalize_isolated_lab_run as finalizer
from scripts.run_isolated_lab_campaign import tree_manifest, write_json


def make_run(tmp_path: Path) -> Path:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    profile = workspace / "data" / "sut_profiles" / "0.c0026.yml"
    profile.parent.mkdir(parents=True)
    profile.write_text("requirements:\n  required_vms: [target-base]\n", encoding="utf-8")
    vm_dir = workspace / "lab" / "vagrant" / "target-linux-1"
    vm_dir.mkdir(parents=True)
    (vm_dir / "Vagrantfile").write_text("# fixture\n", encoding="utf-8")

    artifacts = workspace / "data" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "runner.txt").write_text("synthetic\n", encoding="utf-8")
    artifact_manifest = tree_manifest(artifacts)
    write_json(run_root / "artifact_manifest.json", artifact_manifest)

    evidence = run_root / "evidence"
    summary = evidence / "0.c0026_001" / "summary.json"
    summary.parent.mkdir(parents=True)
    write_json(summary, {
        "campaign_id": "0.c0026",
        "total_techniques": 1,
        "successful": 1,
        "failed": 0,
        "skipped": 0,
    })
    initial_manifest = tree_manifest(evidence)
    write_json(run_root / "evidence_manifest.json", initial_manifest)
    probe = workspace / "scripts/probe_c0026_target.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("print('fixture')\n", encoding="utf-8")
    probe_digest = hashlib.sha256(probe.read_bytes()).hexdigest()
    write_json(run_root / "source_manifest.json", {
        "tree_sha256": "source-digest",
        "files": [{"path": "scripts/probe_c0026_target.py", "sha256": probe_digest}],
    })
    execution_log = run_root / "execution.log"
    execution_log.write_bytes(b"synthetic campaign output\n")
    write_json(run_root / "run_context.json", {
        "campaign_id": "0.c0026",
        "exit_code": 0,
        "keep_lab_requested": True,
        "source_tree_sha256": "source-digest",
        "evidence_tree_sha256": initial_manifest["tree_sha256"],
        "artifact_tree_sha256": artifact_manifest["tree_sha256"],
        "execution_log_path": execution_log.name,
        "execution_log_sha256": finalizer.sha256_file(execution_log),
    })
    observation = {
        "schema": "c0026-target-chain-observation/v1",
        "hostname": "target-linux-1",
        "boot_id": "synthetic-boot",
        "observer_uid": 0,
        "collection_sha256": "a" * 64,
        "archive_sha256": "b" * 64,
        "chunk_count": 2,
        "scope": "Synthetic guest fixture chain",
        "checks": {"synthetic_effect": True},
        "passed": True,
    }
    write_json(evidence / "c0026-target-observation.transport.json", {
        "exit_code": 0, "stdout": json.dumps(observation), "stderr": "",
        "probe_sha256": probe_digest,
    })
    write_json(evidence / "c0026-target-observation.json", {
        "schema": "c0026-target-observer-receipt/v1",
        "campaign_id": "0.c0026",
        "source_tree_sha256": "source-digest",
        "probe_sha256": probe_digest,
        "observation": observation,
    })
    return run_root


def make_c0010_run(
    tmp_path: Path,
    executor_name: str = "executors.executor_registry.execute_t1588_002_real",
) -> Path:
    run_root = make_run(tmp_path)
    workspace = run_root / "workspace"
    (workspace / "data/sut_profiles/0.c0026.yml").rename(
        workspace / "data/sut_profiles/0.c0010.yml"
    )
    evidence = run_root / "evidence"
    (evidence / "0.c0026_001").rename(evidence / "0.c0010_001")
    summary_path = evidence / "0.c0010_001/summary.json"
    write_json(summary_path, {
        "campaign_id": "0.c0010", "total_techniques": 1,
        "successful": 1, "failed": 0, "skipped": 0,
        "technique_results": [{
            "technique_id": "T1588.002", "status": "success",
            "executor_name": executor_name,
        }],
    })
    (evidence / "c0026-target-observation.json").unlink()
    (evidence / "c0026-target-observation.transport.json").unlink()
    initial_manifest = tree_manifest(evidence)
    write_json(run_root / "evidence_manifest.json", initial_manifest)

    probe = workspace / "scripts/probe_c0010_target.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("print('fixture')\n", encoding="utf-8")
    probe_digest = hashlib.sha256(probe.read_bytes()).hexdigest()
    write_json(run_root / "source_manifest.json", {
        "tree_sha256": "source-digest",
        "files": [{"path": "scripts/probe_c0010_target.py", "sha256": probe_digest}],
    })
    context = json.loads((run_root / "run_context.json").read_text(encoding="utf-8"))
    context["campaign_id"] = "0.c0010"
    context["evidence_tree_sha256"] = initial_manifest["tree_sha256"]
    write_json(run_root / "run_context.json", context)

    checks = {
        "declared_notice_present": True,
        "declared_page_present": True,
        "download_executable": True,
        "http_get_recorded": True,
        "transfer_matches_source": True,
    }
    observation = {
        "schema": "c0010-target-transfer-observation/v1",
        "hostname": "target-linux-1",
        "boot_id": "synthetic-boot",
        "checks": checks,
        "passed": True,
    }
    write_json(evidence / "c0010-target-observation.transport.json", {
        "exit_code": 0,
        "stdout": json.dumps(observation),
        "stderr": "",
        "probe_sha256": probe_digest,
    })
    write_json(evidence / "c0010-target-observation.json", {
        "schema": "c0010-target-observer-receipt/v1",
        "campaign_id": "0.c0010",
        "source_tree_sha256": "source-digest",
        "probe_sha256": probe_digest,
        "observation": observation,
    })
    return run_root


@pytest.mark.parametrize("executor_name", [
    "executors.executor_registry.execute_t1588_002_real",
    "executors.executor_registry.execute_t1588_002_simulated",
])
def test_c0010_receipt_seals_transport_probe_and_runner(tmp_path: Path, monkeypatch, executor_name) -> None:
    run_root = make_c0010_run(tmp_path, executor_name)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")

    receipt = finalizer.build_receipt(run_root)

    assert receipt["campaign_id"] == "0.c0010"
    assert receipt["runner_successful"] == 1
    assert receipt["observer_checks"]["transfer_matches_source"] is True
    assert receipt["vm_states"] == {"target-linux-1": "not_created"}


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("missing_check", "missing or extra checks"),
        ("transport_failure", "not bound to the run"),
        ("wrong_probe", "not bound to the run"),
        ("wrong_executor", "incompatible or unrecorded executor"),
    ],
)
def test_c0010_receipt_rejects_unbound_observation(
    tmp_path: Path, monkeypatch, mutation: str, message: str
) -> None:
    run_root = make_c0010_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    evidence = run_root / "evidence"
    if mutation == "missing_check":
        receipt_path = evidence / "c0010-target-observation.json"
        payload = json.loads(receipt_path.read_text(encoding="utf-8"))
        del payload["observation"]["checks"]["http_get_recorded"]
        write_json(receipt_path, payload)
        transport_path = evidence / "c0010-target-observation.transport.json"
        transport = json.loads(transport_path.read_text(encoding="utf-8"))
        transport["stdout"] = json.dumps(payload["observation"])
        write_json(transport_path, transport)
    elif mutation == "transport_failure":
        transport_path = evidence / "c0010-target-observation.transport.json"
        payload = json.loads(transport_path.read_text(encoding="utf-8"))
        payload["exit_code"] = 1
        write_json(transport_path, payload)
    elif mutation == "wrong_probe":
        (run_root / "workspace/scripts/probe_c0010_target.py").write_text(
            "print('altered')\n", encoding="utf-8"
        )
    elif mutation == "wrong_executor":
        summary_path = evidence / "0.c0010_001/summary.json"
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        payload["technique_results"][0]["executor_name"] = "executors.shadowray_fixed_executors.execute_t1588_002_shadowray_fixed"
        write_json(summary_path, payload)
        observer_files = [
            evidence / "c0010-target-observation.json",
            evidence / "c0010-target-observation.transport.json",
        ]
        for observer_file in observer_files:
            observer_file.rename(tmp_path / observer_file.name)
        initial_manifest = tree_manifest(evidence)
        for observer_file in observer_files:
            (tmp_path / observer_file.name).rename(observer_file)
        write_json(run_root / "evidence_manifest.json", initial_manifest)
        context_path = run_root / "run_context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["evidence_tree_sha256"] = initial_manifest["tree_sha256"]
        write_json(context_path, context)

    with pytest.raises(ValueError, match=message):
        finalizer.build_receipt(run_root)


def test_final_receipt_seals_observer_and_teardown(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")

    receipt = finalizer.build_receipt(run_root)
    assert receipt["cycle_passed"] is True
    assert receipt["vm_states"] == {"target-linux-1": "not_created"}
    assert receipt["observation_sha256"] == finalizer.sha256_file(
        run_root / "evidence" / "c0026-target-observation.json"
    )
    assert receipt["final_evidence_tree_sha256"] == tree_manifest(run_root / "evidence")[
        "tree_sha256"
    ]
    assert receipt["execution_log_sha256"] == finalizer.sha256_file(
        run_root / "execution.log"
    )
    assert receipt["observer_transport_sha256"] == finalizer.sha256_file(
        run_root / "evidence/c0026-target-observation.transport.json"
    )


@pytest.mark.parametrize("mutation", [
    "missing_transport", "transport_failure", "changed_stdout", "wrong_probe",
    "changed_source", "wrong_campaign",
])
def test_c0026_receipt_rejects_unbound_guest_observation(
    tmp_path: Path, monkeypatch, mutation: str,
) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    evidence = run_root / "evidence"
    transport_path = evidence / "c0026-target-observation.transport.json"
    receipt_path = evidence / "c0026-target-observation.json"
    if mutation == "missing_transport":
        transport_path.unlink()
    elif mutation == "changed_source":
        (run_root / "workspace/scripts/probe_c0026_target.py").write_text(
            "print('changed')\n", encoding="utf-8"
        )
    elif mutation == "wrong_campaign":
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt["campaign_id"] = "0.c0010"
        write_json(receipt_path, receipt)
    else:
        transport = json.loads(transport_path.read_text(encoding="utf-8"))
        if mutation == "transport_failure":
            transport["exit_code"] = 1
        elif mutation == "changed_stdout":
            transport["stdout"] = "{}"
        else:
            transport["probe_sha256"] = "0" * 64
        write_json(transport_path, transport)

    with pytest.raises((ValueError, FileNotFoundError)):
        finalizer.build_receipt(run_root)


def test_final_receipt_rejects_changed_execution_log(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    (run_root / "execution.log").write_bytes(b"changed\n")

    with pytest.raises(ValueError, match="Execution log differs from the run context"):
        finalizer.build_receipt(run_root)


def test_final_receipt_accepts_older_run_without_execution_log(
    tmp_path: Path, monkeypatch
) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    context_path = run_root / "run_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    del context["execution_log_path"]
    del context["execution_log_sha256"]
    write_json(context_path, context)
    (run_root / "execution.log").unlink()

    assert "execution_log_sha256" not in finalizer.build_receipt(run_root)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("runner_evidence", "Initial runner evidence changed"),
        ("observer_rejected", "not bound to the run and guest transport"),
        ("extra_evidence", "Unexpected independent observation files"),
        ("runner_failed", "Runner did not finish"),
        ("artifact_changed", "Runner artifacts changed"),
    ],
)
def test_final_receipt_rejects_inconsistent_run(
    tmp_path: Path, monkeypatch, mutation: str, message: str
) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    evidence = run_root / "evidence"
    if mutation == "runner_evidence":
        (evidence / "0.c0026_001" / "summary.json").write_text("{}\n", encoding="utf-8")
    elif mutation == "observer_rejected":
        observer = evidence / "c0026-target-observation.json"
        payload = json.loads(observer.read_text(encoding="utf-8"))
        payload["observation"]["checks"]["synthetic_effect"] = False
        write_json(observer, payload)
    elif mutation == "extra_evidence":
        (evidence / "unexpected.txt").write_text("unexpected\n", encoding="utf-8")
    elif mutation == "runner_failed":
        context = run_root / "run_context.json"
        payload = json.loads(context.read_text(encoding="utf-8"))
        payload["exit_code"] = 1
        write_json(context, payload)
    elif mutation == "artifact_changed":
        (run_root / "workspace" / "data" / "artifacts" / "runner.txt").write_text(
            "changed\n", encoding="utf-8"
        )

    with pytest.raises(ValueError, match=message):
        finalizer.build_receipt(run_root)


def test_final_receipt_rejects_running_vm(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "running")

    with pytest.raises(ValueError, match="not all been destroyed"):
        finalizer.build_receipt(run_root)


def test_verify_rejects_tampered_receipt(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    receipt_path = run_root / finalizer.FINAL_RECEIPT
    receipt = finalizer.build_receipt(run_root)
    receipt["runner_successful"] = 99
    write_json(receipt_path, receipt)
    monkeypatch.setattr(sys, "argv", [
        "finalize_isolated_lab_run.py", "--run-root", str(run_root), "--verify",
    ])

    with pytest.raises(ValueError, match="no longer matches"):
        finalizer.main()


SHADOWRAY_CHECKS = {
    "transfer_matches_source": True,
    "http_get_recorded": True,
    "backup_matches_fixture": True,
    "toolkit_files_executable": True,
}


def make_shadowray_run(tmp_path: Path) -> Path:
    run_root = make_run(tmp_path)
    workspace = run_root / "workspace"
    (workspace / "data/sut_profiles/0.c0026.yml").rename(
        workspace / "data/sut_profiles/0.shadowray.yml"
    )
    evidence = run_root / "evidence"
    (evidence / "0.c0026_001").rename(evidence / "0.shadowray_001")
    write_json(evidence / "0.shadowray_001/summary.json", {
        "campaign_id": "0.shadowray", "total_techniques": 2,
        "successful": 2, "failed": 0, "skipped": 0,
        "technique_results": [
            {"technique_id": "T1105", "status": "success",
             "execution_mode": "real_controlled",
             "executor_name": "executors.shadowray_fixed_executors.execute_t1105_shadowray_fixed",
             "capabilities_produced": ["artifacts:downloaded_tool"]},
            {"technique_id": "T1003.008", "status": "success",
             "execution_mode": "naive_simulated",
             "executor_name": "executors.shadowray_fixed_executors.execute_t1003_008_shadowray_vm",
             "capabilities_produced": ["simulation:credential_access_probe_recorded"]},
        ],
    })
    (evidence / "c0026-target-observation.json").unlink()
    (evidence / "c0026-target-observation.transport.json").unlink()
    initial_manifest = tree_manifest(evidence)
    write_json(run_root / "evidence_manifest.json", initial_manifest)

    probe = workspace / "scripts/probe_shadowray_target.py"
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("print('fixture')\n", encoding="utf-8")
    probe_digest = hashlib.sha256(probe.read_bytes()).hexdigest()
    campaign = workspace / "campaigns/0.shadowray.json"
    campaign.parent.mkdir(parents=True)
    write_json(campaign, {"campaign_id": "0.shadowray", "techniques": [
        {"technique_id": "T1105", "expected_mode": "real_controlled",
         "produces": ["artifacts:downloaded_tool"]},
        {"technique_id": "T1003.008", "expected_mode": "naive_simulated",
         "produces": ["simulation:credential_access_probe_recorded"]},
    ]})
    campaign_digest = hashlib.sha256(campaign.read_bytes()).hexdigest()
    write_json(run_root / "source_manifest.json", {
        "tree_sha256": "source-digest",
        "files": [
            {"path": "scripts/probe_shadowray_target.py", "sha256": probe_digest},
            {"path": "campaigns/0.shadowray.json", "sha256": campaign_digest},
        ],
    })
    context_path = run_root / "run_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["campaign_id"] = "0.shadowray"
    context["evidence_tree_sha256"] = initial_manifest["tree_sha256"]
    write_json(context_path, context)

    observation = {
        "schema": "shadowray-fixture-observation/v1",
        "hostname": "target-linux-1", "boot_id": "synthetic-boot",
        "observer_uid": 0, "checks": SHADOWRAY_CHECKS, "passed": True,
        "files": {"fixture": {"sha256": "0" * 64}},
        "http_log": {"sha256": "1" * 64},
        "scope": "Retained fixtures only; no proof of escalation, historical fidelity, "
                 "executor identity, shell-startup behavior, or cross-host ingress.",
    }
    write_json(evidence / "shadowray-target-observation.transport.json", {
        "exit_code": 0, "stdout": json.dumps(observation), "stderr": "",
        "probe_sha256": probe_digest,
    })
    write_json(evidence / "shadowray-target-observation.json", {
        "schema": "shadowray-target-observer-receipt/v1",
        "campaign_id": "0.shadowray", "source_tree_sha256": "source-digest",
        "probe_sha256": probe_digest, "observation": observation,
    })
    return run_root


def test_shadowray_receipt_seals_guest_transport_and_simulation_scope(tmp_path: Path, monkeypatch) -> None:
    run_root = make_shadowray_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")

    receipt = finalizer.build_receipt(run_root)

    assert receipt["campaign_id"] == "0.shadowray"
    assert receipt["observer_checks"] == SHADOWRAY_CHECKS
    assert receipt["runner_successful"] == 2
    assert "Retained fixtures" in receipt["scope"]


@pytest.mark.parametrize(("mutation", "message"), [
    ("missing_check", "missing or extra checks"),
    ("wrong_probe", "not bound"),
    ("transport_failure", "not bound"),
    ("simulation_product", "unscoped simulated product"),
    ("running_vm", "not all been destroyed"),
])
def test_shadowray_receipt_fails_closed(
    tmp_path: Path, monkeypatch, mutation: str, message: str
) -> None:
    run_root = make_shadowray_run(tmp_path)
    monkeypatch.setattr(
        finalizer, "read_vm_state", lambda _: "running" if mutation == "running_vm" else "not_created"
    )
    evidence = run_root / "evidence"
    if mutation == "missing_check":
        path = evidence / "shadowray-target-observation.json"
        receipt = json.loads(path.read_text(encoding="utf-8"))
        del receipt["observation"]["checks"]["http_get_recorded"]
        write_json(path, receipt)
        path = evidence / "shadowray-target-observation.transport.json"
        transport = json.loads(path.read_text(encoding="utf-8"))
        transport["stdout"] = json.dumps(receipt["observation"])
        write_json(path, transport)
    elif mutation == "wrong_probe":
        (run_root / "workspace/scripts/probe_shadowray_target.py").write_text(
            "print('altered')\n", encoding="utf-8"
        )
    elif mutation == "transport_failure":
        path = evidence / "shadowray-target-observation.transport.json"
        transport = json.loads(path.read_text(encoding="utf-8"))
        transport["exit_code"] = 1
        write_json(path, transport)
    elif mutation == "simulation_product":
        path = evidence / "0.shadowray_001/summary.json"
        summary = json.loads(path.read_text(encoding="utf-8"))
        summary["technique_results"][1]["capabilities_produced"] = ["access:privileged"]
        write_json(path, summary)
        observer_files = [
            evidence / "shadowray-target-observation.json",
            evidence / "shadowray-target-observation.transport.json",
        ]
        for observer_file in observer_files:
            observer_file.rename(tmp_path / observer_file.name)
        initial_manifest = tree_manifest(evidence)
        for observer_file in observer_files:
            (tmp_path / observer_file.name).rename(observer_file)
        write_json(run_root / "evidence_manifest.json", initial_manifest)
        context_path = run_root / "run_context.json"
        context = json.loads(context_path.read_text(encoding="utf-8"))
        context["evidence_tree_sha256"] = initial_manifest["tree_sha256"]
        write_json(context_path, context)

    with pytest.raises(ValueError, match=message):
        finalizer.build_receipt(run_root)


def make_outer_space_run(tmp_path: Path) -> Path:
    run_root = make_run(tmp_path)
    workspace = run_root / "workspace"
    evidence = run_root / "evidence"
    (workspace / "data/sut_profiles/0.c0026.yml").unlink()
    (evidence / "0.c0026_001").rename(evidence / "0.outer_space_001")
    controlled = {"T1105", "T1217"}
    technique_ids = [
        "T1105", "T1584.004", "T1217", "T1071.001",
        "T1585.003", "T1027.013", "T1587.001", "T1059.005",
    ]
    write_json(evidence / "0.outer_space_001/summary.json", {
        "campaign_id": "0.outer_space", "total_techniques": 8,
        "successful": 8, "failed": 0, "skipped": 0,
        "technique_results": [
            {
                "technique_id": technique_id,
                "status": "success",
                "execution_mode": "real_controlled" if technique_id in controlled else "naive_simulated",
                "host": "",
                "executor_name": (
                    f"executors.executor_registry.execute_{technique_id.lower().replace('.', '_')}_real"
                    if technique_id in controlled else "executors.simulated_executor"
                ),
            }
            for technique_id in technique_ids
        ],
    })
    (evidence / "c0026-target-observation.json").unlink()
    (evidence / "c0026-target-observation.transport.json").unlink()
    initial_manifest = tree_manifest(evidence)
    write_json(run_root / "evidence_manifest.json", initial_manifest)

    browser_path = "/home/clouduser/.mozilla/firefox/profiles.ini"
    profile = workspace / "data/sut_profiles/0.outer_space.yml"
    profile.write_text(
        "requirements:\n  required_vms: [target-base]\n"
        "sut_configuration:\n  target-base:\n    files:\n"
        f"      - path: {browser_path}\n"
        "        content: 'browser\\n'\n        owner: clouduser\n"
        "        permissions: '644'\n",
        encoding="utf-8",
    )
    artifacts = workspace / "data/artifacts"
    browser_report = artifacts / "0.outer_space_browser_discovery.txt"
    browser_report.write_text(f"[identity] clouduser\n{browser_path}\n", encoding="utf-8")
    artifact_manifest = tree_manifest(artifacts)
    write_json(run_root / "artifact_manifest.json", artifact_manifest)

    paths = {
        "profile_sha256": profile,
        "browser_report_sha256": browser_report,
        "probe_sha256": workspace / "scripts/probe_controlled_target.py",
        "validator_sha256": workspace / "src/validators/controlled_target_observer.py",
        "cli_sha256": workspace / "scripts/observe_controlled_target.py",
    }
    for name, path in paths.items():
        if name in {"profile_sha256", "browser_report_sha256"}:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {name}\n", encoding="utf-8")
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    source_files = [
        {"path": path.relative_to(workspace).as_posix(), "sha256": hashes[name]}
        for name, path in paths.items() if name != "browser_report_sha256"
    ]
    write_json(run_root / "source_manifest.json", {
        "tree_sha256": "source-digest", "files": source_files,
    })
    context = json.loads((run_root / "run_context.json").read_text(encoding="utf-8"))
    context.update(
        campaign_id="0.outer_space",
        evidence_tree_sha256=initial_manifest["tree_sha256"],
        artifact_tree_sha256=artifact_manifest["tree_sha256"],
    )
    write_json(run_root / "run_context.json", context)

    observation = {
        "hostname": "target-linux-1", "boot_id": "synthetic-boot",
        "files": [{
            "path": browser_path,
            "sha256": hashlib.sha256(b"browser\\n").hexdigest(),
            "owner": "clouduser", "mode": "644", "owner_read_exit_code": 0,
        }],
        "payload_sha256": hashlib.sha256(b"#!/bin/sh\necho STICKS benign payload\n").hexdigest(),
        "server_log": '"GET /payload.sh HTTP/1.1" 200',
        "mac_addresses": {
            "primary": "52:54:00:aa:bb:cc", "private": "52:54:00:dd:ee:ff",
        },
    }
    write_json(evidence / "outer-space-target-observation.json.transport.json", {
        "transport_exit_code": 0, "stdout": json.dumps(observation), "stderr": "",
        **hashes, "changed_inputs": [],
    })
    write_json(evidence / "outer-space-target-observation.json", {
        **hashes, "changed_inputs": [], "observation": observation,
        "errors": [], "passed": True,
    })
    return run_root


def test_outer_space_finalizer_binds_guest_observation_and_source(tmp_path: Path, monkeypatch) -> None:
    run_root = make_outer_space_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")

    receipt = finalizer.build_receipt(run_root)

    assert receipt["campaign_id"] == "0.outer_space"
    assert receipt["runner_successful"] == 8
    assert receipt["observer_checks"]["browser_and_fixture_consistent"]


@pytest.mark.parametrize("corruption", [
    "guest_stdout", "input_digest", "transport_failure", "fixture_owner", "browser_report",
])
def test_outer_space_finalizer_rejects_unbound_evidence(
    tmp_path: Path, monkeypatch, corruption: str,
) -> None:
    run_root = make_outer_space_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    evidence = run_root / "evidence"
    transport_path = evidence / "outer-space-target-observation.json.transport.json"
    transport = json.loads(transport_path.read_text(encoding="utf-8"))
    if corruption == "guest_stdout":
        raw_observation = json.loads(transport["stdout"])
        raw_observation["hostname"] = "controller"
        transport["stdout"] = json.dumps(raw_observation)
    elif corruption == "input_digest":
        transport["probe_sha256"] = "0" * 64
    elif corruption == "transport_failure":
        transport["transport_exit_code"] = 1
    elif corruption == "fixture_owner":
        raw_observation = json.loads(transport["stdout"])
        raw_observation["files"][0]["owner"] = "root"
        transport["stdout"] = json.dumps(raw_observation)
        receipt_path = evidence / "outer-space-target-observation.json"
        observer_receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        observer_receipt["observation"] = raw_observation
        write_json(receipt_path, observer_receipt)
    else:
        (run_root / "workspace/data/artifacts/0.outer_space_browser_discovery.txt").write_text(
            "[identity] controller\n", encoding="utf-8",
        )
    if corruption != "browser_report":
        write_json(transport_path, transport)

    with pytest.raises(ValueError):
        finalizer.build_receipt(run_root)


def test_outer_space_finalizer_rejects_simulation_promoted_to_guest(
    tmp_path: Path, monkeypatch,
) -> None:
    run_root = make_outer_space_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    summary_path = run_root / "evidence/0.outer_space_001/summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["technique_results"][1]["execution_mode"] = "real_controlled"
    write_json(summary_path, summary)
    observation_path = run_root / "evidence/outer-space-target-observation.json"
    transport_path = run_root / "evidence/outer-space-target-observation.json.transport.json"
    observation_path.rename(run_root / "outer-space-target-observation.json")
    transport_path.rename(run_root / "outer-space-target-observation.json.transport.json")
    initial_manifest = tree_manifest(run_root / "evidence")
    (run_root / "outer-space-target-observation.json").rename(observation_path)
    (run_root / "outer-space-target-observation.json.transport.json").rename(transport_path)
    write_json(run_root / "evidence_manifest.json", initial_manifest)
    context_path = run_root / "run_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["evidence_tree_sha256"] = initial_manifest["tree_sha256"]
    write_json(context_path, context)

    with pytest.raises(ValueError, match="Outer Space runner classification"):
        finalizer.build_receipt(run_root)


def test_outer_space_finalizer_rejects_unbound_controlled_executor(
    tmp_path: Path, monkeypatch,
) -> None:
    run_root = make_outer_space_run(tmp_path)
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    summary_path = run_root / "evidence/0.outer_space_001/summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["technique_results"][0]["executor_name"] = "controller_simulation"
    write_json(summary_path, summary)
    observation_path = run_root / "evidence/outer-space-target-observation.json"
    transport_path = run_root / "evidence/outer-space-target-observation.json.transport.json"
    observation_path.rename(run_root / "outer-space-target-observation.json")
    transport_path.rename(run_root / "outer-space-target-observation.json.transport.json")
    initial_manifest = tree_manifest(run_root / "evidence")
    observation_path.parent.mkdir(exist_ok=True)
    (run_root / "outer-space-target-observation.json").rename(observation_path)
    (run_root / "outer-space-target-observation.json.transport.json").rename(transport_path)
    write_json(run_root / "evidence_manifest.json", initial_manifest)
    context_path = run_root / "run_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["evidence_tree_sha256"] = initial_manifest["tree_sha256"]
    write_json(context_path, context)

    with pytest.raises(ValueError, match="Outer Space runner classification"):
        finalizer.build_receipt(run_root)
