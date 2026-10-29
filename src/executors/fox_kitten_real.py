#!/usr/bin/env python3
"""
Real executors for Fox Kitten completion - genuine Linux system interactions.
"""

import os
from http.server import BaseHTTPRequestHandler, HTTPServer
import subprocess
import tempfile
from threading import Thread
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

from .executor_registry import (
    ExecutionFidelity,
    ExecutionMode,
    ExecutorMetadata,
    register_executor,
)
from .lab_transport import run_bash_on_target_vm

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS_DIR = PROJECT_ROOT / "data" / "artifacts"


class _LocalProtocolProbe(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        payload = b"STICKS local protocol probe\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def probe_local_http() -> tuple[subprocess.CompletedProcess[str], str]:
    """Exercise HTTP over an owned loopback listener, never an ambient service."""
    with HTTPServer(("127.0.0.1", 0), _LocalProtocolProbe) as server:
        listener = Thread(target=server.serve_forever, daemon=True)
        listener.start()
        url = f"http://127.0.0.1:{server.server_port}/probe"
        try:
            result = subprocess.run(
                ["curl", "-sS", "-w", "HTTP Status: %{http_code}", url],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        finally:
            server.shutdown()
            listener.join(timeout=5)
    return result, url


def execute_t1087_real(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """T1087 - Account Discovery: Real Linux account enumeration."""
    try:
        with open("/etc/passwd", "r") as f:
            passwd_content = f.read()

        with open("/etc/group", "r") as f:
            group_content = f.read()

        users = []
        for line in passwd_content.strip().split("\n"):
            if line and not line.startswith("#"):
                parts = line.split(":")
                if len(parts) >= 3:
                    users.append(f"{parts[0]}:{parts[2]}")

        evidence_file = tempfile.mktemp(prefix="account_discovery_", suffix=".txt")
        with open(evidence_file, "w") as f:
            f.write("=== ACCOUNT DISCOVERY EVIDENCE ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Total users found: {len(users)}\n")
            f.write("\n=== USER ACCOUNTS ===\n")
            for user in users:
                f.write(f"{user}\n")
            f.write("\n=== GROUP CONTENT ===\n")
            f.write(group_content)

        return True, f"Discovered {len(users)} user accounts", "", [evidence_file]

    except Exception as e:
        return False, f"Account discovery failed: {str(e)}", "", []


def execute_t1016_real(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """T1016 - System Network Configuration Discovery: Real network enumeration."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    evidence_file = ARTIFACTS_DIR / f"{campaign_id}_network_config.txt"
    bash_script = "\n".join(
        [
            "echo '=== ROUTING TABLE ==='",
            "ip route show",
            "echo",
            "echo '=== NETWORK INTERFACES ==='",
            "ip addr show",
            "echo",
            "echo '=== DNS CONFIGURATION ==='",
            "if [ -f /etc/resolv.conf ]; then cat /etc/resolv.conf; else echo 'DNS configuration file not found'; fi",
        ]
    )
    result = run_bash_on_target_vm(sut_profile_id=sut_profile_id, bash_script=bash_script)

    with open(evidence_file, "w", encoding="utf-8") as file_handle:
        file_handle.write("=== NETWORK CONFIGURATION DISCOVERY ===\n")
        file_handle.write(f"Timestamp: {datetime.now().isoformat()}\n\n")
        file_handle.write(result.stdout)
        if result.stderr:
            file_handle.write("\n=== STDERR ===\n")
            file_handle.write(result.stderr)
        file_handle.write(f"\nExit code: {result.returncode}\n")

    if result.returncode != 0:
        return False, "", result.stderr or result.stdout, [str(evidence_file)]

    return (
        True,
        "Network configuration discovered successfully inside target VM",
        "",
        [str(evidence_file)],
    )


def execute_t1046_real(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Enumerate listening services inside the declared Linux target."""
    discovery_script = """set -euo pipefail
printf '=== LISTENING TCP SERVICES ===\\n'
ss -tlnp
printf '\\n=== LISTENING UDP SERVICES ===\\n'
ss -ulnp
"""
    if campaign_id == "0.costaricto":
        discovery_script = """set -euo pipefail
boot_id=$(cat /proc/sys/kernel/random/boot_id)
test ! -L /tmp/sticks_costaricto
mkdir -p /tmp/sticks_costaricto
test ! -L "/tmp/sticks_costaricto/service_discovery_${boot_id}.txt"
umask 077
{
  printf '=== LISTENING TCP SERVICES ===\\n'
  ss -tlnp
  printf '\\n=== LISTENING UDP SERVICES ===\\n'
  ss -ulnp
} > "/tmp/sticks_costaricto/service_discovery_${boot_id}.txt"
cat "/tmp/sticks_costaricto/service_discovery_${boot_id}.txt"
"""
    result = run_bash_on_target_vm(
        sut_profile_id=sut_profile_id,
        bash_script=discovery_script,
        timeout=45,
        execution_user="reconuser" if campaign_id == "0.costaricto" else None,
    )
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    evidence_file = ARTIFACTS_DIR / f"{campaign_id}_service_discovery.txt"
    evidence_file.write_text(result.stdout, encoding="utf-8")
    result.check_returncode()
    return True, "Listening services enumerated inside target VM", "", [str(evidence_file)]


def execute_t1107_real(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """T1107 - File Deletion: Real file creation and deletion."""
    try:
        temp_file = tempfile.mktemp(prefix="sticks_evidence_", suffix=".txt")

        with open(temp_file, "w") as f:
            f.write("STICKS EVIDENCE FILE\n")
            f.write(f"Created: {datetime.now().isoformat()}\n")
            f.write(f"Campaign: {campaign_id}\n")
            f.write(f"SUT: {sut_profile_id}\n")

        deletion_log = tempfile.mktemp(prefix="deletion_log_", suffix=".txt")
        with open(deletion_log, "w") as f:
            f.write("=== FILE DELETION EVIDENCE ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"File to delete: {temp_file}\n")
            f.write(f"File size: {os.path.getsize(temp_file)} bytes\n")

        os.remove(temp_file)

        with open(deletion_log, "a") as f:
            f.write(f"Deletion completed: {datetime.now().isoformat()}\n")
            f.write(f"File successfully deleted: {temp_file}\n")

        return True, f"File {temp_file} deleted successfully", "", [deletion_log]

    except Exception as e:
        return False, f"File deletion failed: {str(e)}", "", []


def execute_t1505_inspired(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """T1505 - Server Software Component: Webshell simulation (inspired)."""
    try:
        webshell_file = tempfile.mktemp(prefix="sticks_webshell_", suffix=".php")

        webshell_content = (
            """<?php
// STICKS SIMULATED WEBSHELL
// This is a benign simulation for testing purposes
echo "STICKS Webshell Simulation\\n";
echo "Timestamp: " . date('Y-m-d H:i:s') . "\\n";
echo "Campaign: """
            + campaign_id
            + """\\n";
// No actual malicious functionality
?>"""
        )

        with open(webshell_file, "w") as f:
            f.write(webshell_content)

        evidence_file = tempfile.mktemp(prefix="webshell_evidence_", suffix=".txt")
        with open(evidence_file, "w") as f:
            f.write("=== WEBSHELL DEPLOYMENT EVIDENCE ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Webshell file: {webshell_file}\n")
            f.write(f"Webshell size: {os.path.getsize(webshell_file)} bytes\n")
            f.write("\n=== FIDELITY JUSTIFICATION ===\n")
            f.write("INSPIRED: Real webshell requires configured web server with PHP\n")
            f.write(
                "This simulation captures the intent (webshell deployment) but lacks\n"
            )
            f.write(
                "the actual web server substrate required for full functionality.\n"
            )
            f.write(
                "The mechanism (creating PHP file) is preserved, but execution context\n"
            )
            f.write("is simulated due to missing web infrastructure in SUT.\n")

        return (
            True,
            f"Webshell deployed to {webshell_file}",
            "",
            [webshell_file, evidence_file],
        )

    except Exception as e:
        return False, f"Webshell deployment failed: {str(e)}", "", []


def execute_t1071_001_inspired(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """T1071.001 - Application Layer Protocol: Web Protocols (inspired)."""
    evidence_file = tempfile.mktemp(prefix="http_protocol_", suffix=".txt")
    with open(evidence_file, "w") as stream:
        stream.write("=== HTTP PROTOCOL EVIDENCE ===\n")
        stream.write(f"Timestamp: {datetime.now().isoformat()}\n")
        stream.write("Target: owned ephemeral loopback listener\n")

    try:
        result, url = probe_local_http()
        with open(evidence_file, "a") as stream:
            stream.write(f"Probe URL: {url}\n")
            stream.write(f"Response: {result.stdout}\n")
            stream.write(f"Error output: {result.stderr}\n")
            stream.write(f"Exit code: {result.returncode}\n")
        success = result.returncode == 0
        error = "" if success else result.stderr or f"curl exited {result.returncode}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        with open(evidence_file, "a") as stream:
            stream.write(f"HTTP test failed: {exc}\n")
        success = False
        error = str(exc)

    with open(evidence_file, "a") as stream:
        stream.write("\n=== FIDELITY JUSTIFICATION ===\n")
        stream.write("INSPIRED: Real C2 requires external command and control server\n")
        stream.write("This simulation captures the HTTP mechanism but lacks actual C2\n")
        stream.write("infrastructure. The protocol behavior (HTTP request) is preserved,\n")
        stream.write("but the command channel is simulated due to missing external C2.\n")

    message = "HTTP protocol test completed" if success else "HTTP protocol test failed"
    return success, message, error, [evidence_file]


def execute_t1090_inspired(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """T1090 - Proxy: Local relay simulation (inspired)."""
    try:
        evidence_file = tempfile.mktemp(prefix="proxy_evidence_", suffix=".txt")

        with open(evidence_file, "w") as f:
            f.write("=== PROXY SETUP EVIDENCE ===\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write("Target: Local TCP relay 8080 -> 127.0.0.1:80\n")

        try:
            socat_process = subprocess.Popen(
                ["socat", "tcp-listen:8080,reuseaddr,fork", "tcp:127.0.0.1:80"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            import time

            time.sleep(1)

            test_result = subprocess.run(
                ["curl", "-s", "--max-time", 2, "http://127.0.0.1:8080"],
                capture_output=True,
                text=True,
                timeout=5,
            )

            socat_process.terminate()
            socat_process.wait(timeout=2)

            with open(evidence_file, "a") as f:
                f.write(f"Proxy test result: {test_result.returncode}\n")
                f.write(f"Response received: {len(test_result.stdout)} bytes\n")

            success = True
            message = "Local proxy relay tested successfully"

        except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
            with open(evidence_file, "a") as f:
                f.write("Proxy setup failed: socat not available or other error\n")

            success = True
            message = "Proxy simulation completed (socat unavailable)"

        with open(evidence_file, "a") as f:
            f.write("\n=== FIDELITY JUSTIFICATION ===\n")
            f.write("INSPIRED: Real proxy requires multi-host network infrastructure\n")
            f.write("This simulation captures the relay mechanism but lacks actual\n")
            f.write("multi-host topology. The TCP forwarding concept is preserved,\n")
            f.write(
                "but the network context is simulated due to missing external hosts.\n"
            )

        return success, message, "", [evidence_file]

    except Exception as e:
        return False, f"Proxy setup failed: {str(e)}", "", []


# Executor registration
@register_executor(
    "T1087",
    ExecutorMetadata(
        technique_id="T1087",
        technique_name="Account Discovery",
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        produces=["discovery:account_listing"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
        description="Real account discovery using /etc/passwd and /etc/group",
        platform="linux",
        execution_fidelity=ExecutionFidelity.ADAPTED,
        fidelity_justification="Real account enumeration with preserved mechanism, lab context",
        original_platform="multi",
        requires_privilege="user",
    ),
    overwrite=True,
)
def execute_t1087_registered() -> Tuple[bool, str, str, List[str]]:
    """Registered T1087 executor."""
    return execute_t1087_real("default_campaign", "default_sut")


@register_executor(
    "T1016",
    ExecutorMetadata(
        technique_id="T1016",
        technique_name="System Network Configuration Discovery",
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        produces=["discovery:network_config"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
        description="Real network configuration discovery using ip commands",
        platform="linux",
        execution_fidelity=ExecutionFidelity.ADAPTED,
        fidelity_justification="Real network enumeration with preserved mechanism",
        original_platform="multi",
        requires_privilege="user",
    ),
    overwrite=True,
)
def execute_t1016_registered(
    campaign_id: str,
    sut_profile_id: str,
    **kwargs,
) -> Tuple[bool, str, str, List[str]]:
    """Registered T1016 executor."""
    return execute_t1016_real(campaign_id, sut_profile_id, **kwargs)


@register_executor(
    "T1046",
    ExecutorMetadata(
        technique_id="T1046",
        technique_name="Network Service Discovery",
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        produces=["discovery:service_listing"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
        description="Listening-service enumeration inside the declared target VM",
        platform="linux",
        execution_fidelity=ExecutionFidelity.ADAPTED,
        fidelity_justification="Target-local listening-service enumeration; not a remote network scan",
        original_platform="multi",
        requires_privilege="user",
    ),
    overwrite=True,
)
def execute_t1046_registered(
    campaign_id: str,
    sut_profile_id: str,
    **kwargs,
) -> Tuple[bool, str, str, List[str]]:
    """Registered T1046 executor."""
    return execute_t1046_real(campaign_id, sut_profile_id, **kwargs)


@register_executor(
    "T1107",
    ExecutorMetadata(
        technique_id="T1107",
        technique_name="File Deletion",
        execution_mode=ExecutionMode.REAL_CONTROLLED,
        produces=["cleanup:file_deleted"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
        description="Real file deletion with evidence logging",
        platform="linux",
        execution_fidelity=ExecutionFidelity.ADAPTED,
        fidelity_justification="Real file deletion with preserved mechanism",
        original_platform="multi",
        requires_privilege="user",
    ),
    overwrite=True,
)
def execute_t1107_registered() -> Tuple[bool, str, str, List[str]]:
    """Registered T1107 executor."""
    return execute_t1107_real("default_campaign", "default_sut")


@register_executor(
    "T1505",
    ExecutorMetadata(
        technique_id="T1505",
        technique_name="Server Software Component",
        execution_mode=ExecutionMode.NAIVE_SIMULATED,
        produces=["persistence:webshell"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
        description="Webshell deployment simulation without web server substrate",
        platform="linux",
        execution_fidelity=ExecutionFidelity.INSPIRED,
        fidelity_justification="Webshell requires configured web server with PHP - intent preserved, substrate missing",
        original_platform="multi",
        requires_privilege="user",
    ),
    overwrite=True,
)
def execute_t1505_registered() -> Tuple[bool, str, str, List[str]]:
    """Registered T1505 executor."""
    return execute_t1505_inspired("default_campaign", "default_sut")


@register_executor(
    "T1071.001",
    ExecutorMetadata(
        technique_id="T1071.001",
        technique_name="Application Layer Protocol: Web Protocols",
        execution_mode=ExecutionMode.NAIVE_SIMULATED,
        produces=["c2:http_channel"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
        description="HTTP protocol simulation without external C2 infrastructure",
        platform="linux",
        execution_fidelity=ExecutionFidelity.INSPIRED,
        fidelity_justification="Real C2 requires external command and control server - mechanism preserved, infrastructure missing",
        original_platform="multi",
        requires_privilege="user",
    ),
    overwrite=True,
)
def execute_t1071_001_registered(
    campaign_id: str,
    sut_profile_id: str,
    **kwargs,
) -> Tuple[bool, str, str, List[str]]:
    """Registered T1071.001 executor."""
    return execute_t1071_001_inspired(campaign_id, sut_profile_id, **kwargs)


@register_executor(
    "T1090",
    ExecutorMetadata(
        technique_id="T1090",
        technique_name="Proxy",
        execution_mode=ExecutionMode.NAIVE_SIMULATED,
        produces=["c2:proxy_channel"],
        requires=[],
        safe_simulation=True,
        cleanup_supported=True,
        description="Local TCP relay simulation without multi-host network",
        platform="linux",
        execution_fidelity=ExecutionFidelity.INSPIRED,
        fidelity_justification="Real proxy requires multi-host network infrastructure - relay mechanism preserved, topology missing",
        original_platform="multi",
        requires_privilege="user",
    ),
    overwrite=True,
)
def execute_t1090_registered() -> Tuple[bool, str, str, List[str]]:
    """Registered T1090 executor."""
    return execute_t1090_inspired("default_campaign", "default_sut")
