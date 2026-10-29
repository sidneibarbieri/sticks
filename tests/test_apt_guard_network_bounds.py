"""Check bounded package transport settings used by fresh VM provisioning."""

import subprocess
from pathlib import Path

import pytest

APT_GUARD = (
    Path(__file__).resolve().parents[1] / "lab" / "vagrant" / "shared" / "apt_guard.sh"
)


def test_apt_helpers_apply_transport_bounds() -> None:
    completed = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; wait_for_apt_ready() { :; }; '
                'apt-get() { printf "%s\\n" "$*"; }; '
                "apt_update_quiet; apt_install_quiet curl; apt_install_minimal openssh-server"
            ),
            "bash",
            str(APT_GUARD),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    commands = completed.stdout.splitlines()
    assert len(commands) == 3
    for command in commands:
        assert "Acquire::Retries=3" in command
        assert "Acquire::http::Timeout=30" in command
        assert "Acquire::https::Timeout=30" in command
        assert "DPkg::Lock::Timeout=300" in command
    assert commands[0].endswith("update -qq")
    assert commands[1].endswith("install -y -qq curl")
    assert commands[2].endswith("install -y -qq --no-install-recommends openssh-server")


def test_installed_base_packages_do_not_trigger_network_access() -> None:
    completed = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; '
                'dpkg-query() { printf "install ok installed"; }; '
                'apt_update_quiet() { printf "unexpected update\\n"; return 1; }; '
                'apt_install_minimal() { printf "unexpected install\\n"; return 1; }; '
                "apt_install_missing_minimal curl openssh-server"
            ),
            "bash",
            str(APT_GUARD),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert "skipping apt network access" in completed.stdout
    assert "unexpected" not in completed.stdout


def test_missing_base_package_is_the_only_install_target() -> None:
    completed = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; '
                "dpkg-query() { "
                '  if [[ "${!#}" == "wget" ]]; then return 1; fi; '
                '  printf "install ok installed"; '
                "}; "
                'apt_update_quiet() { printf "update\\n"; }; '
                'apt_install_minimal() { printf "install:%s\\n" "$*"; }; '
                "apt_install_missing_minimal curl wget openssh-server"
            ),
            "bash",
            str(APT_GUARD),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    assert completed.stdout.splitlines() == ["update", "install:wget"]


def test_failed_update_stops_missing_package_install_in_conditional_call() -> None:
    completed = subprocess.run(
        [
            "bash",
            "-c",
            (
                'source "$1"; '
                "dpkg-query() { return 1; }; "
                "apt_update_quiet() { return 42; }; "
                'apt_install_minimal() { printf "unexpected install\\n"; }; '
                'apt_install_missing_minimal wget || exit "$?"'
            ),
            "bash",
            str(APT_GUARD),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 42
    assert "unexpected" not in completed.stdout


@pytest.mark.parametrize(
    "command",
    [
        "apt_update_quiet",
        "apt_install_quiet wget",
        "apt_install_minimal wget",
    ],
)
def test_lock_timeout_stops_apt_command_in_conditional_call(command: str) -> None:
    completed = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; '
            "wait_for_apt_ready() { return 42; }; "
            'apt-get() { printf "unexpected apt\\n"; }; ' + command + ' || exit "$?"',
            "bash",
            str(APT_GUARD),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 42
    assert "unexpected" not in completed.stdout
