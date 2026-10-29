"""Guest-only ShadowRay observer transport and receipt boundaries."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import observe_shadowray_target as observer


def make_run(tmp_path: Path) -> Path:
    run_root = tmp_path / "run"
    (run_root / "workspace/scripts").mkdir(parents=True)
    (run_root / "workspace/lab/vagrant/target-linux-1").mkdir(parents=True)
    (run_root / "evidence").mkdir()
    (run_root / "workspace/scripts/probe_shadowray_target.py").write_text(
        "print('fixture')\n", encoding="utf-8"
    )
    (run_root / "run_context.json").write_text(json.dumps({
        "campaign_id": "0.shadowray", "exit_code": 0,
        "keep_lab_requested": True, "source_tree_sha256": "source-digest",
    }), encoding="utf-8")
    return run_root


def observation() -> dict:
    return {
        "schema": "shadowray-fixture-observation/v1",
        "hostname": "target-linux-1", "boot_id": "synthetic-boot",
        "observer_uid": 0,
        "checks": {
            "transfer_matches_source": True,
            "http_get_recorded": True,
            "backup_matches_fixture": True,
            "toolkit_files_executable": True,
        },
        "passed": True,
        "files": {"fixture": {"sha256": "0" * 64}},
        "http_log": {"sha256": "1" * 64},
        "scope": "Retained fixtures only; no proof of escalation, historical fidelity, "
                 "executor identity, shell-startup behavior, or cross-host ingress.",
    }


def test_shadowray_observer_records_guest_transport(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps(observation()), "")

    monkeypatch.setattr(observer.subprocess, "run", fake_run)
    monkeypatch.setattr(sys, "argv", ["observe_shadowray_target.py", "--run-root", str(run_root)])

    assert observer.main() == 0
    receipt = json.loads((run_root / "evidence/shadowray-target-observation.json").read_text())
    transport = json.loads((run_root / "evidence/shadowray-target-observation.transport.json").read_text())
    assert receipt["observation"] == observation()
    assert transport["exit_code"] == 0
    assert calls[0][0] == ["vagrant", "ssh", "-c", "sudo -n python3 -"]
    assert calls[0][1]["cwd"] == run_root / "workspace/lab/vagrant/target-linux-1"


def test_shadowray_observer_preserves_failed_transport(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(
        observer.subprocess, "run",
        lambda command, **kwargs: subprocess.CompletedProcess(command, 17, "", "guest error"),
    )
    monkeypatch.setattr(sys, "argv", ["observe_shadowray_target.py", "--run-root", str(run_root)])

    with pytest.raises(RuntimeError, match="exited 17"):
        observer.main()
    transport = json.loads((run_root / "evidence/shadowray-target-observation.transport.json").read_text())
    assert transport["stderr"] == "guest error"
    assert not (run_root / "evidence/shadowray-target-observation.json").exists()


def test_shadowray_observer_does_not_overwrite(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    (run_root / "evidence/shadowray-target-observation.json").write_text("preserved\n")
    monkeypatch.setattr(sys, "argv", ["observe_shadowray_target.py", "--run-root", str(run_root)])

    with pytest.raises(FileExistsError):
        observer.main()
