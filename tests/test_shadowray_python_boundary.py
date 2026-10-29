"""Python discovery must use the selected target user's home, not SSH cwd."""

import os
import subprocess

from executors import shadowray_fixed_executors as shadowray


def test_python_lists_target_home_instead_of_inherited_ssh_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)
    home = tmp_path / "target-home"
    home.mkdir()
    (home / "target-owned-fixture").write_text("declared laboratory fixture\n")
    inherited = tmp_path / "inherited-ssh-directory"
    inherited.mkdir()
    (inherited / "unrelated-ssh-account-file").write_text("not target home\n")

    def transport(**kwargs):
        assert kwargs["execution_user"] == "rayuser"
        return subprocess.run(
            ["bash", "-c", kwargs["bash_script"]],
            cwd=inherited,
            env=os.environ | {"HOME": str(home)},
            capture_output=True,
            text=True,
        )

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", transport)
    success, output, error, _ = shadowray.execute_t1059_006_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert success, error
    assert "target-owned-fixture" in output
    assert "unrelated-ssh-account-file" not in output


def test_missing_target_home_does_not_fall_back_to_ssh_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/artifacts").mkdir(parents=True)

    def transport(**kwargs):
        return subprocess.run(
            ["bash", "-c", kwargs["bash_script"]],
            cwd=tmp_path,
            env=os.environ | {"HOME": str(tmp_path / "missing-home")},
            capture_output=True,
            text=True,
        )

    monkeypatch.setattr(shadowray, "run_bash_on_target_vm", transport)
    success, output, error, _ = shadowray.execute_t1059_006_shadowray_vm(
        "0.shadowray", "0.shadowray"
    )
    assert not success
    assert "Python version:" not in output
    assert "missing-home" in error
