"""C0010 completion requires the nine reviewed, bound runtime outcomes."""

import ast
import hashlib
import json
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from executors import executor_registry, legacy_campaign_executors
from runners import (
    c0010_controller_observers,
    c0010_guest_observer,
    campaign_runner,
    lab_bootstrap_observer,
    lab_runtime_bootstrap,
)
from scripts import finalize_isolated_lab_run as finalizer
from scripts.run_isolated_lab_campaign import tree_manifest, write_json
from scripts.typed_runtime_seal import validate_c0010_typed_completion

SOURCE_PATHS = (
    "data/runtime_contracts/c0010.json",
    "src/executors/executor_registry.py",
    "src/executors/legacy_campaign_executors.py",
    "data/observer_specs/c0010_controller.json",
    "src/runners/c0010_controller_observers.py",
    "src/runners/c0010_http_observer.py",
    "src/runners/c0010_guest_observer.py",
    "scripts/probe_c0010_controller.py",
    "scripts/probe_c0010_http.py",
    "scripts/probe_c0010_target.py",
)


def _guest_reply(bash_script: str) -> str:
    code = shlex.split(bash_script)[2]
    if "module={'__name__':'c0010_preflight'}" in code:
        nonce = next(
            keyword.value.value
            for node in ast.walk(ast.parse(code))
            if isinstance(node, ast.Call)
            for keyword in node.keywords
            if keyword.arg == "nonce"
        )
        return json.dumps(
            {
                "hostname": "target-linux-1",
                "principal": "ubuntu",
                "observer_uid": 1000,
                "boot_id": "test-boot",
                "nonce": nonce,
                "notice_matches": True,
                "page_matches": True,
            }
        )
    if "module={'__name__':'c0010_probe'}" in code:
        nonce = re.search(r"observation\['nonce'\]='([^']+)'", code)
        assert nonce is not None
        return json.dumps(
            {
                "schema": "c0010-target-transfer-observation/v1",
                "hostname": "target-linux-1",
                "principal": "ubuntu",
                "observer_uid": 1000,
                "boot_id": "test-boot",
                "nonce": nonce.group(1),
                "payload_sha256": "b088ddaef2625e7f19f1ef1031b8af0617d4e849134d367bde139c77b7ad7be9",
                "checks": {
                    "declared_notice_present": True,
                    "declared_page_present": True,
                    "transfer_matches_source": True,
                    "http_get_recorded": True,
                    "download_executable": True,
                },
                "passed": True,
                "scope": "bounded test fixture",
            }
        )
    nonce = next(
        keyword.value.value
        for node in ast.walk(ast.parse(code))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "dict"
        for keyword in node.keywords
        if keyword.arg == "nonce"
    )
    return json.dumps(
        {
            "hostname": "target-linux-1",
            "principal": "ubuntu",
            "boot_id": "test-boot",
            "nonce": nonce,
        }
    )


def prepared(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_root = Path(__file__).resolve().parents[1]
    runtime_root = tmp_path / "runtime"
    runtime_root.mkdir()
    (runtime_root / "data/artifacts").mkdir(parents=True)
    monkeypatch.chdir(runtime_root)
    monkeypatch.setattr(campaign_runner, "PROJECT_ROOT", runtime_root)
    monkeypatch.setattr(campaign_runner, "detect_lab_infrastructure", lambda _: "qemu")
    monkeypatch.setattr(
        legacy_campaign_executors, "ARTIFACTS_DIR", runtime_root / "data/artifacts"
    )
    monkeypatch.setattr(
        executor_registry, "ARTIFACTS_DIR", runtime_root / "data/artifacts"
    )
    monkeypatch.setattr(c0010_controller_observers, "_PROJECT_ROOT", runtime_root)

    def transport(sut_profile_id: str, bash_script: str, **options):
        assert sut_profile_id == "0.c0010"
        assert options["execution_user"] == "ubuntu"
        stdout = (
            _guest_reply(bash_script)
            if bash_script.startswith("python3 -c ")
            else "guest command completed\n"
        )
        return subprocess.CompletedProcess(["guest-fixture"], 0, stdout, "")

    def topology_probe(vm_name: str, nonce: str, **options):
        return subprocess.CompletedProcess(
            ["topology-fixture", vm_name],
            0,
            f"{nonce}\t{vm_name}-fixture\ttest-boot\n",
            "",
        )

    for module in (
        executor_registry,
        c0010_guest_observer,
        lab_bootstrap_observer,
        lab_runtime_bootstrap,
    ):
        monkeypatch.setattr(module, "run_bash_on_target_vm", transport)
    monkeypatch.setattr(
        lab_runtime_bootstrap, "detect_vagrant_provider", lambda: "qemu"
    )
    monkeypatch.setattr(lab_runtime_bootstrap, "probe_vm_identity", topology_probe)

    runner = campaign_runner.UnifiedCampaignRunner(
        "0.c0010", tmp_path / "output", require_lab=True
    )
    report = runner.run()
    assert report.failed == 0, [
        (step.contract.occurrence, step.error_type, step.error_message)
        for step in report.steps
        if step.status not in {"observed", "simulated"}
    ]
    workspace = tmp_path / "seal-workspace"
    entries = []
    for relative in SOURCE_PATHS:
        target = workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_root / relative, target)
        entries.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
            }
        )
    payload = json.loads((runner.evidence_dir / "summary.json").read_text())
    return payload, runner.evidence_dir, workspace, {"files": entries}


def test_c0010_typed_completion_accepts_bounded_full_cycle(tmp_path, monkeypatch):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    report = validate_c0010_typed_completion(payload, evidence, workspace, manifest)
    assert (report.effects_observed, report.simulated, report.failed) == (5, 4, 0)
    assert sum(step.contract.scope.locus == "target" for step in report.steps) == 1


@pytest.mark.parametrize(
    "alteration",
    [
        "drop_step",
        "promote_simulation",
        "shift_guest",
        "missing_observation",
        "source_drift",
    ],
)
def test_c0010_typed_completion_rejects_broken_evidence(
    tmp_path, monkeypatch, alteration
):
    payload, evidence, workspace, manifest = prepared(tmp_path, monkeypatch)
    if alteration == "drop_step":
        payload["steps"].pop()
        payload["total_techniques"] = 8
        payload["effects_observed"] = 4
    elif alteration == "promote_simulation":
        payload["steps"][0]["status"] = "observed"
    elif alteration == "shift_guest":
        payload["steps"][8]["contract"]["scope"]["locus"] = "controller"
    elif alteration == "missing_observation":
        reference = payload["steps"][8]["outcome"]["observation_references"][0]
        (evidence / reference["record_path"]).unlink()
    else:
        (workspace / "src/executors/executor_registry.py").write_text("changed source")
    with pytest.raises((ValueError, FileNotFoundError)):
        validate_c0010_typed_completion(payload, evidence, workspace, manifest)


def _isolated_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    payload, evidence, source_workspace, _ = prepared(tmp_path, monkeypatch)
    run_root = tmp_path / "isolated-run"
    workspace = run_root / "workspace"
    shutil.copytree(source_workspace, workspace)
    profile = workspace / "data/sut_profiles/0.c0010.yml"
    profile.parent.mkdir(parents=True)
    profile.write_text(
        "requirements:\n  required_vms: [caldera, attacker, target-base]\n",
        encoding="utf-8",
    )
    artifacts = workspace / "data/artifacts"
    artifacts.mkdir(parents=True)
    for vm_name in ("caldera", "attacker", "target-linux-1"):
        vm_path = workspace / "lab/vagrant" / vm_name
        vm_path.mkdir(parents=True)
        (vm_path / "Vagrantfile").write_text("# isolated fixture\n", encoding="utf-8")
    source_manifest = tree_manifest(workspace)
    write_json(run_root / "source_manifest.json", source_manifest)
    write_json(run_root / "artifact_manifest.json", tree_manifest(artifacts))
    summary_path = run_root / "evidence/runtime-v2" / payload["run_id"]
    shutil.copytree(evidence, summary_path)
    evidence_manifest = tree_manifest(run_root / "evidence")
    write_json(run_root / "evidence_manifest.json", evidence_manifest)
    execution_log = run_root / "execution.log"
    execution_log.write_text("synthetic typed C0010 fixture\n", encoding="utf-8")
    write_json(
        run_root / "run_context.json",
        {
            "campaign_id": "0.c0010",
            "exit_code": 0,
            "keep_lab_requested": False,
            "source_tree_sha256": source_manifest["tree_sha256"],
            "evidence_tree_sha256": evidence_manifest["tree_sha256"],
            "artifact_tree_sha256": tree_manifest(artifacts)["tree_sha256"],
            "execution_log_path": "execution.log",
            "execution_log_sha256": finalizer.sha256_file(execution_log),
        },
    )
    monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "not_created")
    return run_root


def test_c0010_typed_finalizer_accepts_isolated_cycle(tmp_path, monkeypatch):
    run_root = _isolated_run(tmp_path, monkeypatch)
    monkeypatch.setattr(finalizer, "unchanged_initial_evidence", lambda *_: None)
    monkeypatch.setattr(
        finalizer,
        "validate_c0010_observation",
        lambda *_: (SimpleNamespace(checks={"fixture": True}), {}),
    )
    receipt = finalizer.build_receipt(run_root)
    assert receipt["schema"] == "isolated-c0010-typed-receipt/v1"
    assert (
        receipt["controller_effects_observed"],
        receipt["guest_effects_observed"],
        receipt["simulated"],
    ) == (4, 1, 4)
    assert set(receipt["vm_states"].values()) == {"not_created"}


@pytest.mark.parametrize("alteration", ["log", "source", "evidence", "vm_state"])
def test_c0010_typed_finalizer_rejects_broken_cycle(tmp_path, monkeypatch, alteration):
    run_root = _isolated_run(tmp_path, monkeypatch)
    monkeypatch.setattr(finalizer, "unchanged_initial_evidence", lambda *_: None)
    monkeypatch.setattr(
        finalizer,
        "validate_c0010_observation",
        lambda *_: (SimpleNamespace(checks={"fixture": True}), {}),
    )
    if alteration == "log":
        (run_root / "execution.log").write_text("changed", encoding="utf-8")
    elif alteration == "source":
        (run_root / "workspace/data/runtime_contracts/c0010.json").write_text(
            "{}", encoding="utf-8"
        )
    elif alteration == "evidence":
        summary = next((run_root / "evidence/runtime-v2").glob("*/summary.json"))
        summary.write_text("{}", encoding="utf-8")
    else:
        monkeypatch.setattr(finalizer, "read_vm_state", lambda _: "running")
    with pytest.raises((ValueError, FileNotFoundError)):
        finalizer.build_receipt(run_root)


def test_c0010_observer_files_are_the_only_post_run_evidence_additions(
    tmp_path, monkeypatch
):
    run_root = _isolated_run(tmp_path, monkeypatch)
    evidence = run_root / "evidence"
    allowed = finalizer.OBSERVATION_FILES["0.c0010"]
    for path in allowed:
        (evidence / path).write_text("{}\n", encoding="utf-8")

    finalizer.unchanged_initial_evidence(run_root, tree_manifest(evidence), allowed)

    (evidence / "unexpected.json").write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Unexpected independent observation files"):
        finalizer.unchanged_initial_evidence(run_root, tree_manifest(evidence), allowed)
