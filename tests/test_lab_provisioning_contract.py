from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
APT_GUARD = PROJECT_ROOT / "lab" / "vagrant" / "shared" / "apt_guard.sh"
BASE_SCRIPT = PROJECT_ROOT / "lab" / "vagrant" / "shared" / "base.sh"
ATTACKER_SCRIPT = PROJECT_ROOT / "lab" / "vagrant" / "shared" / "attacker.sh"
CALDERA_SCRIPT = PROJECT_ROOT / "lab" / "vagrant" / "shared" / "caldera.sh"
CALDERA_VAGRANTFILE = PROJECT_ROOT / "lab" / "vagrant" / "caldera" / "Vagrantfile"
CALDERA_RUNTIME_REQUIREMENTS = (
    PROJECT_ROOT / "lab" / "vagrant" / "shared" / "caldera-runtime-requirements.txt"
)
UP_LAB_SCRIPT = PROJECT_ROOT / "scripts" / "up_lab.sh"
DESTROY_LAB_SCRIPT = PROJECT_ROOT / "scripts" / "destroy_lab.sh"
APPLY_SUT_PROFILE = PROJECT_ROOT / "src" / "apply_sut_profile.py"
CAMPAIGN_RUNNER = PROJECT_ROOT / "src" / "runners" / "campaign_runner.py"
HEALTH_CHECK = PROJECT_ROOT / "lab" / "health_check.py"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_apt_guard_exposes_minimal_install_helper() -> None:
    text = _read(APT_GUARD)

    assert "apt_install_minimal()" in text
    assert "--no-install-recommends" in text


def test_base_script_avoids_role_specific_packages() -> None:
    text = _read(BASE_SCRIPT)

    assert "apt_install_missing_minimal \\" in text
    for package in ("git", "python3-pip", "python3-venv", "sshpass", "jq", "vim"):
        assert f"    {package} \\" not in text


def test_attacker_script_keeps_sshpass_but_not_pip() -> None:
    text = _read(ATTACKER_SCRIPT)

    assert "apt_install_missing_minimal \\" in text
    assert "\n    sshpass || {" in text
    assert "\n    python3-pip \\" not in text


def test_attacker_bootstrap_does_not_bake_a_private_key() -> None:
    text = _read(ATTACKER_SCRIPT)

    assert "ssh-keygen" not in text
    assert "id_rsa" not in text


def test_attacker_script_refreshes_extended_tool_indexes_explicitly() -> None:
    text = _read(ATTACKER_SCRIPT)
    extended = text.split('if [[ "$INSTALL_EXTENDED_TOOLS" == "1" ]]; then', 1)[1]

    assert extended.index("apt_update_quiet") < extended.index("apt_install_quiet")


def test_caldera_script_installs_required_runtime_and_fails_if_missing() -> None:
    text = _read(CALDERA_SCRIPT)

    assert "apt_install_minimal python3-pip git curl xz-utils golang-1.22-go" in text
    assert "git submodule update --init --recursive" in text
    assert "npm ci --no-audit --no-fund" in text
    assert "npm run build" in text
    assert 'RUNTIME_REQUIREMENTS_FILE="/tmp/caldera-runtime-requirements.txt"' in text
    assert 'test -f "$RUNTIME_REQUIREMENTS_FILE"' in text
    assert "wait_for_caldera_http" in text


def test_caldera_vagrantfile_provisions_runtime_requirements() -> None:
    text = _read(CALDERA_VAGRANTFILE)

    assert 'source: "../shared/caldera-runtime-requirements.txt"' in text
    assert 'destination: "/tmp/caldera-runtime-requirements.txt"' in text


def test_caldera_runtime_requirements_match_enabled_plugin_slice() -> None:
    text = _read(CALDERA_RUNTIME_REQUIREMENTS)
    dependency_lines = {
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }

    assert "aiohttp-apispec==3.0.0b2" in dependency_lines
    assert "networkx==2.8.5" in dependency_lines
    assert "numpy>=1.20" in dependency_lines
    assert "matplotlib>=3.5.2" in dependency_lines
    assert "donut-shellcode==1.0.2" not in dependency_lines
    assert "Sphinx==7.1.2" not in dependency_lines
    assert "reportlab==4.0.4" not in dependency_lines


def test_vm_backed_path_reads_versioned_sut_profiles() -> None:
    assert '"data" / "sut_profiles"' in _read(APPLY_SUT_PROFILE)
    assert '"data" / "sut_profiles"' in _read(UP_LAB_SCRIPT)
    assert 'Path("data/sut_profiles")' in _read(CAMPAIGN_RUNNER)


def test_health_check_and_destroy_lab_use_versioned_sut_profiles() -> None:
    assert '"data" / "sut_profiles"' in _read(DESTROY_LAB_SCRIPT)
    assert '"data" / "sut_profiles"' in _read(HEALTH_CHECK)


def test_health_check_runs_after_sut_profile_application() -> None:
    up_lab = _read(UP_LAB_SCRIPT)

    profile_application = up_lab.index('"$PYTHON_BIN" "$ROOT_DIR/apply_sut_profile.py"')
    health_check = up_lab.index('"$PYTHON_BIN" "$ROOT_DIR/lab/health_check.py"')

    assert profile_application < health_check


def test_up_lab_uses_resolved_python_for_host_side_preflight_steps() -> None:
    up_lab = _read(UP_LAB_SCRIPT)

    assert 'python3 "$ROOT_DIR/apply_sut_profile.py"' not in up_lab
    assert 'python3 "$ROOT_DIR/lab/health_check.py"' not in up_lab
    assert '"$PYTHON_BIN" "$ROOT_DIR/apply_sut_profile.py"' in up_lab
    assert '"$PYTHON_BIN" "$ROOT_DIR/lab/health_check.py"' in up_lab


def test_health_check_describes_post_profile_service_readiness() -> None:
    text = _read(HEALTH_CHECK)
    assert '_campaign_uses_technique(campaign_id, "T1190")' not in text
    assert "Check services after the declared SUT profile has been applied" in text


@pytest.mark.parametrize(
    "campaign_id",
    ['0.c0011"; raise RuntimeError("unsafe")', "../outside", "0.foo/bar", "0..foo"],
)
def test_up_lab_rejects_invalid_campaign_before_vagrant(campaign_id: str) -> None:
    environment = os.environ.copy()
    environment["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        ["bash", str(UP_LAB_SCRIPT), "--campaign", campaign_id],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode != 0
    assert "Invalid campaign ID" in result.stderr
    assert "Vagrant not found" not in result.stderr


def test_up_lab_accepts_versioned_campaign_id_before_dependency_check() -> None:
    environment = os.environ.copy()
    environment["PATH"] = "/usr/bin:/bin"
    result = subprocess.run(
        ["bash", str(UP_LAB_SCRIPT), "--campaign", "0.c0011"],
        capture_output=True,
        text=True,
        env=environment,
        check=False,
    )

    assert result.returncode != 0
    assert "Vagrant not found" in result.stderr
    assert "Invalid campaign ID" not in result.stderr


def test_qemu_preflight_rejects_ambiguous_socket_vmnet_daemons() -> None:
    text = _read(UP_LAB_SCRIPT)

    assert "require_single_socket_vmnet_daemon" in text
    assert "Expected exactly one socket_vmnet daemon" in text
    assert text.index("require_single_socket_vmnet_daemon") < text.index(
        'log_info "[ok] QEMU provider ready"'
    )
