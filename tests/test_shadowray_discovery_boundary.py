from pathlib import Path
import socket
import subprocess

import pytest

from executors import shadowray_fixed_executors as shadowray


@pytest.mark.parametrize("executor,marker", [
    (shadowray.execute_t1016_shadowray_fixed, "[network-target] target-linux-1"),
    (shadowray.execute_t1588_002_shadowray_fixed, "[toolkit-target] target-linux-1"),
])
def test_registered_discovery_uses_only_guest_transport(executor, marker, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)

    def reject_operator(*args, **kwargs):
        raise AssertionError("Operator observation is forbidden")

    def guest_transport(**kwargs):
        assert kwargs["sut_profile_id"] == "0.shadowray"
        assert "hostname" in kwargs["bash_script"]
        return subprocess.CompletedProcess([], 0, marker, "")

    monkeypatch.setattr(socket, "gethostname", reject_operator)
    monkeypatch.setattr(subprocess, "run", reject_operator)
    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", guest_transport)
    success, stdout, _, artifacts = executor("0.shadowray", "0.shadowray")
    assert success
    assert marker in stdout
    assert Path(artifacts[0]).is_relative_to(Path("data/artifacts"))


@pytest.mark.parametrize("executor", [
    shadowray.execute_t1016_shadowray_fixed,
    shadowray.execute_t1588_002_shadowray_fixed,
])
def test_no_target_observation_means_failure(executor, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", lambda **kwargs:
                        subprocess.CompletedProcess([], 0, "", ""))
    success, _, stderr, _ = executor("0.shadowray", "0.shadowray")
    assert not success
    assert "observation missing" in stderr


def test_toolkit_keeps_three_tools_and_optional_port_limit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    guest_fixture = tmp_path / "guest-toolkit"
    guest_proc = tmp_path / "guest-proc"
    guest_proc.mkdir()
    (guest_proc / "123").mkdir()

    def guest_transport(**kwargs):
        script = kwargs["bash_script"].replace(
            "/tmp/sticks-shadowray-toolkit", str(guest_fixture)
        ).replace("os.listdir('/proc')", f"os.listdir({str(guest_proc)!r})")
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", guest_transport)
    success, _, _, _ = shadowray.execute_t1588_002_shadowray_vm("0.shadowray", "0.shadowray")
    assert success
    assert {path.name for path in guest_fixture.iterdir()} == {
        "port_scanner.py", "service_enum.sh", "sys_profiler.py",
    }
    result = subprocess.run(
        ["python3", str(guest_fixture / "port_scanner.py"), "127.0.0.1", "1"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert len(result.stdout.splitlines()) == 1


def test_registered_python_step_uses_guest_transport(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)

    def reject_controller_process(*args, **kwargs):
        raise AssertionError("Controller-side Python execution is forbidden")

    def guest_transport(**kwargs):
        assert kwargs["sut_profile_id"] == "0.shadowray"
        assert "python3" in kwargs["bash_script"]
        return subprocess.CompletedProcess([], 0, "guest-python-completed", "")

    monkeypatch.setattr(subprocess, "run", reject_controller_process)
    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", guest_transport)

    success, output, error, artifacts = shadowray.execute_t1059_006_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )

    assert success
    assert "guest-python-completed" in output
    assert not error
    assert Path(artifacts[0]).is_file()


def test_python_step_preserves_guest_process_failure(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(
        shadowray,
        "run_bash_on_target_vm",
        lambda **kwargs: subprocess.CompletedProcess([], 23, "guest-output", "guest-error"),
    )

    success, output, error, artifacts = shadowray.execute_t1059_006_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )

    assert not success
    assert output == "guest-output"
    assert error == "guest-error"
    assert Path(artifacts[0]).is_file()
