import subprocess
import os
import pwd
import shlex
from pathlib import Path
from types import SimpleNamespace

from executors import executor_registry
from runners.campaign_runner import UnifiedCampaignRunner


def test_browser_discovery_uses_target_transport_without_host_home(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()

    def reject_host_home():
        raise AssertionError("Host home must not be inspected")

    def run_on_target(sut_profile_id, bash_script, timeout=45, execution_user=None):
        assert sut_profile_id == "0.outer_space"
        assert "/home/" in bash_script
        assert execution_user == "clouduser"
        return subprocess.CompletedProcess([], 0, "[identity] clouduser\n/home/clouduser/.mozilla/profiles.ini\n", ""), ""

    monkeypatch.setattr(Path, "home", reject_host_home)
    monkeypatch.setattr(executor_registry, "browser_discovery_binding", lambda _: ("clouduser", ("/home/clouduser/.mozilla/profiles.ini",)))
    monkeypatch.setattr(executor_registry, "_try_run_on_target_vm", run_on_target)

    success, stdout, stderr, artifacts = executor_registry.execute_t1217_real(
        "0.outer_space", "0.outer_space"
    )

    assert success is True
    assert "inside target VM" in stdout
    assert stderr == ""
    assert "/home/clouduser/" in Path(artifacts[0]).read_text()


def test_browser_discovery_rejects_transport_failure_without_local_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    monkeypatch.setattr(executor_registry, "browser_discovery_binding", lambda _: ("clouduser", ("/home/clouduser/.mozilla/profiles.ini",)))
    monkeypatch.setattr(executor_registry, "_try_run_on_target_vm", lambda *args, **kwargs: (None, "SSH refused"))

    success, stdout, stderr, artifacts = executor_registry.execute_t1217_real(
        "0.outer_space", "0.outer_space"
    )

    assert success is False
    assert "SSH refused" in stderr
    assert artifacts == []
    assert not (tmp_path / "data/artifacts/0.outer_space_browser_discovery.txt").exists()


def test_browser_discovery_rejects_empty_observation(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(executor_registry, "browser_discovery_binding", lambda _: ("clouduser", ("/home/clouduser/.mozilla/profiles.ini",)))
    monkeypatch.setattr(executor_registry, "_try_run_on_target_vm", lambda *args, **kwargs: (subprocess.CompletedProcess([], 0, "[identity] clouduser\nmissing\n", ""), ""))
    success, _, stderr, artifacts = executor_registry.execute_t1217_real("fixture", "fixture")
    assert not success
    assert "does not match binding" in stderr
    assert Path(artifacts[0]).is_file()


def test_browser_discovery_does_not_require_the_transport_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    username = pwd.getpwuid(os.getuid()).pw_name
    user_home = tmp_path / "guest-home"
    fixture = user_home / ".mozilla/profiles.ini"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("controlled fixture")
    transport_directory = tmp_path / "transport-home"
    transport_directory.mkdir()
    command_directory = tmp_path / "guest-bin"
    command_directory.mkdir()
    find_guard = command_directory / "find"
    find_guard.write_text(
        "#!/bin/bash\n"
        f"test \"$PWD\" = {shlex.quote(str(user_home))} || exit 77\n"
        'exec /usr/bin/find "$@"\n'
    )
    find_guard.chmod(0o755)
    monkeypatch.setattr(executor_registry, "browser_discovery_binding", lambda _: (username, (str(fixture),)))

    def run_in_guest_filesystem(sut_profile_id, bash_script, **kwargs):
        script = bash_script.replace(f"/home/{username}", str(user_home))
        environment = dict(os.environ, PATH=f"{command_directory}:{os.environ['PATH']}")
        result = subprocess.run(["bash", "-c", script], cwd=transport_directory, env=environment, capture_output=True, text=True)
        return (result, "") if result.returncode == 0 else (None, result.stderr)

    monkeypatch.setattr(executor_registry, "_try_run_on_target_vm", run_in_guest_filesystem)
    success, _, stderr, artifacts = executor_registry.execute_t1217_real("fixture", "fixture")
    assert success, stderr
    assert str(fixture) in Path(artifacts[0]).read_text()


def test_real_controlled_label_does_not_prove_execution_on_target():
    runner = UnifiedCampaignRunner.__new__(UnifiedCampaignRunner)
    runner._infrastructure_provider = "qemu"
    runner.sut = SimpleNamespace(campaign_id="0.outer_space")
    evidence = SimpleNamespace(
        execution_mode="real_controlled",
        stdout="Executed inside target VM",
        artifacts_created=["target-vm:/tmp/unverified.txt"],
    )

    assert runner._infer_host(evidence) == ""
