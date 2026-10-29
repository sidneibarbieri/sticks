from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _lab_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "artifact"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    script = scripts / "destroy_lab.sh"
    shutil.copy2(PROJECT_ROOT / "scripts" / "destroy_lab.sh", script)
    shutil.copy2(PROJECT_ROOT / "scripts" / "python_env.sh", scripts / "python_env.sh")

    for vm_name in ("caldera", "attacker"):
        vm_dir = root / "lab" / "vagrant" / vm_name
        vm_dir.mkdir(parents=True)
        (vm_dir / "Vagrantfile").write_text("Vagrant.configure(2) {}\n", encoding="utf-8")

    state_dir = root / "data" / "state"
    state_dir.mkdir(parents=True)
    state_marker = state_dir / "other-run.json"
    state_marker.write_text("{}", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    vagrant = bin_dir / "vagrant"
    vagrant.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' \"$(basename \"$PWD\")\" >> \"$VM_CALLS\"\n"
        "exit \"${VM_EXIT_CODE:-0}\"\n",
        encoding="utf-8",
    )
    vagrant.chmod(0o755)
    return script, state_marker, bin_dir


def _run(script: Path, bin_dir: Path, calls_path: Path, campaign_id: str, *, vm_exit_code: int = 0):
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["VM_CALLS"] = str(calls_path)
    environment["VM_EXIT_CODE"] = str(vm_exit_code)
    environment["STICKS_PYTHON"] = sys.executable
    return subprocess.run(
        ["bash", str(script), "--campaign", campaign_id],
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )


def test_unknown_campaign_cannot_destroy_any_vm_or_other_run_state(tmp_path: Path) -> None:
    script, state_marker, bin_dir = _lab_fixture(tmp_path)
    calls_path = tmp_path / "vagrant-calls.txt"

    result = _run(script, bin_dir, calls_path, "0.unknown")

    assert result.returncode != 0
    assert not calls_path.exists()
    assert state_marker.exists()


def test_empty_campaign_cannot_expand_to_all_vms(tmp_path: Path) -> None:
    script, state_marker, bin_dir = _lab_fixture(tmp_path)
    calls_path = tmp_path / "vagrant-calls.txt"

    result = _run(script, bin_dir, calls_path, "")

    assert result.returncode != 0
    assert "Invalid campaign ID" in result.stderr
    assert not calls_path.exists()
    assert state_marker.exists()


def test_no_argument_cannot_destroy_all_vms(tmp_path: Path) -> None:
    script, state_marker, bin_dir = _lab_fixture(tmp_path)
    calls_path = tmp_path / "vagrant-calls.txt"
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["VM_CALLS"] = str(calls_path)
    environment["STICKS_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode != 0
    assert "--campaign ID or --all" in result.stderr
    assert not calls_path.exists()
    assert state_marker.exists()


def test_explicit_all_destroys_only_managed_vm_directories(tmp_path: Path) -> None:
    script, state_marker, bin_dir = _lab_fixture(tmp_path)
    unrelated_vm = script.parent.parent / "lab" / "vagrant" / "unrelated"
    unrelated_vm.mkdir(parents=True)
    (unrelated_vm / "Vagrantfile").write_text("Vagrant.configure(2) {}\n", encoding="utf-8")
    calls_path = tmp_path / "vagrant-calls.txt"
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_dir}:{environment['PATH']}"
    environment["VM_CALLS"] = str(calls_path)
    environment["STICKS_PYTHON"] = sys.executable

    result = subprocess.run(
        ["bash", str(script), "--all"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode == 0
    assert calls_path.read_text(encoding="utf-8").splitlines() == ["caldera", "attacker"]
    assert state_marker.exists()


def test_teardown_targets_only_declared_vms_and_keeps_other_run_state(tmp_path: Path) -> None:
    script, state_marker, bin_dir = _lab_fixture(tmp_path)
    profile_dir = script.parent.parent / "data" / "sut_profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "0.example.yml").write_text(
        "requirements:\n  required_vms: [caldera]\n", encoding="utf-8"
    )
    calls_path = tmp_path / "vagrant-calls.txt"

    result = _run(script, bin_dir, calls_path, "0.example")

    assert result.returncode == 0, result.stderr
    assert calls_path.read_text(encoding="utf-8").splitlines() == ["caldera"]
    assert state_marker.exists()


def test_vm_destroy_failure_is_reported(tmp_path: Path) -> None:
    script, _, bin_dir = _lab_fixture(tmp_path)
    profile_dir = script.parent.parent / "data" / "sut_profiles"
    profile_dir.mkdir(parents=True)
    (profile_dir / "0.example.yml").write_text(
        "requirements:\n  required_vms: [caldera]\n", encoding="utf-8"
    )

    result = _run(script, bin_dir, tmp_path / "vagrant-calls.txt", "0.example", vm_exit_code=4)

    assert result.returncode != 0
