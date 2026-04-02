#!/usr/bin/env python3
"""
apply_sut_profile.py - Apply SUT (System Under Test) profile to Vagrant VMs
Configures deliberate weaknesses, vulnerabilities, services, and preconditions.
"""

import argparse
import base64
import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

import yaml
from executors.realistic_data_generator import generate_realistic_files

HOSTNAME_VM_ALIAS = {
    "target-base": "target-linux-1",
    "target-secondary": "target-linux-2",
    "target-1": "target-linux-1",
    "target-2": "target-linux-2",
    "target-ray": "target-linux-1",
}

VM_IPS = {
    "caldera": "192.168.56.10",
    "attacker": "192.168.56.20",
    "target-linux-1": "192.168.56.30",
    "target-linux-2": "192.168.56.31",
    "target-1": "192.168.56.30",
    "target-2": "192.168.56.31",
}


def log_info(msg: str) -> None:
    print(f"[SUT-APPLY] {msg}")


def log_warn(msg: str) -> None:
    print(f"[SUT-APPLY] WARN: {msg}")


def log_error(msg: str) -> None:
    print(f"[SUT-APPLY] ERROR: {msg}", file=sys.stderr)


def load_sut_profile(campaign_id: str, base_dir: Path) -> dict:
    """Load SUT profile YAML for the given campaign."""
    profile_path = base_dir / "data" / "sut_profiles" / f"{campaign_id}.yml"
    if not profile_path.exists():
        raise FileNotFoundError(f"SUT profile not found: {profile_path}")

    with open(profile_path) as f:
        return yaml.safe_load(f)


def execute_ssh_command(
    host_ip: str,
    command: str,
    user: str = "vagrant",
    password: str = "vagrant",
    provider: str = "libvirt",
    vm_name: Optional[str] = None,
    base_dir: Optional[Path] = None,
) -> tuple:
    """Execute command on host via provider-aware transport."""
    if provider == "qemu" and vm_name and base_dir:
        vm_dir = base_dir / "lab" / "vagrant" / vm_name
        if vm_dir.exists():
            try:
                env = os.environ.copy()
                env["VAGRANT_DEFAULT_PROVIDER"] = provider
                result = subprocess.run(
                    ["vagrant", "ssh", "-c", command],
                    cwd=str(vm_dir),
                    capture_output=True,
                    text=True,
                    timeout=45,
                    env=env,
                )
                return result.returncode == 0, result.stdout, result.stderr
            except subprocess.TimeoutExpired:
                return False, "", "Command timed out"
            except Exception as e:
                return False, "", str(e)

    # Fallback: SSH via private IP using sshpass.
    ssh_cmd = [
        "sshpass",
        "-p",
        password,
        "ssh",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        f"{user}@{host_ip}",
        command,
    ]

    try:
        result = subprocess.run(ssh_cmd, capture_output=True, text=True, timeout=30)
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def apply_weak_credentials(
    host_ip: str, weakness: dict, provider: str, vm_name: str, base_dir: Path
) -> bool:
    """Apply weak credential weakness to target host."""
    username = weakness.get("username", "victim")
    password = weakness.get("password", "victim123")

    log_info(f"Creating user {username} with weak password on {host_ip}")

    # Create user
    success, stdout, stderr = execute_ssh_command(
        host_ip,
        f"sudo useradd -m -s /bin/bash {username} 2>/dev/null || true && "
        f"echo '{username}:{password}' | sudo chpasswd",
        provider=provider,
        vm_name=vm_name,
        base_dir=base_dir,
    )

    if success:
        log_info(f"✓ Weak credentials applied: {username}:{password}")
        return True
    else:
        log_error(f"Failed to apply weak credentials: {stderr}")
        return False


def apply_vulnerable_service(
    host_ip: str, service: dict, provider: str, vm_name: str, base_dir: Path
) -> bool:
    """Apply vulnerable service configuration."""
    name = service.get("name", "unknown")
    _config = service.get("configuration", {})  # Reserved for future use

    log_info(f"Configuring vulnerable service: {name} on {host_ip}")

    # Configure Apache (generic + vulnerable profile fallback)
    if name in {"apache-vulnerable", "apache2", "apache"}:
        commands = [
            "sudo apt-get update -qq",
            "sudo apt-get install -y -qq apache2=2.4.49-4ubuntu1 2>/dev/null || sudo apt-get install -y -qq apache2",
            "sudo sed -i 's/Options FollowSymLinks/Options FollowSymLinks Indexes/' /etc/apache2/apache2.conf 2>/dev/null || true",
            "sudo systemctl enable apache2 || true",
            "sudo systemctl restart apache2 || true",
        ]

        for cmd in commands:
            success, _, stderr = execute_ssh_command(
                host_ip,
                cmd,
                provider=provider,
                vm_name=vm_name,
                base_dir=base_dir,
            )
            if not success and "already" not in stderr.lower():
                log_warn(f"Command may have failed: {stderr}")

        log_info("✓ Vulnerable Apache configured")
        return True

    if name == "ray-dashboard":
        dashboard_source = """from http.server import BaseHTTPRequestHandler, HTTPServer
import json


class Handler(BaseHTTPRequestHandler):
    def _reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        return

    def do_GET(self):
        if self.path in {"/", "/api/version"}:
            self._reply(200, {"version": "2.9.0", "service": "ray-dashboard"})
            return
        if self.path == "/api/jobs/":
            self._reply(200, {"jobs": [], "auth": "disabled"})
            return
        self._reply(404, {"detail": "not found"})


HTTPServer(("0.0.0.0", 8265), Handler).serve_forever()
"""
        encoded_dashboard = base64.b64encode(dashboard_source.encode("utf-8")).decode(
            "ascii"
        )
        commands = [
            "sudo mkdir -p /opt/sticks-shadowray",
            (
                f"echo '{encoded_dashboard}' | base64 -d | "
                "sudo tee /opt/sticks-shadowray/ray_dashboard.py >/dev/null"
            ),
            "sudo pkill -f /opt/sticks-shadowray/ray_dashboard.py 2>/dev/null || true",
            "sudo bash -lc 'nohup python3 /opt/sticks-shadowray/ray_dashboard.py >/var/log/sticks-ray-dashboard.log 2>&1 &'",
            "sleep 2 && curl -fsS http://127.0.0.1:8265/api/version >/tmp/sticks-ray-dashboard-version.json",
        ]

        for cmd in commands:
            success, _, stderr = execute_ssh_command(
                host_ip,
                cmd,
                provider=provider,
                vm_name=vm_name,
                base_dir=base_dir,
            )
            if "pkill -f /opt/sticks-shadowray/ray_dashboard.py" in cmd:
                continue
            if not success:
                log_error(f"Failed to configure Ray dashboard: {stderr}")
                return False

        log_info("✓ Ray dashboard configured")
        return True

    return True


def apply_network_topology(network_config: dict) -> bool:
    """Apply network configuration (already done by Vagrant, verify only)."""
    log_info("Verifying network topology...")

    for host in network_config.get("hosts", []):
        hostname = host.get("hostname", "unknown")
        ip = host.get("ip", "unknown")
        log_info(f"  {hostname}: {ip}")

    return True


def apply_sut_to_host(
    host_config: dict, profile: dict, base_dir: Path, provider: str
) -> dict:
    """Apply SUT profile configuration to a specific host."""
    hostname = host_config.get("hostname", "unknown")
    ip = host_config.get("ip", "unknown")
    role = host_config.get("role", "unknown")
    vm_name = host_config.get("vm_name", hostname)
    host_profile = profile.get("sut_configuration", {}).get(hostname, {})

    log_info(f"Applying SUT to {hostname} ({ip}) - role: {role}")

    results = {
        "hostname": hostname,
        "ip": ip,
        "role": role,
        "weaknesses_applied": [],
        "services_configured": [],
        "errors": [],
    }

    # Apply deliberate weaknesses
    weaknesses = []
    for w in profile.get("deliberate_weaknesses", []):
        weaknesses.append(w)
    for w in host_profile.get("deliberate_weaknesses", []):
        w_copy = dict(w)
        w_copy.setdefault("target", hostname)
        weaknesses.append(w_copy)

    users = host_profile.get("users", [])
    provisioned_usernames = set()
    for user_cfg in users:
        username = user_cfg.get("username")
        password = user_cfg.get("password")
        if username and password:
            user_weakness = {"username": username, "password": password}
            if apply_weak_credentials(ip, user_weakness, provider, vm_name, base_dir):
                results["weaknesses_applied"].append(f"user:{username}")
                provisioned_usernames.add(username)
            else:
                results["errors"].append(f"Failed to provision user {username}")

    for weakness in weaknesses:
        if weakness.get("target") == hostname or weakness.get("target") == "all":
            wtype = weakness.get("type", "unknown")

            if wtype in {"weak_credentials", "weak_ssh_password"}:
                weak_user = weakness.get("username")
                if weak_user and weak_user in provisioned_usernames:
                    continue
                if apply_weak_credentials(ip, weakness, provider, vm_name, base_dir):
                    results["weaknesses_applied"].append(wtype)
                else:
                    results["errors"].append(f"Failed to apply {wtype}")

            elif wtype == "writable_directory":
                path = weakness.get("path", "/tmp/vulnerable")
                success, _, _ = execute_ssh_command(
                    ip,
                    f"sudo mkdir -p {path} && sudo chmod 777 {path}",
                    provider=provider,
                    vm_name=vm_name,
                    base_dir=base_dir,
                )
                if success:
                    results["weaknesses_applied"].append(f"writable_dir:{path}")
                else:
                    results["errors"].append(f"Failed to create writable dir: {path}")

            elif wtype == "suid_binary":
                binary = weakness.get("binary", "/bin/bash")
                success, _, _ = execute_ssh_command(
                    ip,
                    f"sudo chmod u+s {binary}",
                    provider=provider,
                    vm_name=vm_name,
                    base_dir=base_dir,
                )
                if success:
                    results["weaknesses_applied"].append(f"suid:{binary}")
                else:
                    results["errors"].append(f"Failed to set SUID on {binary}")

    # Apply services
    services = []
    for s in profile.get("services", []):
        services.append(s)
    for s in host_profile.get("services", []):
        s_copy = dict(s)
        s_copy["host"] = hostname
        services.append(s_copy)

    for service in services:
        if service.get("host") == hostname:
            if apply_vulnerable_service(ip, service, provider, vm_name, base_dir):
                results["services_configured"].append(service.get("name"))

    return results


def main():
    parser = argparse.ArgumentParser(
        description="Apply SUT profile to lab infrastructure"
    )
    parser.add_argument("--campaign", required=True, help="Campaign ID (e.g., 0.c0011)")
    parser.add_argument("--base-dir", default=".", help="Base directory of the project")
    parser.add_argument(
        "--provider",
        default="",
        help="Vagrant provider (qemu|libvirt|virtualbox)",
    )

    args = parser.parse_args()

    base_dir = Path(args.base_dir).resolve()
    provider = args.provider
    if not provider:
        provider = (
            "qemu"
            if platform.system() == "Darwin" and platform.machine() == "arm64"
            else "libvirt"
        )

    log_info(f"Loading SUT profile for campaign: {args.campaign}")

    try:
        profile = load_sut_profile(args.campaign, base_dir)
    except FileNotFoundError as e:
        log_error(str(e))
        sys.exit(1)

    log_info(f"Campaign: {profile.get('campaign_id', 'unknown')}")
    log_info(f"Description: {profile.get('description', 'N/A')}")

    # Apply network topology
    network_config = profile.get("network", {})
    apply_network_topology(network_config)

    # Apply SUT to each host (supports both `network.hosts` and `sut_configuration`)
    hosts = network_config.get("hosts", [])
    if not hosts:
        sut_cfg = profile.get("sut_configuration", {})
        for host_name in sut_cfg.keys():
            vm_name: str = HOSTNAME_VM_ALIAS.get(host_name) or host_name
            hosts.append(
                {
                    "hostname": host_name,
                    "vm_name": vm_name,
                    "ip": VM_IPS.get(vm_name, "unknown"),
                    "role": "target" if host_name.startswith("target") else "service",
                }
            )
    if not hosts:
        log_error("No hosts defined in SUT profile")
        sys.exit(1)

    all_results = []
    for host in hosts:
        result = apply_sut_to_host(host, profile, base_dir, provider)
        all_results.append(result)

    # Generate realistic data for target hosts
    log_info("Generating realistic data for exfiltration simulation...")
    for host in hosts:
        if host.get("role") == "target" or host.get("hostname").startswith("target"):
            target_ip = host.get("ip")
            if target_ip != "unknown":
                # Create realistic data directory on target
                data_dir = "/home/vagrant/realistic_corporate_data"
                success, _, _ = execute_ssh_command(
                    target_ip,
                    f"mkdir -p {data_dir}",
                    provider=provider,
                    vm_name=host.get("vm_name"),
                    base_dir=base_dir,
                )
                if success:
                    log_info(f"Created realistic data directory on {host['hostname']}")
                    # Generate realistic files locally for reference
                    local_data_dir = (
                        base_dir / "release" / "realistic_data" / args.campaign
                    )
                    generate_realistic_files(local_data_dir, args.campaign)
                    log_info(f"Generated realistic data reference in {local_data_dir}")
                else:
                    log_error(f"Failed to create data directory on {host['hostname']}")

    # Generate report
    report = {
        "campaign": args.campaign,
        "profile_version": profile.get("version", "unknown"),
        "hosts_configured": len(all_results),
        "results": all_results,
    }

    # Save report
    report_dir = base_dir / "release" / "sut_reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / f"{args.campaign}_sut_report.json"

    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)

    log_info("✓ SUT profile applied successfully")
    log_info(f"  Hosts configured: {len(all_results)}")
    log_info(f"  Report saved to: {report_path}")

    # Summary
    total_weaknesses = sum(len(r["weaknesses_applied"]) for r in all_results)
    total_services = sum(len(r["services_configured"]) for r in all_results)
    total_errors = sum(len(r["errors"]) for r in all_results)

    log_info(f"  Weaknesses applied: {total_weaknesses}")
    log_info(f"  Services configured: {total_services}")
    if total_errors > 0:
        log_warn(f"  Errors: {total_errors}")

    return 0 if total_errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
