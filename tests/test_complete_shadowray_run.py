"""ShadowRay completion preserves observation errors and scopes teardown."""

import json
import subprocess
from pathlib import Path

import pytest

from scripts import complete_shadowray_run as completion


def make_run(tmp_path: Path, exit_code: int = 0) -> Path:
    run_root = tmp_path / "run"
    (run_root / "workspace/scripts").mkdir(parents=True)
    (run_root / "evidence").mkdir()
    (run_root / "run_context.json").write_text(json.dumps({
        "campaign_id": "0.shadowray", "keep_lab_requested": True,
        "exit_code": exit_code,
    }), encoding="utf-8")
    return run_root


def test_completion_observes_destroys_and_seals(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    calls = []
    monkeypatch.setattr(completion, "observe_target", lambda _: calls.append("observe"))
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: calls.append("finalize"))

    completion.complete_run(run_root)

    assert calls == ["observe", "destroy", "finalize"]


def test_failed_observer_still_destroys_without_sealing(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    calls = []

    def fail(_: Path) -> None:
        raise ValueError("guest failed")

    monkeypatch.setattr(completion, "observe_target", fail)
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: pytest.fail("sealed failed run"))

    with pytest.raises(ValueError, match="guest failed"):
        completion.complete_run(run_root)
    assert calls == ["destroy"]


def test_failed_run_destroys_without_observing(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path, exit_code=1)
    calls = []
    monkeypatch.setattr(completion, "observe_target", lambda _: pytest.fail("observed failed run"))
    monkeypatch.setattr(completion, "destroy_lab", lambda _: calls.append("destroy"))
    monkeypatch.setattr(completion, "finalize_run", lambda _: pytest.fail("sealed failed run"))

    with pytest.raises(ValueError, match="Campaign failed"):
        completion.complete_run(run_root)
    assert calls == ["destroy"]


def test_teardown_error_does_not_mask_observer_error(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)

    def fail_observer(_: Path) -> None:
        raise ValueError("guest failed")

    def fail_teardown(_: Path) -> None:
        raise subprocess.CalledProcessError(3, ["destroy_lab.sh"])

    monkeypatch.setattr(completion, "observe_target", fail_observer)
    monkeypatch.setattr(completion, "destroy_lab", fail_teardown)
    with pytest.raises(BaseExceptionGroup) as failure:
        completion.complete_run(run_root)
    assert len(failure.value.exceptions) == 2
    assert "guest failed" in str(failure.value.exceptions[0])


def test_destroy_targets_only_shadowray(tmp_path: Path, monkeypatch) -> None:
    run_root = make_run(tmp_path)
    commands = []
    monkeypatch.setattr(completion.subprocess, "run", lambda command, **kwargs: commands.append(command))

    completion.destroy_lab(run_root)

    assert commands == [["bash", str(run_root / "workspace/scripts/destroy_lab.sh"),
                         "--campaign", "0.shadowray"]]
