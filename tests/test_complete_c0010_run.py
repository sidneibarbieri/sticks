"""A C0010 completion must tear down its own lab even after observation failure."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts import complete_c0010_run as completion


def test_invalid_caldera_journal_still_tears_down(tmp_path, monkeypatch):
    run_root = make_run(tmp_path)
    (run_root / "evidence/caldera-session.json").write_text("{}")
    calls = []

    def reject_journal(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(completion.subprocess, "run", reject_journal)
    monkeypatch.setattr(completion, "observe_target", lambda _: calls.append("observe"))
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: calls.append("finalize"))
    with pytest.raises(subprocess.CalledProcessError):
        completion.complete_run(run_root)
    assert calls == ["destroy"]


def make_run(tmp_path: Path, exit_code: int = 0) -> Path:
    run_root = tmp_path / "run"
    workspace = run_root / "workspace"
    (workspace / "scripts").mkdir(parents=True)
    (run_root / "evidence").mkdir()
    (run_root / "run_context.json").write_text(
        json.dumps({
            "campaign_id": "0.c0010",
            "keep_lab_requested": True,
            "exit_code": exit_code,
        }),
        encoding="utf-8",
    )
    return run_root


def test_completion_observes_tears_down_and_finalizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(completion, "observe_target", lambda _: calls.append("observe"))
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: calls.append("finalize"))

    completion.complete_run(run_root)

    assert calls == ["observe", "destroy", "finalize"]


def test_observer_failure_still_tears_down_without_finalizing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    calls: list[str] = []

    def failed_observation(_: Path) -> None:
        calls.append("observe")
        raise ValueError("bad guest observation")

    monkeypatch.setattr(completion, "observe_target", failed_observation)
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: calls.append("finalize"))

    with pytest.raises(ValueError, match="bad guest observation"):
        completion.complete_run(run_root)
    assert calls == ["observe", "destroy"]


def test_failed_runner_tears_down_without_observing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path, exit_code=1)
    calls: list[str] = []
    monkeypatch.setattr(completion, "observe_target", lambda _: calls.append("observe"))
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: calls.append("finalize"))

    with pytest.raises(ValueError, match="Campaign failed"):
        completion.complete_run(run_root)
    assert calls == ["destroy"]


def test_observation_and_teardown_errors_are_both_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)

    def failed_observation(_: Path) -> None:
        raise ValueError("observer failed")

    def failed_teardown(_: Path) -> None:
        raise subprocess.CalledProcessError(1, ["destroy_lab.sh"])

    monkeypatch.setattr(completion, "observe_target", failed_observation)
    monkeypatch.setattr(completion, "destroy_lab", failed_teardown)
    monkeypatch.setattr(completion, "finalize_run", lambda _: pytest.fail("finalized"))

    with pytest.raises(BaseExceptionGroup) as failure:
        completion.complete_run(run_root)
    assert len(failure.value.exceptions) == 2
    assert "observer failed" in str(failure.value.exceptions[0])


def test_teardown_is_scoped_to_c0010(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    commands: list[list[str]] = []

    def record_run(command: list[str], **kwargs: object) -> None:
        commands.append(command)

    monkeypatch.setattr(completion.subprocess, "run", record_run)
    completion.destroy_lab(run_root)
    assert len(commands) == 1
    assert commands[0][-2:] == ["--campaign", "0.c0010"]


def test_completion_resumes_after_persisted_observation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    evidence = run_root / "evidence"
    (evidence / "c0010-target-observation.json").write_text("{}", encoding="utf-8")
    (evidence / "c0010-target-observation.transport.json").write_text("{}", encoding="utf-8")
    calls: list[str] = []
    monkeypatch.setattr(completion, "observe_target", lambda _: calls.append("observe"))
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: calls.append("finalize"))

    completion.complete_run(run_root)

    assert calls == ["destroy", "finalize"]


def test_completion_rejects_partial_observation_but_tears_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_root = make_run(tmp_path)
    (run_root / "evidence/c0010-target-observation.transport.json").write_text(
        "{}", encoding="utf-8"
    )
    calls: list[str] = []
    monkeypatch.setattr(completion, "observe_target", lambda _: calls.append("observe"))
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: calls.append("finalize"))

    with pytest.raises(ValueError, match="Incomplete C0010 observation"):
        completion.complete_run(run_root)

    assert calls == ["destroy"]
