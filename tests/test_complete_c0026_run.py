"""Completion must preserve observation failures and always attempt scoped teardown."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import complete_c0026_run as completion


def make_run(tmp_path: Path, exit_code: int = 0) -> Path:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    (workspace / "lab" / "vagrant" / "target-linux-1").mkdir(parents=True)
    (workspace / "scripts").mkdir()
    (run_root / "evidence").mkdir()
    (workspace / "scripts" / "probe_c0026_target.py").write_text("pass\n", encoding="utf-8")
    (run_root / "run_context.json").write_text(
        json.dumps({"campaign_id": "0.c0026", "keep_lab_requested": True,
                    "source_tree_sha256": "source-digest", "exit_code": exit_code}),
        encoding="utf-8",
    )
    return run_root


def test_complete_observes_then_destroys_then_finalizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if command[:3] == ["vagrant", "ssh", "-c"]:
            return SimpleNamespace(returncode=0, stdout=json.dumps({
                "schema": "c0026-target-chain-observation/v1"}), stderr="")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(completion.subprocess, "run", fake_run)
    completion.complete_run(run_root)

    assert [command[0] for command in calls] == ["vagrant", "bash", completion.sys.executable]
    assert calls[0][-1] == "sudo -n python3 -"
    assert calls[1][-2:] == ["--campaign", "0.c0026"]
    assert calls[2][-2:] == ["--run-root", str(run_root)]
    receipt = json.loads((run_root / "evidence" / "c0026-target-observation.json").read_text())
    transport = json.loads((run_root / "evidence" / "c0026-target-observation.transport.json").read_text())
    assert receipt["observation"]["schema"] == "c0026-target-chain-observation/v1"
    assert receipt["probe_sha256"] == transport["probe_sha256"]


def test_probe_failure_still_destroys_and_does_not_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    calls: list[str] = []

    def fake_run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command[0])
        if command[:3] == ["vagrant", "ssh", "-c"]:
            return SimpleNamespace(returncode=1, stdout="", stderr="probe failed")
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(completion.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError, match="target observation failed"):
        completion.complete_run(run_root)
    assert calls == ["vagrant", "bash"]
    assert not (run_root / "final_run_receipt.json").exists()
    assert json.loads((run_root / "evidence/c0026-target-observation.transport.json").read_text())[
        "exit_code"
    ] == 1


def test_invalid_caldera_journal_still_tears_down_without_certifying(tmp_path, monkeypatch):
    import subprocess
    run_root = make_run(tmp_path)
    (run_root / "evidence/caldera-session.json").write_text("{}")
    destroyed = []

    def reject(command, **kwargs):
        assert command[1].endswith("verify_caldera_run_journal.py")
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(completion.subprocess, "run", reject)
    monkeypatch.setattr(completion, "destroy_lab", destroyed.append)
    monkeypatch.setattr(completion, "observe_target", lambda _: pytest.fail("journal failed"))
    with pytest.raises(subprocess.CalledProcessError):
        completion.complete_run(run_root)
    assert destroyed == [run_root]
    assert not (run_root / "final_run_receipt.json").exists()


def test_failed_campaign_does_not_observe_or_finalize(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path, exit_code=1)
    destroyed: list[Path] = []
    monkeypatch.setattr(completion, "observe_target", lambda root: pytest.fail("observed"))
    monkeypatch.setattr(completion, "destroy_lab", destroyed.append)
    with pytest.raises(ValueError, match="Campaign failed"):
        completion.complete_run(run_root)
    assert destroyed == [run_root]
    assert not (run_root / "final_run_receipt.json").exists()


def test_observation_and_teardown_failures_are_both_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    monkeypatch.setattr(completion, "observe_target", lambda root: (_ for _ in ()).throw(ValueError("probe")))
    monkeypatch.setattr(completion, "destroy_lab", lambda root: (_ for _ in ()).throw(OSError("teardown")))
    with pytest.raises(BaseExceptionGroup) as failure:
        completion.complete_run(run_root)
    assert [str(error) for error in failure.value.exceptions] == ["probe", "teardown"]
