"""An HTTP attempt cannot become a successful T1190 effect by default."""

import subprocess
from pathlib import Path

import pytest

from executors import executor_registry


@pytest.mark.parametrize(
    ("return_code", "response", "expected_success"),
    [
        (0, "No declared file content", False),
        (7, "root:synthetic", False),
        (0, "root:synthetic", True),
    ],
)
def test_t1190_status_requires_completed_response(
    monkeypatch, tmp_path: Path, return_code: int, response: str, expected_success: bool,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        executor_registry.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], return_code, response, "connection failed" if return_code else "",
        ),
    )

    success, stdout, stderr, artifacts = executor_registry.execute_t1190_real(
        "0.operation_midnighteclipse", "0.operation_midnighteclipse",
    )

    assert success is expected_success
    assert len(artifacts) == 1
    log = Path(artifacts[0]).read_text(encoding="utf-8")
    assert f"Exit code: {return_code}" in log
    assert response in log
    if return_code:
        assert stderr == "connection failed"
    if not expected_success:
        assert "exploit successful" not in stdout.lower()


def test_t1190_timeout_preserves_original_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(executor_registry.subprocess, "run", timeout)

    with pytest.raises(subprocess.TimeoutExpired):
        executor_registry.execute_t1190_real(
            "0.operation_midnighteclipse", "0.operation_midnighteclipse",
        )


def test_t1190_http_failure_does_not_produce_initial_access(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)

    def failed_http_request(command, **kwargs):
        assert "-f" in command[1]
        return subprocess.CompletedProcess(command, 22, "root:synthetic", "HTTP 404")

    monkeypatch.setattr(executor_registry.subprocess, "run", failed_http_request)
    evidence = executor_registry.execute_technique(
        technique_id="T1190",
        available_capabilities=["network:http_available"],
        campaign_id="0.operation_midnighteclipse",
        sut_profile_id="0.operation_midnighteclipse",
    )

    assert evidence.status == "failed"
    assert evidence.capabilities_produced == []
    assert "HTTP 404" in evidence.stderr


def test_t1190_response_marker_does_not_grant_initial_access(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        executor_registry.subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, 0, "root:synthetic", "",
        ),
    )

    evidence = executor_registry.execute_technique(
        technique_id="T1190",
        available_capabilities=["network:http_available"],
        campaign_id="0.operation_midnighteclipse",
        sut_profile_id="0.operation_midnighteclipse",
    )

    assert evidence.status == "success"
    assert evidence.capabilities_produced == ["observation:http_root_marker"]
    assert "access:initial" not in evidence.capabilities_produced
