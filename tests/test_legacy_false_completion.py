"""Selected legacy steps must not turn absent effects into completion."""

import subprocess

import pytest

from executors.executor_registry import execute_t1059_006_real, execute_t1190_real


@pytest.mark.parametrize("reply", ["", "<html>Not vulnerable</html>"])
def test_http_attempt_without_file_read_is_not_completed(monkeypatch, tmp_path, reply):
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **options: subprocess.CompletedProcess(command, 0, reply, ""),
    )
    completed, _, _, _ = execute_t1190_real(
        "0.operation_midnighteclipse", "0.operation_midnighteclipse"
    )
    assert completed is False
    assert (tmp_path / "data/artifacts/exploit_cve_2021_41773.log").is_file()


def test_http_launch_error_preserves_original_exception(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    original_error = FileNotFoundError("curl unavailable")

    def fail_to_launch(command, **options):
        raise original_error

    monkeypatch.setattr(subprocess, "run", fail_to_launch)
    with pytest.raises(FileNotFoundError) as caught:
        execute_t1190_real("0.operation_midnighteclipse", "0.operation_midnighteclipse")
    assert caught.value is original_error


def test_http_nonzero_return_cannot_report_success(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **options: subprocess.CompletedProcess(
            command, 23, "root:x:0:0:fixture", "original transport failure"
        ),
    )
    completed, _, error, artifacts = execute_t1190_real(
        "0.operation_midnighteclipse", "0.operation_midnighteclipse"
    )
    assert completed is False
    assert error == "original transport failure"
    assert "Exit code: 23" in (tmp_path / artifacts[0]).read_text()


def test_python_nonzero_return_is_not_reported_completed(monkeypatch, tmp_path):
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **options: subprocess.CompletedProcess(
            command, 23, "", "original failure"
        ),
    )
    with pytest.raises(subprocess.CalledProcessError) as caught:
        execute_t1059_006_real(
            "0.salesforce_data_exfiltration", "0.salesforce_data_exfiltration"
        )
    assert caught.value.returncode == 23
    assert caught.value.stderr == "original failure"


def test_python_launch_error_preserves_original_exception(monkeypatch, tmp_path):
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    original_error = FileNotFoundError("interpreter unavailable")

    def fail_to_launch(command, **options):
        raise original_error

    monkeypatch.setattr(subprocess, "run", fail_to_launch)
    with pytest.raises(FileNotFoundError) as caught:
        execute_t1059_006_real(
            "0.salesforce_data_exfiltration", "0.salesforce_data_exfiltration"
        )
    assert caught.value is original_error


def test_python_success_retains_controller_output(monkeypatch, tmp_path):
    (tmp_path / "data").mkdir()
    monkeypatch.chdir(tmp_path)
    completed, output, error, artifacts = execute_t1059_006_real(
        "0.salesforce_data_exfiltration", "0.salesforce_data_exfiltration"
    )
    assert completed is True
    assert "controller" in output
    assert error == ""
    assert len(artifacts) == 2
    assert (
        "Python execution successful"
        in (tmp_path / "data/artifacts/python_execution.log").read_text()
    )
