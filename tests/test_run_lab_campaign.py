from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_lab_campaign.py"
EVIDENCE_ROOT = PROJECT_ROOT / "release" / "evidence"
REQUIRES_LAB_EVIDENCE = pytest.mark.skipif(
    not EVIDENCE_ROOT.exists(),
    reason="requires lab-run evidence under release/evidence/ "
    "(produced by running the lab campaigns; not shipped in the repository)",
)


def _load_module():
    spec = importlib.util.spec_from_file_location("run_lab_campaign", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_success_path_runs_up_execute_collect_and_teardown(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []
    restored = {"value": False}
    cleaned = {"value": False}

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))

    class DummySnapshot:
        def restore(self) -> None:
            restored["value"] = True

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: DummySnapshot())
    monkeypatch.setattr(
        module, "_cleanup_runtime_outputs", lambda: cleaned.__setitem__("value", True)
    )

    exit_code = module.main(["--campaign", "0.c0026", "--provider", "qemu"])

    assert exit_code == 0
    assert restored["value"] is True
    assert cleaned["value"] is True
    assert calls == [
        ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026", "--provider", "qemu"],
        [sys.executable, str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0026", "--require-lab"],
        ["bash", str(module.COLLECT_EVIDENCE_SCRIPT)],
        [sys.executable, str(module.GENERATE_CORPUS_STATE_SCRIPT)],
        ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"],
    ]


def test_keep_lab_skips_teardown(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []
    restored = {"value": False}
    discarded = {"value": False}

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))

    class DummySnapshot:
        def restore(self) -> None:
            restored["value"] = True

        def discard(self) -> None:
            discarded["value"] = True

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: DummySnapshot())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    exit_code = module.main(["--campaign", "0.c0026", "--keep-lab"])

    assert exit_code == 0
    assert calls[-1] != ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"]
    assert calls[0] == ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026"]
    assert restored["value"] is False
    assert discarded["value"] is True


def test_isolated_evidence_output_never_refreshes_release_summaries(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))
        assert env["STICKS_EVIDENCE_DIR"] == str(tmp_path.resolve())

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module,
        "_capture_derived_state",
        lambda: type("Snapshot", (), {"restore": lambda self: None})(),
    )
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    exit_code = module.main(
        [
            "--campaign",
            "0.c0026",
            "--evidence-output",
            str(tmp_path),
        ]
    )

    assert exit_code == 0
    assert calls == [
        ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026"],
        [
            sys.executable,
            str(module.RUN_CAMPAIGN_SCRIPT),
            "--campaign",
            "0.c0026",
            "--require-lab",
            "--output",
            str(tmp_path.resolve()),
        ],
        ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"],
    ]


def test_teardown_runs_when_campaign_execution_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))
        if list(command)[1:] == [str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0010", "--require-lab"]:
            raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: type("S", (), {"restore": lambda self: None})())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    with pytest.raises(module.subprocess.CalledProcessError):
        module.main(["--campaign", "0.c0010"])

    assert calls[0] == ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0010"]
    assert calls[-1] == ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0010"]


@REQUIRES_LAB_EVIDENCE
def test_failure_still_refreshes_evidence_and_corpus_state(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))
        if list(command)[1:] == [str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0010", "--require-lab"]:
            raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: type("S", (), {"restore": lambda self: None})())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    with pytest.raises(module.subprocess.CalledProcessError):
        module.main(["--campaign", "0.c0010"])

    assert calls == [
        ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0010"],
        [sys.executable, str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0010", "--require-lab"],
        ["bash", str(module.COLLECT_EVIDENCE_SCRIPT)],
        [sys.executable, str(module.GENERATE_CORPUS_STATE_SCRIPT)],
        ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0010"],
    ]


def test_teardown_runs_when_up_lab_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))
        if list(command) == ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026"]:
            raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: type("S", (), {"restore": lambda self: None})())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    with pytest.raises(module.subprocess.CalledProcessError):
        module.main(["--campaign", "0.c0026"])

    assert calls == [
        ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026"],
        ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"],
    ]


@pytest.mark.parametrize("failed_stage", ["startup", "campaign"])
def test_keep_lab_tears_down_owned_lab_after_failure(
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: str,
) -> None:
    module = _load_module()
    calls: list[list[str]] = []
    up_command = ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026"]
    campaign_command = [
        sys.executable,
        str(module.RUN_CAMPAIGN_SCRIPT),
        "--campaign",
        "0.c0026",
        "--require-lab",
    ]
    failure_command = up_command if failed_stage == "startup" else campaign_command

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))
        if list(command) == failure_command:
            raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: type("S", (), {"restore": lambda self: None})())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    with pytest.raises(module.subprocess.CalledProcessError) as error:
        module.main(["--campaign", "0.c0026", "--keep-lab", "--skip-collect-evidence"])

    assert error.value.cmd == failure_command
    assert calls[-1] == ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"]


def test_keep_lab_preserves_unowned_lab_after_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []
    campaign_command = [
        sys.executable,
        str(module.RUN_CAMPAIGN_SCRIPT),
        "--campaign",
        "0.c0026",
        "--require-lab",
    ]

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))
        raise module.subprocess.CalledProcessError(returncode=1, cmd=command)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: type("S", (), {"restore": lambda self: None})())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    with pytest.raises(module.subprocess.CalledProcessError):
        module.main(
            ["--campaign", "0.c0026", "--assume-lab-running", "--keep-lab", "--skip-collect-evidence"]
        )

    assert calls == [campaign_command]


def test_skip_collect_evidence_avoids_post_run_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: type("S", (), {"restore": lambda self: None})())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    exit_code = module.main(["--campaign", "0.c0026", "--skip-collect-evidence"])

    assert exit_code == 0
    assert calls == [
        ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026"],
        [sys.executable, str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0026", "--require-lab"],
        ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"],
    ]


def test_assume_lab_running_skips_up_lab(monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "_capture_derived_state", lambda: type("S", (), {"restore": lambda self: None})())
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    exit_code = module.main(["--campaign", "0.c0026", "--assume-lab-running"])

    assert exit_code == 0
    assert calls == [
        [sys.executable, str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0026", "--require-lab"],
        ["bash", str(module.COLLECT_EVIDENCE_SCRIPT)],
        [sys.executable, str(module.GENERATE_CORPUS_STATE_SCRIPT)],
    ]


def test_explicitly_tearing_down_an_assumed_lab_requires_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    calls: list[list[str]] = []

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module,
        "_capture_derived_state",
        lambda: type("S", (), {"restore": lambda self: None})(),
    )
    monkeypatch.setattr(module, "_cleanup_runtime_outputs", lambda: None)

    exit_code = module.main(
        [
            "--campaign",
            "0.c0026",
            "--assume-lab-running",
            "--tear-down-assumed-lab",
            "--skip-collect-evidence",
        ]
    )

    assert exit_code == 0
    assert calls == [
        [sys.executable, str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0026", "--require-lab"],
        ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"],
    ]


def test_persist_derived_state_skips_restore_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = _load_module()
    calls: list[list[str]] = []
    capture_called = {"value": False}
    cleaned = {"value": False}

    def fake_run(command, cwd=None, check=None, env=None):
        calls.append(list(command))

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(
        module, "_capture_derived_state", lambda: capture_called.__setitem__("value", True)
    )
    monkeypatch.setattr(
        module, "_cleanup_runtime_outputs", lambda: cleaned.__setitem__("value", True)
    )

    exit_code = module.main(["--campaign", "0.c0026", "--persist-derived-state"])

    assert exit_code == 0
    assert capture_called["value"] is False
    assert cleaned["value"] is False
    assert calls == [
        ["bash", str(module.UP_LAB_SCRIPT), "--campaign", "0.c0026"],
        [sys.executable, str(module.RUN_CAMPAIGN_SCRIPT), "--campaign", "0.c0026", "--require-lab"],
        ["bash", str(module.COLLECT_EVIDENCE_SCRIPT)],
        [sys.executable, str(module.GENERATE_CORPUS_STATE_SCRIPT)],
        ["bash", str(module.DESTROY_LAB_SCRIPT), "--campaign", "0.c0026"],
    ]


def test_legacy_campaign_is_rejected_before_any_lab_operation(monkeypatch):
    module = _load_module()
    monkeypatch.setattr(module, "_capture_derived_state", lambda: pytest.fail("No state may be touched"))
    with pytest.raises(ValueError, match="typed runtime contract"):
        module.main(["--campaign", "0.c0011", "--provider", "qemu"])
