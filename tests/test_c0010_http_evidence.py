"""C0010 local HTTP observations must match the content actually staged."""

import subprocess

import pytest

from executors import legacy_campaign_executors as executors
from executors.executor_registry import execute_technique


class LocalServerDouble:
    """Stand in for the server process while preserving executor validation."""

    def terminate(self) -> None:
        pass

    def wait(self, timeout: int) -> int:
        return 0


def test_drive_by_visit_fetches_staged_content_on_controller(monkeypatch, tmp_path):
    """The local compatibility path fetches both staged files over HTTP."""
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    executors.execute_t1608_004_real("0.c0010", "0.c0010")

    completed, output, error, artifacts = executors.execute_t1189_real("0.c0010", "0.c0010")

    assert completed is True
    assert "127.0.0.1" in output
    assert error == ""
    assert artifacts == [str(tmp_path / "0.c0010_drive_by_visit.log")]
    visit_log = (tmp_path / "0.c0010_drive_by_visit.log").read_text(encoding="utf-8")
    assert "Israeli Shipping Login" in visit_log
    assert "STICKS benign drive-by profile script" in visit_log


def test_local_page_fetch_does_not_grant_initial_access(monkeypatch, tmp_path):
    """Controller HTTP activity cannot establish target-side initial access."""
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    executors.execute_t1608_004_real("0.c0010", "0.c0010")

    evidence = execute_technique(
        technique_id="T1189",
        available_capabilities=["network:http_available"],
        campaign_id="0.c0010",
        sut_profile_id="0.c0010",
    )

    assert evidence.status == "success"
    assert "access:initial" not in evidence.capabilities_produced
    assert "controller:watering_hole_fetched" in evidence.capabilities_produced


def test_drive_by_visit_requires_prior_staging(monkeypatch, tmp_path):
    """A missing earlier product must not be created by the consumer."""
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)

    with pytest.raises(FileNotFoundError, match="watering-hole content"):
        executors.execute_t1189_real("0.c0010", "0.c0010")

    assert not (tmp_path / "0.c0010_watering_hole").exists()
    assert not (tmp_path / "0.c0010_drive_by_visit.log").exists()


def test_drive_by_visit_rejects_unexpected_http_body(monkeypatch, tmp_path):
    """A successful curl exit with unrelated content is not a staged-page visit."""
    monkeypatch.setattr(executors, "ARTIFACTS_DIR", tmp_path)
    executors.execute_t1608_004_real("0.c0010", "0.c0010")
    monkeypatch.setattr(executors, "_reserve_local_port", lambda: 18080)
    monkeypatch.setattr(executors.subprocess, "Popen", lambda *args, **kwargs: LocalServerDouble())

    def curl_reply(command, **options):
        body = "unrelated response" if command[-1].endswith("index.html") else (
            "console.log('STICKS benign drive-by profile script');\n"
        )
        return subprocess.CompletedProcess(command, 0, body, "")

    monkeypatch.setattr(executors.subprocess, "run", curl_reply)

    with pytest.raises(ValueError, match="staged HTTP content"):
        executors.execute_t1189_real("0.c0010", "0.c0010")
    assert not (tmp_path / "0.c0010_drive_by_visit.log").exists()
