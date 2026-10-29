"""The ShadowRay credential probe records access status without file contents."""

import json
import subprocess
from pathlib import Path

import pytest

from executors import shadowray_fixed_executors as shadowray


def test_probe_records_only_access_status(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    commands = []

    def run_probe(*, sut_profile_id, bash_script, timeout):
        commands.append(bash_script)
        return subprocess.CompletedProcess([], 0, "sudo-readable\n", "")

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", run_probe)
    success, stdout, stderr, artifacts = shadowray.execute_t1003_008_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )

    assert success
    assert not stderr
    assert "sudo-readable" in stdout
    assert "cat /etc/passwd" not in commands[0]
    assert "head -5 /etc/shadow" not in commands[0]
    assert "sudo -n test -r /etc/shadow" in commands[0]
    assert len(artifacts) == 1
    assert Path(artifacts[0]).read_text(encoding="utf-8") == "sudo-readable\n"


def test_probe_rejects_unexpected_guest_output_without_persisting_it(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    def run_probe(*, sut_profile_id, bash_script, timeout):
        return subprocess.CompletedProcess([], 0, "root:$6$unexpected-hash\n", "")

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", run_probe)
    with pytest.raises(ValueError, match="Unexpected credential probe output"):
        shadowray.execute_t1003_008_shadowray_vm("0.shadowray", "0.shadowray")
    assert not (tmp_path / "data/artifacts/shadowray_credentials_probe.txt").exists()


def test_probe_preserves_guest_process_error(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def run_probe(*, sut_profile_id, bash_script, timeout):
        return subprocess.CompletedProcess([], 23, "", "guest transport failed")

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", run_probe)
    success, stdout, stderr, artifacts = shadowray.execute_t1003_008_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert not success
    assert not stdout
    assert stderr == "guest transport failed"
    assert not artifacts


def test_manifest_and_executor_keep_probe_simulated():
    campaign_path = Path(__file__).resolve().parents[1] / "campaigns/0.shadowray.json"
    campaign = json.loads(campaign_path.read_text(encoding="utf-8"))
    step = next(
        step for step in campaign["techniques"] if step["technique_id"] == "T1003.008"
    )
    assert step["expected_mode"] == "naive_simulated"
    assert step["expected_fidelity"] == shadowray.metadata_t1003_008.execution_fidelity.value
    assert step["produces"] == shadowray.metadata_t1003_008.produces
    assert all(product.startswith("simulation:") for product in step["produces"])
