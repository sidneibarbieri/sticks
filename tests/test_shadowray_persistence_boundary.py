from pathlib import Path
import subprocess

import pytest

from executors import shadowray_additional_executors as additional
from executors import shadowray_fixed_executors as fixed


@pytest.mark.parametrize("executor", [
    fixed.execute_t1546_004_shadowray_fixed,
    additional.execute_t1546_004_shadowray,
])
def test_legacy_entries_do_not_inspect_operator_home(executor, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)

    def reject_operator_home():
        raise AssertionError("Operator home must remain untouched")

    def controlled_target(**kwargs):
        assert kwargs["sut_profile_id"] == "0.shadowray"
        return subprocess.CompletedProcess([], 0, "[shell-startup] active", "")

    monkeypatch.setattr(Path, "home", reject_operator_home)
    monkeypatch.setattr(fixed, "run_bash_on_target_vm", controlled_target)
    success, stdout, stderr, artifacts = executor("0.shadowray", "0.shadowray")
    assert success
    assert "target VM" in stdout
    assert stderr == ""
    assert Path(artifacts[0]).is_relative_to(Path("data/artifacts"))


def test_vm_fixture_proves_isolated_shell_startup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    guest_fixture = tmp_path / "guest-fixture"

    def controlled_target(**kwargs):
        script = kwargs["bash_script"].replace(
            "/tmp/sticks-shadowray-persistence", str(guest_fixture)
        )
        assert "setpriv --no-new-privs bash" in script
        script = script.replace("setpriv --no-new-privs ", "")
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    monkeypatch.setattr(fixed, "run_bash_on_target_vm", controlled_target)
    success, stdout, _, artifacts = fixed.execute_t1546_004_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert success
    assert "[shell-startup] active" in stdout
    assert (guest_fixture / ".bashrc_sticks_backup").read_bytes() == (
        guest_fixture / ".bashrc_sticks_simulation"
    ).read_bytes()
    assert "[shell-startup] active" in Path(artifacts[0]).read_text()


@pytest.mark.parametrize("executor", [
    fixed.execute_t1546_004_shadowray_fixed,
    additional.execute_t1546_004_shadowray,
])
def test_transport_failure_does_not_fall_back_to_operator(executor, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "forbidden-operator-home")
    monkeypatch.setattr(fixed, "run_bash_on_target_vm", lambda **kwargs:
                        subprocess.CompletedProcess([], 7, "", "guest denied"))
    success, _, stderr, artifacts = executor("0.shadowray", "0.shadowray")
    assert not success
    assert stderr == "guest denied"
    assert Path(artifacts[0]).read_text().endswith("guest denied")


def test_unexpected_transport_error_remains_visible(monkeypatch):
    def denied(**kwargs):
        raise PermissionError("controlled transport failure")

    monkeypatch.setattr(fixed, "run_bash_on_target_vm", denied)
    monkeypatch.setattr(Path, "home", lambda: Path("/invalid-controlled-home"))
    with pytest.raises(PermissionError, match="controlled transport failure"):
        fixed.execute_t1546_004_shadowray_fixed("0.shadowray", "0.shadowray")


def test_zero_exit_without_startup_observation_is_not_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    monkeypatch.setattr(fixed, "run_bash_on_target_vm", lambda **kwargs:
                        subprocess.CompletedProcess([], 0, "files created", ""))
    success, _, stderr, artifacts = fixed.execute_t1546_004_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert not success
    assert "observation missing" in stderr
    assert Path(artifacts[0]).read_text() == "files created"


def test_missing_alias_fails_before_success_marker(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    guest_fixture = tmp_path / "guest-fixture"

    def controlled_target(**kwargs):
        script = kwargs["bash_script"].replace(
            "/tmp/sticks-shadowray-persistence", str(guest_fixture)
        ).replace("alias sticks-ping='echo", "alias wrong-alias='echo")
        assert "setpriv --no-new-privs bash" in script
        script = script.replace("setpriv --no-new-privs ", "")
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True)

    monkeypatch.setattr(fixed, "run_bash_on_target_vm", controlled_target)
    success, stdout, _, _ = fixed.execute_t1546_004_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert not success
    assert "[shell-startup] active" not in stdout
