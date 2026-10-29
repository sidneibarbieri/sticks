#!/usr/bin/env python3
"""Provider-aware transport helpers for executing commands inside lab VMs."""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
from pathlib import Path

from loaders.campaign_loader import load_sut_profile

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
LAB_VAGRANT_DIR = PROJECT_ROOT / "lab" / "vagrant"

HOSTNAME_VM_ALIAS = {
    "target": "target-linux-1",
    "target-base": "target-linux-1",
    "target-secondary": "target-linux-2",
    "target-1": "target-linux-1",
    "target-2": "target-linux-2",
    "target-ray": "target-linux-1",
}

CONTROL_PLANE_VMS = {"attacker", "caldera"}


def detect_vagrant_provider() -> str:
    """Resolve the active Vagrant provider for the current host or orchestration env."""
    if os.environ.get("STICKS_VAGRANT_PROVIDER"):
        return os.environ["STICKS_VAGRANT_PROVIDER"]
    if os.environ.get("VAGRANT_DEFAULT_PROVIDER"):
        return os.environ["VAGRANT_DEFAULT_PROVIDER"]
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return "qemu"
    return "libvirt"


def build_vagrant_env(provider: str | None = None) -> dict[str, str]:
    """Build a stable subprocess environment for Vagrant commands."""
    env = os.environ.copy()
    env["VAGRANT_DEFAULT_PROVIDER"] = provider or detect_vagrant_provider()
    return env


def normalize_vm_name(host_name: str) -> str:
    """Resolve profile aliases to a concrete Vagrant VM directory name."""
    vm_name = HOSTNAME_VM_ALIAS.get(host_name, host_name)
    if vm_name.startswith("target-") and not (LAB_VAGRANT_DIR / vm_name).exists():
        return "target-linux-1"
    return vm_name


def resolve_target_vm_name(sut_profile_id: str) -> str:
    """Select the first non-control-plane target declared by the SUT profile."""
    sut_profile = load_sut_profile(sut_profile_id)

    candidate_hosts = [
        host_name
        for host_name in sut_profile.hosts.keys()
        if normalize_vm_name(host_name) not in CONTROL_PLANE_VMS
    ]
    if not candidate_hosts:
        candidate_hosts = [
            vm_name
            for vm_name in sut_profile.required_vms
            if normalize_vm_name(vm_name) not in CONTROL_PLANE_VMS
        ]

    if not candidate_hosts:
        raise ValueError(f"No target VM declared in SUT profile: {sut_profile_id}")

    for host_name in candidate_hosts:
        vm_name = normalize_vm_name(host_name)
        vm_dir = LAB_VAGRANT_DIR / vm_name
        if vm_dir.exists():
            return vm_name

    raise FileNotFoundError(
        f"No Vagrant directory found for SUT targets in {sut_profile_id}: "
        f"{', '.join(candidate_hosts)}"
    )


def run_command_in_vm(
    vm_name: str,
    remote_cmd: str,
    timeout: int = 45,
    provider: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a shell command inside the requested VM via Vagrant."""
    vm_dir = LAB_VAGRANT_DIR / vm_name
    if not vm_dir.exists():
        raise FileNotFoundError(f"Vagrant directory not found for VM: {vm_dir}")

    return subprocess.run(
        ["vagrant", "ssh", "-c", remote_cmd],
        cwd=vm_dir,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=build_vagrant_env(provider),
    )


def probe_vm_identity(
    vm_name: str,
    nonce: str,
    *,
    timeout: int = 15,
    provider: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Read a challenge-bound identity from one declared laboratory VM.

    This is a read-only topology probe. It does not establish shell authority
    or imply that a campaign occurrence executed on the VM.
    """
    if not nonce or any(character.isspace() for character in nonce):
        raise ValueError("Topology probe nonce must be one non-empty token")
    command = (
        "printf '%s\\t%s\\t%s\\n' "
        f'{shlex.quote(nonce)} "$(hostname)" '
        '"$(cat /proc/sys/kernel/random/boot_id)"'
    )
    return run_command_in_vm(
        vm_name,
        command,
        timeout=timeout,
        provider=provider,
    )


def detect_lab_infrastructure(sut_profile_id: str) -> str:
    """Probe whether Vagrant-managed VMs are reachable for the given SUT profile.

    Returns the detected provider string (e.g. "qemu", "libvirt") when the
    target VM responds to a basic SSH probe, or "" when no lab infrastructure
    is available.
    """
    provider = detect_vagrant_provider()
    try:
        vm_name = resolve_target_vm_name(sut_profile_id)
        result = run_command_in_vm(
            vm_name=vm_name,
            remote_cmd="echo STICKS_PROBE_OK",
            timeout=10,
            provider=provider,
        )
        if result.returncode == 0 and "STICKS_PROBE_OK" in result.stdout:
            return provider
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return ""
    return ""


def run_bash_on_target_vm(
    sut_profile_id: str,
    bash_script: str,
    timeout: int = 45,
    provider: str | None = None,
    execution_user: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Execute a bash script inside the target VM selected by the SUT profile."""
    vm_name = resolve_target_vm_name(sut_profile_id)
    remote_cmd = f"bash -lc {shlex.quote(bash_script)}"
    if execution_user is not None:
        if (
            not execution_user
            or execution_user == "root"
            or execution_user.startswith("-")
        ):
            raise ValueError("A non-root target execution user is required")
        remote_cmd = f"sudo -n -H -u {shlex.quote(execution_user)} -- {remote_cmd}"
    return run_command_in_vm(
        vm_name=vm_name,
        remote_cmd=remote_cmd,
        timeout=timeout,
        provider=provider,
    )


def browser_discovery_binding(sut_profile_id: str) -> tuple[str, tuple[str, ...]]:
    """Bind controlled browser discovery to one declared target account and its fixtures."""
    profile = load_sut_profile(sut_profile_id)
    target_vm = resolve_target_vm_name(sut_profile_id)
    browser_files = []
    declared_users = set()
    for host_name, host in profile.hosts.items():
        if normalize_vm_name(host_name) != target_vm:
            continue
        declared_users.update(user.username for user in host.users)
        for staged_file in host.files:
            home = Path("/home") / staged_file.owner
            browser_roots = (
                home / ".mozilla",
                home / ".config/google-chrome",
                home / ".config/chromium",
            )
            if any(
                Path(staged_file.path).is_relative_to(root) for root in browser_roots
            ):
                browser_files.append(staged_file)
    owners = {staged_file.owner for staged_file in browser_files}
    if len(owners) != 1 or not owners <= declared_users or "root" in owners:
        raise ValueError(
            "Browser discovery requires fixtures owned by one declared non-root target user"
        )
    return owners.pop(), tuple(staged_file.path for staged_file in browser_files)
