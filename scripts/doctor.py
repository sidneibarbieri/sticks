#!/usr/bin/env python3
"""Read-only preflight for each reviewer path, with the exact fix for every failure.

The laboratory checks call the same functions the laboratory runner calls, so
this report and the runner cannot disagree about host readiness. Nothing here
starts a VM, a container, a daemon, or a network, and nothing is deleted.
"""
from __future__ import annotations

import argparse
import importlib
import ipaddress
import json
import platform
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


@dataclass
class Check:
    name: str
    status: str  # OK, WARN, FAIL
    detail: str
    fix: str = ""


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def check_python() -> list[Check]:
    version = sys.version.split()[0]
    checks = [Check("python", "OK", version)]
    if sys.version_info < (3, 11):
        checks[0] = Check("python", "FAIL", version, "Install Python 3.11 or newer.")
    missing = []
    for module in ("pydantic", "requests", "yaml"):
        try:
            importlib.import_module(module)
        except ImportError:
            missing.append(module)
    if missing:
        checks.append(Check("python packages", "FAIL", "missing: " + ", ".join(missing),
                            "bash artifact/setup.sh"))
    else:
        checks.append(Check("python packages", "OK", "pydantic, requests, yaml importable"))
    return checks


def check_host() -> list[Check]:
    system, machine = platform.system(), platform.machine().lower()
    if system == "Darwin" and machine in ("arm64", "aarch64"):
        return [Check("host", "OK", "Apple-silicon macOS, the validated laboratory host")]
    return [Check("host", "WARN", f"{system} {machine}: not the validated laboratory host",
                  "The guests are ARM64 (perk/ubuntu-2204-arm64). They were validated on "
                  "Apple-silicon macOS; elsewhere they may run under full emulation or not at all.")]


def check_lab_tools() -> list[Check]:
    checks = []
    if shutil.which("vagrant"):
        if "vagrant-qemu" in run(["vagrant", "plugin", "list"]).stdout:
            checks.append(Check("vagrant-qemu", "OK", "plugin installed"))
        else:
            checks.append(Check("vagrant-qemu", "FAIL", "plugin missing",
                                "vagrant plugin install vagrant-qemu --plugin-version 0.6.3"))
    else:
        checks.append(Check("vagrant", "FAIL", "not on PATH",
                            "Install Vagrant: https://developer.hashicorp.com/vagrant/install"))
    qemu = shutil.which("qemu-system-aarch64")
    checks.append(Check("qemu", "OK", qemu) if qemu else
                  Check("qemu", "FAIL", "qemu-system-aarch64 not on PATH", "brew install qemu"))
    return checks


def socket_vmnet_daemons(binary: str) -> list[tuple[str, float, str]]:
    daemons = []
    for row in run(["ps", "-axo", "pid=,lstart=,command="]).stdout.splitlines():
        fields = row.split()
        if len(fields) < 7 or not " ".join(fields[6:]).startswith(f"{binary} "):
            continue
        started = " ".join(fields[1:6])
        try:
            stamp = datetime.strptime(started, "%a %b %d %H:%M:%S %Y").timestamp()
        except ValueError:
            stamp = 0.0
        daemons.append((fields[0], stamp, started))
    return daemons


def check_qemu_network(lab) -> list[Check]:
    try:
        lab.require_qemu_network("qemu")
        return [Check("socket_vmnet", "OK", "one daemon answering on the default socket")]
    except FileNotFoundError as error:
        return [Check("socket_vmnet", "FAIL", str(error),
                      "brew install socket_vmnet && sudo brew services start socket_vmnet")]
    except ConnectionError as error:
        return [Check("socket_vmnet", "FAIL", str(error), "sudo brew services restart socket_vmnet")]
    except RuntimeError as error:
        daemons = socket_vmnet_daemons(lab.SOCKET_VMNET_BINARY)
        socket_mtime = lab.DEFAULT_SOCKET_VMNET.stat().st_mtime
        # The daemon that created the current socket file started last before its mtime.
        candidates = [daemon for daemon in daemons if daemon[1] <= socket_mtime + 2]
        owner = max(candidates, key=lambda daemon: daemon[1])[0] if candidates else None
        stale = [pid for pid, _, _ in daemons if pid != owner]
        listing = "; ".join(f"pid {pid} started {started}" for pid, _, started in daemons)
        if owner and stale:
            fix = (f"sudo kill {' '.join(stale)}   "
                   f"# pid {owner} owns the socket file; stop VMs first if any are running")
        else:
            fix = "sudo brew services restart socket_vmnet"
        return [Check("socket_vmnet", "FAIL", f"{error} [{listing}]", fix)]


def check_running_vms() -> list[Check]:
    guests = run(["pgrep", "-fl", "qemu-system"]).stdout.strip()
    if guests:
        # Two laboratories would share the fixed private-network addresses; fail closed.
        return [Check("running QEMU guest", "FAIL", guests.splitlines()[0][:120],
                      "Let the other run finish (or complete it with its complete_*_run.py); "
                      "'vagrant global-status' lists its machines.")]
    return [Check("running QEMU guest", "OK", "none")]


def check_capacity(lab, run_root: Path) -> list[Check]:
    try:
        lab.require_vm_host_capacity(run_root)
    except OSError as error:
        return [Check("disk space", "FAIL", str(error), "Free at least 25 GiB on the run-root volume.")]
    probe = run_root
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free / 1024**3
    return [Check("disk space", "OK", f"{free:.0f} GiB free (floor 25 GiB)")]


def check_caldera_sources(lab) -> list[Check]:
    try:
        lab.require_safe_caldera_sources(PROJECT_ROOT)
    except Exception as error:  # the policy raises several precise exception types
        return [Check("Caldera sources", "FAIL", str(error),
                      "Restore the runner sources from the release; never hard-code credentials.")]
    return [Check("Caldera sources", "OK", "no credential literal in runner sources")]


def compose_subnets(compose_files: list[Path]) -> list[tuple[str, ipaddress.IPv4Network]]:
    wanted = []
    for compose in compose_files:
        for line in compose.read_text(encoding="utf-8").splitlines():
            stripped = line.split("#", 1)[0].strip().removeprefix("- ")
            if stripped.startswith("subnet:"):
                wanted.append((compose.name, ipaddress.ip_network(stripped.split(":", 1)[1].strip())))
    return wanted


def check_docker(compose_files: list[Path]) -> list[Check]:
    if not shutil.which("docker"):
        return [Check("docker", "FAIL", "not on PATH", "Install Docker Desktop or colima.")]
    info = run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if info.returncode != 0:
        return [Check("docker", "FAIL", "daemon unreachable", "colima start")]
    checks = [Check("docker", "OK", f"server {info.stdout.strip()}")]
    wanted = compose_subnets(compose_files)
    if not wanted:
        checks.append(Check("docker subnets", "OK", "compose files declare no fixed subnet"))
        return checks
    project = {compose.parent.name for compose in compose_files}
    existing = []
    for name in run(["docker", "network", "ls", "--format", "{{.Name}}"]).stdout.split():
        for net in json.loads(run(["docker", "network", "inspect", name]).stdout or "[]"):
            labels = net.get("Labels") or {}
            if labels.get("com.docker.compose.project") in project:
                continue  # leftovers of this very project are replaced by compose itself
            for config in net.get("IPAM", {}).get("Config") or []:
                if config.get("Subnet"):
                    existing.append((name, ipaddress.ip_network(config["Subnet"]),
                                     len(net.get("Containers") or {})))
    clashes = [(compose_name, subnet, name, net_subnet, attached)
               for compose_name, subnet in wanted
               for name, net_subnet, attached in existing
               if subnet.overlaps(net_subnet)]
    if not clashes:
        checks.append(Check("docker subnets", "OK", f"{len(wanted)} fixed subnet(s) free"))
    for compose_name, subnet, name, net_subnet, attached in clashes:
        if attached == 0:
            fix = (f"docker network inspect {name} > {name}.json && docker network rm {name}   "
                   f"# no container attached; its compose project recreates it on next 'up'")
        else:
            fix = f"Stop the project that owns '{name}' ({attached} container(s) attached) first."
        checks.append(Check("docker subnets", "FAIL",
                            f"{compose_name} needs {subnet}; overlaps '{name}' {net_subnet}", fix))
    return checks


def collect(path: str, run_root: Path, compose_files: list[Path]) -> list[Check]:
    checks = check_python()
    if path in ("lab", "all"):
        try:
            lab = importlib.import_module("run_isolated_lab_campaign")
        except Exception as error:
            return checks + [Check("lab runner import", "FAIL", str(error), "bash artifact/setup.sh")]
        checks += check_host()
        checks += check_lab_tools()
        checks += check_qemu_network(lab)
        checks += check_running_vms()
        checks += check_capacity(lab, run_root)
        checks += check_caldera_sources(lab)
    if path in ("docker", "all"):
        checks += check_docker(compose_files)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", choices=("review", "lab", "docker", "all"), default="all",
                        help="review: offline gate; lab: QEMU laboratory; docker: compose-based runs")
    parser.add_argument("--run-root", type=Path, default=Path.home(),
                        help="Where a laboratory run will be written (used by the disk check).")
    parser.add_argument("--compose", type=Path, action="append", default=[],
                        help="Compose file whose fixed subnets must be free (repeatable).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable results.")
    args = parser.parse_args()
    compose_files = args.compose or sorted((PROJECT_ROOT / "measurement" / "sut").glob("docker-compose*.yml"))
    checks = collect(args.path, args.run_root, compose_files)
    failed = sum(check.status == "FAIL" for check in checks)
    if args.json:
        print(json.dumps([asdict(check) for check in checks], indent=2))
    else:
        width = max(len(check.name) for check in checks)
        for check in checks:
            print(f"[{check.status:<4}] {check.name:<{width}}  {check.detail}")
            if check.fix and check.status != "OK":
                print(f"{'':7}{'':<{width}}  fix: {check.fix}")
        print(f"\n{len(checks)} checks, {failed} failing" + ("" if failed else ": ready"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
