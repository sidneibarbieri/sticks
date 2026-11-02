"""The comparison execution arm must never fall back to an SSH-only run."""

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "controlled_execution_cli", ROOT / "scripts/run_controlled_execution_arm.py"
)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


def test_runtime_runs_only_inside_selected_caldera_session(tmp_path, monkeypatch):
    active = []
    report = type("Report", (), {"run_id": "run-1"})()
    runtime = tmp_path / "runtime"
    summary = runtime / "runtime-v2/run-1/summary.json"
    session_path = tmp_path / "session.json"
    session_path.write_bytes(b'{"session":"original"}')

    @contextmanager
    def session(path, journal):
        assert path == runtime / "caldera-session.json"
        assert path.read_bytes() == session_path.read_bytes()
        assert journal == runtime / "caldera-dispatch"
        active.append(True)
        yield
        active.clear()

    class Runner:
        def __init__(self, campaign, *, output_dir, require_lab):
            assert active and require_lab
            assert campaign == "0.c0026" and output_dir == runtime

        def run(self):
            assert active
            summary.parent.mkdir(parents=True)
            summary.write_bytes(b'{"retained":true}')
            return report

    monkeypatch.setattr(driver, "campaign_caldera_session", session)
    monkeypatch.setattr(driver, "UnifiedCampaignRunner", Runner)
    monkeypatch.setattr(driver, "RuntimeCampaignReport", type(report))

    actual, retained = driver._execute_runtime(
        "0.c0026", runtime, caldera_session_path=session_path
    )

    assert actual is report and retained == summary.read_bytes()
    assert not active


def test_session_failure_never_invokes_runtime(tmp_path, monkeypatch):
    session_path = tmp_path / "session.json"
    session_path.write_bytes(b'{"session":"original"}')
    @contextmanager
    def failed_session(*args):
        raise ValueError("target boot changed")
        yield

    def forbidden(*args, **kwargs):
        pytest.fail("runtime must not start without a valid CALDERA session")

    monkeypatch.setattr(driver, "campaign_caldera_session", failed_session)
    monkeypatch.setattr(driver, "UnifiedCampaignRunner", forbidden)
    with pytest.raises(ValueError, match="target boot changed"):
        driver._execute_runtime(
            "0.c0026", tmp_path / "runtime", caldera_session_path=session_path
        )


def test_unregistered_campaign_is_rejected_before_transport(tmp_path, monkeypatch):
    def forbidden(*args):
        pytest.fail("unsupported campaign must fail before opening a session")

    monkeypatch.setattr(driver, "campaign_caldera_session", forbidden)
    with pytest.raises(ValueError, match="lacks CALDERA transport support"):
        driver._execute_runtime(
            "0.unsupported", tmp_path, caldera_session_path=tmp_path / "session.json"
        )


def test_cli_requires_explicit_caldera_session(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["execution", "--collection-dir", ".",
        "--campaign", "C0026", "--seed", "1", "--output-dir", "run"])
    with pytest.raises(SystemExit) as error:
        driver.parse_args()
    assert error.value.code == 2
