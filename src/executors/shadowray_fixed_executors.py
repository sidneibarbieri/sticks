#!/usr/bin/env python3
"""
ShadowRay Executors - Fixed with correct tuple return format
"""

import hashlib
import subprocess
import time
from pathlib import Path
from typing import List, Tuple

from executors.executor_registry import (
    ExecutorMetadata,
    execute_t1105_real,
    execute_t1190_real,
    execute_t1588_002_real,
    register_executor,
)
from executors.lab_transport import run_bash_on_target_vm
from executors.c0045_readonly_commands import TraceKind, command_spec
from executors.c0045_trace_executor import run_traced_readonly_step
from executors.models import (
    ExecutionFidelity,
    ExecutionMode,
)


def execute_t1190_shadowray_fixed(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Probe only the Ray-like API already provisioned in the declared SUT."""
    if campaign_id != "0.shadowray":
        return execute_t1190_real(campaign_id, sut_profile_id, **kwargs)

    bash_script = r"""
set -euo pipefail
version_response=$(curl -fsS --max-time 3 http://127.0.0.1:8265/api/version)
jobs_response=$(curl -fsS --max-time 3 http://127.0.0.1:8265/api/jobs/)
python3 - "$version_response" "$jobs_response" <<'PYEOF'
import json
import sys

version = json.loads(sys.argv[1])
jobs = json.loads(sys.argv[2])
if version.get("service") != "ray-dashboard" or jobs.get("auth") != "disabled":
    raise SystemExit("The declared Ray-like API response was not observed")
if not isinstance(jobs.get("jobs"), list):
    raise SystemExit("The declared Ray-like jobs response was not observed")
print("[T1190] Ray-like service boundary observed")
PYEOF
"""

    try:
        result = run_bash_on_target_vm(
            sut_profile_id=sut_profile_id,
            bash_script=bash_script,
            timeout=60,
            execution_user="rayuser",
        )
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired) as exc:
        return False, "", str(exc), []

    artifacts_dir = Path("data/artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    log_path = artifacts_dir / "shadowray_ray_api_probe.log"
    log_path.write_text(
        result.stdout + ("\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )

    if result.returncode != 0:
        stderr = (
            result.stderr.strip() or result.stdout.strip() or "Ray API probe failed"
        )
        return False, result.stdout, stderr, [str(log_path)]

    if "[T1190] Ray-like service boundary observed" not in result.stdout:
        return False, result.stdout, "Guest Ray API observation missing", [str(log_path)]

    stdout = (
        "Ray-like HTTP fixture observed inside the target VM.\n"
        f"{result.stdout.strip()}"
    )
    return True, stdout, result.stderr, [str(log_path)]


def _run_shadowray_vm_script(
    sut_profile_id: str,
    bash_script: str,
    artifact_name: str,
    success_message: str,
    timeout: int = 45,
    trace_kind: TraceKind | None = None,
    live_observer=None,
) -> Tuple[bool, str, str, List[str]]:
    """Execute a ShadowRay step inside the target VM and persist the transcript."""
    if live_observer is not None:
        if trace_kind is None or bash_script != command_spec(trace_kind).script:
            raise ValueError("Observed execution requires a reviewed command")
        result = run_traced_readonly_step(sut_profile_id, trace_kind, live_observer, timeout=timeout)
    else:
        try:
            result = run_bash_on_target_vm(
                sut_profile_id=sut_profile_id,
                bash_script=bash_script,
                timeout=timeout,
                execution_user="rayuser",
            )
        except (FileNotFoundError, ValueError, subprocess.TimeoutExpired) as exc:
            return False, "", str(exc), []

    artifacts_dir = Path("data/artifacts")
    artifacts_dir.mkdir(exist_ok=True)
    artifact_path = artifacts_dir / artifact_name
    artifact_path.write_text(
        result.stdout + ("\n=== STDERR ===\n" + result.stderr if result.stderr else ""),
        encoding="utf-8",
    )

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip() or "VM execution failed"
        return False, result.stdout, stderr, [str(artifact_path)]

    stdout = success_message
    if result.stdout.strip():
        stdout += f"\n{result.stdout.strip()}"
    return True, stdout, result.stderr, [str(artifact_path)]


def execute_t1003_008_shadowray_vm(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Check target credential-file accessibility without copying file content."""
    bash_script = """
set -eu
if sudo -n test -r /etc/shadow 2>/dev/null; then
  printf 'sudo-readable\n'
else
  printf 'sudo-unavailable\n'
fi
"""
    result = run_bash_on_target_vm(
        sut_profile_id=sut_profile_id,
        bash_script=bash_script,
        timeout=45,
        execution_user="rayuser",
    )
    if result.returncode != 0:
        return False, "", result.stderr or f"Credential probe exited {result.returncode}", []
    status = result.stdout.strip()
    if status not in {"sudo-readable", "sudo-unavailable"} or result.stderr:
        raise ValueError("Unexpected credential probe output")
    artifact_path = Path("data/artifacts/shadowray_credentials_probe.txt")
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(status + "\n", encoding="utf-8")
    return (
        True,
        f"Credential-file accessibility probe completed in target VM: {status}; no contents copied",
        "",
        [str(artifact_path)],
    )


def execute_t1059_006_shadowray_vm(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Python execution performed inside the target VM."""
    bash_script = command_spec("python").script
    return _run_shadowray_vm_script(
        sut_profile_id=sut_profile_id,
        bash_script=bash_script,
        artifact_name="shadowray_python_execution.txt",
        success_message="Python execution completed inside the target VM.",
        trace_kind="python", live_observer=kwargs.get("live_observer"),
    )


def execute_t1105_shadowray_vm(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Ingress tool transfer performed over HTTP inside the target VM."""
    bash_script = """
set -e
workspace=/tmp/sticks-shadowray-transfer
mkdir -p "$workspace/source"
cat > "$workspace/source/network_tool.sh" <<'EOF'
#!/bin/bash
echo "Network Reconnaissance Tool"
echo "Target: ${1:-127.0.0.1}"
echo "Mode: ${2:-ping}"
EOF
chmod +x "$workspace/source/network_tool.sh"
cd "$workspace/source"
python3 -m http.server 18080 --bind 127.0.0.1 >/tmp/sticks-shadowray-http.log 2>&1 &
server_pid=$!
trap 'kill $server_pid 2>/dev/null || true' EXIT
sleep 2
kill -0 "$server_pid"
curl -fsS http://127.0.0.1:18080/network_tool.sh -o "$workspace/downloaded_tool.sh"
cmp "$workspace/source/network_tool.sh" "$workspace/downloaded_tool.sh"
chmod +x "$workspace/downloaded_tool.sh"
bash "$workspace/downloaded_tool.sh" 127.0.0.1 ping
ls -l "$workspace/downloaded_tool.sh"
printf '[transfer-target] %s\\n' "$(hostname)"
"""
    success, stdout, stderr, artifacts = _run_shadowray_vm_script(
        sut_profile_id=sut_profile_id,
        bash_script=bash_script,
        artifact_name="shadowray_tool_transfer.txt",
        success_message="Ingress tool transfer completed inside the target VM.",
        timeout=60,
    )
    if success and "[transfer-target] " not in stdout:
        return False, stdout, "Guest transfer observation missing", artifacts
    return success, stdout, stderr, artifacts


def execute_t1016_shadowray_fixed(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Inspect network configuration only through the declared target transport."""
    bash_script = command_spec("network").script
    success, stdout, stderr, artifacts = _run_shadowray_vm_script(
        sut_profile_id=sut_profile_id,
        bash_script=bash_script,
        artifact_name="shadowray_network_discovery.txt",
        success_message="Network configuration observed inside the target VM.",
        trace_kind="network", live_observer=kwargs.get("live_observer"),
    )
    if success and "[network-target] " not in stdout:
        return False, stdout, "Guest network observation missing", artifacts
    return success, stdout, stderr, artifacts


def execute_t1496_001_shadowray_vm(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Bounded compute-hijacking simulation inside the target VM."""
    bash_script = """
set -e
python3 - <<'PY'
import hashlib
import time
from pathlib import Path

duration = 3
start = time.time()
count = 0
while time.time() - start < duration:
    hashlib.sha256(f"block-{count}-{time.time()}".encode()).hexdigest()
    count += 1

log_path = Path("/tmp/sticks-shadowray-mining.log")
log_path.write_text(
    "\\n".join(
        [
            "Cryptocurrency Mining Simulation",
            f"Duration: {duration} seconds",
            f"Hashes calculated: {count}",
            f"Hash rate: {count / duration:.2f} H/s",
            "Status: Simulation completed",
        ]
    )
)
print(log_path.read_text())
PY
"""
    return _run_shadowray_vm_script(
        sut_profile_id=sut_profile_id,
        bash_script=bash_script,
        artifact_name="shadowray_mining_simulation.txt",
        success_message="Compute-hijacking simulation completed inside the target VM.",
        timeout=60,
    )


def execute_t1546_004_shadowray_vm(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Shell configuration persistence simulated inside the target VM."""
    bash_script = """
set -e
workspace=/tmp/sticks-shadowray-persistence
mkdir -p "$workspace"
cat > "$workspace/.bashrc_sticks_simulation" <<'EOF'
# STICKS Simulation: Persistence Mechanism
export STICKS_PERSISTENCE="active"
alias sticks-ping='echo "STICKS: System check complete"'
sticks_check() {
  echo "STICKS: Persistence active at $(date)"
}
sticks_check
EOF
cat > "$workspace/sticks_backup.sh" <<'EOF'
#!/bin/bash
cp /tmp/sticks-shadowray-persistence/.bashrc_sticks_simulation /tmp/sticks-shadowray-persistence/.bashrc_sticks_backup
echo "Backup completed"
EOF
chmod 755 "$workspace/sticks_backup.sh"
setpriv --no-new-privs bash --noprofile --rcfile "$workspace/.bashrc_sticks_simulation" -i -c '
  set -e
  test "$STICKS_PERSISTENCE" = active
  alias sticks-ping
  echo "[shell-startup] $STICKS_PERSISTENCE"
'
bash "$workspace/sticks_backup.sh"
cmp "$workspace/.bashrc_sticks_simulation" "$workspace/.bashrc_sticks_backup"
"""
    success, stdout, stderr, artifacts = _run_shadowray_vm_script(
        sut_profile_id=sut_profile_id,
        bash_script=bash_script,
        artifact_name="shadowray_persistence_simulation.txt",
        success_message="Isolated shell startup checked inside the target VM; the user startup file was not changed.",
    )
    if success and "[shell-startup] active" not in stdout:
        return False, stdout, "Guest shell-startup observation missing", artifacts
    return success, stdout, stderr, artifacts


def execute_t1588_002_shadowray_vm(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Tool acquisition simulated inside the target VM."""
    bash_script = """
set -e
toolkit=/tmp/sticks-shadowray-toolkit
mkdir -p "$toolkit"
cat > "$toolkit/port_scanner.py" <<'EOF'
#!/usr/bin/env python3
from concurrent.futures import ThreadPoolExecutor
import socket
import sys

host = sys.argv[1] if len(sys.argv) > 1 else "127.0.0.1"
max_port = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
if not 1 <= max_port <= 65535:
    raise ValueError("Port limit must be between 1 and 65535")
def scan_port(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as connection:
        connection.settimeout(1)
        result = connection.connect_ex((host, port))
    return f"{host}:{port} {'open' if result == 0 else 'closed'}"

with ThreadPoolExecutor(max_workers=min(50, max_port)) as executor:
    for observation in executor.map(scan_port, range(1, max_port + 1)):
        print(observation)
EOF
cat > "$toolkit/service_enum.sh" <<'EOF'
#!/bin/bash
target="${1:-127.0.0.1}"
for port in 22 80 443 8265; do
  timeout 2 bash -c "</dev/tcp/$target/$port" 2>/dev/null && echo "Port $port: OPEN" || true
done
EOF
cat > "$toolkit/sys_profiler.py" <<'EOF'
#!/usr/bin/env python3
import json
import os
import platform
import socket

print(json.dumps({
    "platform": platform.platform(),
    "architecture": platform.architecture(),
    "processor": platform.processor(),
    "hostname": socket.gethostname(),
    "user": os.getenv("USER", "unknown"),
    "home": os.getenv("HOME", "unknown"),
    "shell": os.getenv("SHELL", "unknown"),
    "network_interfaces": len(socket.if_nameindex()),
    "process_count": len([entry for entry in os.listdir('/proc') if entry.isdigit()]),
}, sort_keys=True))
EOF
chmod 755 "$toolkit/port_scanner.py" "$toolkit/service_enum.sh" "$toolkit/sys_profiler.py"
python3 "$toolkit/port_scanner.py" 127.0.0.1 4
python3 "$toolkit/sys_profiler.py"
ls -l "$toolkit"
printf '[toolkit-target] %s\\n' "$(hostname)"
"""
    success, stdout, stderr, artifacts = _run_shadowray_vm_script(
        sut_profile_id=sut_profile_id,
        bash_script=bash_script,
        artifact_name="shadowray_toolkit_acquisition.txt",
        success_message="Tool-acquisition simulation completed inside the target VM.",
        timeout=60,
    )
    if success and "[toolkit-target] " not in stdout:
        return False, stdout, "Guest toolkit observation missing", artifacts
    return success, stdout, stderr, artifacts


def execute_t1027_013_shadowray_fixed(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Obfuscated Files or Information: Encrypted/Encoded File - FIXED"""
    try:
        original_payload = """
import os
import subprocess
# Simulated malicious payload
print("Executing simulated malicious code...")
os.system("echo 'Simulated execution completed'")
"""

        import base64

        encoded_payload = base64.b64encode(original_payload.encode()).decode()

        obfuscated_content = f'''
# Obfuscated Python script
import base64
import sys

# Hidden payload
payload = "{encoded_payload}"
decoded = base64.b64decode(payload).decode()
exec(decoded)
'''

        artifacts_dir = Path("data/artifacts")
        artifacts_dir.mkdir(exist_ok=True)

        obfuscated_file = artifacts_dir / "obfuscated_script.py"
        with open(obfuscated_file, "w") as f:
            f.write(obfuscated_content)

        decoder_content = f'''
import base64

# Decode the obfuscated script
with open("data/artifacts/obfuscated_script.py", "r") as f:
    content = f.read()

# Extract and decode payload
payload = "{encoded_payload}"
decoded = base64.b64decode(payload).decode()

print("Original payload:")
print(decoded)
'''

        decoder_file = artifacts_dir / "decoder.py"
        with open(decoder_file, "w") as f:
            f.write(decoder_content)

        stdout = f"Created obfuscated script: {obfuscated_file}\n"
        stdout += f"Created decoder script: {decoder_file}\n"
        stdout += f"Payload size: {len(original_payload)} bytes\n"
        stdout += f"Encoded size: {len(encoded_payload)} bytes\n"

        artifacts = [str(obfuscated_file), str(decoder_file)]
        return True, stdout, "", artifacts

    except Exception as e:
        return False, "", str(e), []


def execute_t1105_shadowray_fixed(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Transfer the controlled ShadowRay fixture only inside the target VM."""
    if campaign_id != "0.shadowray":
        return execute_t1105_real(campaign_id, sut_profile_id, **kwargs)
    return execute_t1105_shadowray_vm(campaign_id, sut_profile_id, **kwargs)


def execute_t1496_001_shadowray_fixed(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Resource Hijacking: Compute Hijacking - FIXED"""
    try:
        mining_duration = 3
        start_mining = time.time()

        hash_count = 0
        while time.time() - start_mining < mining_duration:
            hashlib.sha256(f"block_{hash_count}_{time.time()}".encode()).hexdigest()
            hash_count += 1

        artifacts_dir = Path("data/artifacts")
        artifacts_dir.mkdir(exist_ok=True)

        mining_log = artifacts_dir / "mining_log.txt"
        with open(mining_log, "w") as f:
            f.write("Cryptocurrency Mining Simulation\n")
            f.write(f"Duration: {mining_duration} seconds\n")
            f.write(f"Hashes calculated: {hash_count}\n")
            f.write(f"Hash rate: {hash_count / mining_duration:.2f} H/s\n")
            f.write("Status: Simulation completed\n")

        stdout = "Simulated mining completed\n"
        stdout += f"Duration: {mining_duration} seconds\n"
        stdout += f"Hashes calculated: {hash_count}\n"
        stdout += f"Hash rate: {hash_count / mining_duration:.2f} H/s\n"

        artifacts = [str(mining_log)]
        return True, stdout, "", artifacts

    except Exception as e:
        return False, "", str(e), []


def execute_t1546_004_shadowray_fixed(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Compatibility entry point for the target-only shell fixture."""
    return execute_t1546_004_shadowray_vm(campaign_id, sut_profile_id, **kwargs)


def execute_t1588_002_shadowray_fixed(
    campaign_id: str, sut_profile_id: str, **kwargs
) -> Tuple[bool, str, str, List[str]]:
    """Use the ShadowRay toolkit only for the ShadowRay campaign."""
    if campaign_id != "0.shadowray":
        return execute_t1588_002_real(campaign_id, sut_profile_id, **kwargs)
    return execute_t1588_002_shadowray_vm(campaign_id, sut_profile_id, **kwargs)


# Register all FIXED ShadowRay executors
metadata_t1190 = ExecutorMetadata(
    technique_id="T1190",
    technique_name="Exploit Public-Facing Application",
    execution_mode=ExecutionMode.REAL_CONTROLLED,
    produces=["observation:ray_api_http"],
    requires=["network:http_available"],
    safe_simulation=True,
    cleanup_supported=True,
    description="HTTP observation of the SUT-provisioned Ray-like fixture",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification=(
        "Observes the declared Ray-like HTTP fixture; this GET does not establish "
        "initial access, Ray Jobs execution, or CVE exploitation."
    ),
    original_platform="any",
    requires_privilege="user",
)

metadata_t1003_008 = ExecutorMetadata(
    technique_id="T1003.008",
    technique_name="OS Credential Dumping: /etc/passwd and /etc/shadow",
    execution_mode=ExecutionMode.NAIVE_SIMULATED,
    produces=["simulation:credential_access_probe_recorded"],
    requires=[],
    safe_simulation=True,
    cleanup_supported=True,
    description="Bounded credential-file accessibility probe without content capture",
    platform="linux",
    execution_fidelity=ExecutionFidelity.INSPIRED,
    fidelity_justification="Checks target credential-file accessibility without collecting or dumping credentials",
    original_platform="linux",
    requires_privilege="user",
)

metadata_t1059_006 = ExecutorMetadata(
    technique_id="T1059.006",
    technique_name="Command and Scripting Interpreter: Python",
    execution_mode=ExecutionMode.REAL_CONTROLLED,
    produces=["artifacts:python_script", "system:recon_data"],
    requires=[],
    safe_simulation=True,
    cleanup_supported=True,
    description="Python-based reconnaissance",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification="Uses Python for safe system reconnaissance",
    original_platform="linux",
    requires_privilege="user",
)

metadata_t1027_013 = ExecutorMetadata(
    technique_id="T1027.013",
    technique_name="Obfuscated Files or Information: Encrypted/Encoded File",
    execution_mode=ExecutionMode.NAIVE_SIMULATED,
    produces=["simulation:encoded_fixture_recorded"],
    requires=[],
    safe_simulation=True,
    cleanup_supported=True,
    description="File obfuscation simulation",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification="Realistic base64 obfuscation technique",
    original_platform="linux",
    requires_privilege="user",
)

metadata_t1105 = ExecutorMetadata(
    technique_id="T1105",
    technique_name="Ingress Tool Transfer",
    execution_mode=ExecutionMode.REAL_CONTROLLED,
    produces=["artifacts:downloaded_tool", "artifacts:tool_script", "payload:staged"],
    requires=["c2_channel", "network:http_available"],
    safe_simulation=True,
    cleanup_supported=True,
    description="Safe tool transfer in the current lab substrate",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification="Transfers a benign payload over HTTP while preserving observable ingress behavior",
    original_platform="linux",
    requires_privilege="user",
)

metadata_t1496_001 = ExecutorMetadata(
    technique_id="T1496.001",
    technique_name="Resource Hijacking: Compute Hijacking",
    execution_mode=ExecutionMode.NAIVE_SIMULATED,
    produces=["simulation:bounded_compute_recorded"],
    requires=[],
    safe_simulation=True,
    cleanup_supported=True,
    description="Bounded guest CPU workload; simulated resource hijacking",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification=(
        "Runs bounded local CPU work in the guest; does not reproduce "
        "unauthorized hijacking or external mining"
    ),
    original_platform="linux",
    requires_privilege="user",
)

metadata_t1546_004 = ExecutorMetadata(
    technique_id="T1546.004",
    technique_name="Event Triggered Execution: Unix Shell Configuration Modification",
    execution_mode=ExecutionMode.NAIVE_SIMULATED,
    produces=["simulation:shell_startup_fixture_recorded"],
    requires=[],
    safe_simulation=True,
    cleanup_supported=True,
    description="Shell configuration persistence simulation",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification="Realistic persistence mechanism simulation",
    original_platform="linux",
    requires_privilege="user",
)

metadata_t1588_002 = ExecutorMetadata(
    technique_id="T1588.002",
    technique_name="Obtain Capabilities: Tool",
    execution_mode=ExecutionMode.REAL_CONTROLLED,
    produces=["artifacts:recon_toolkit", "system:toolkit"],
    requires=[],
    safe_simulation=True,
    cleanup_supported=True,
    description="Reconnaissance toolkit creation",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification="Creates multi-tool reconnaissance toolkit",
    original_platform="linux",
    requires_privilege="user",
)

metadata_t1016 = ExecutorMetadata(
    technique_id="T1016",
    technique_name="System Network Configuration Discovery",
    execution_mode=ExecutionMode.REAL_CONTROLLED,
    produces=["discovery:network_config"],
    requires=[],
    safe_simulation=True,
    cleanup_supported=True,
    description="Network configuration discovery inside the declared ShadowRay target",
    platform="linux",
    execution_fidelity=ExecutionFidelity.ADAPTED,
    fidelity_justification="Collects guest interfaces and routes through target-only transport",
    original_platform="multi",
    requires_privilege="user",
)

# Register FIXED executors with overwrite=True to replace broken ones
register_executor("T1190", metadata_t1190, overwrite=True, campaign_id="0.shadowray")(
    execute_t1190_shadowray_fixed
)
register_executor("T1003.008", metadata_t1003_008, overwrite=True, campaign_id="0.shadowray")(
    execute_t1003_008_shadowray_vm
)
register_executor("T1059.006", metadata_t1059_006, overwrite=True, campaign_id="0.shadowray")(
    execute_t1059_006_shadowray_vm
)
register_executor("T1027.013", metadata_t1027_013, overwrite=True, campaign_id="0.shadowray")(
    execute_t1027_013_shadowray_fixed
)
register_executor("T1105", metadata_t1105, overwrite=True, campaign_id="0.shadowray")(
    execute_t1105_shadowray_fixed
)
register_executor("T1496.001", metadata_t1496_001, overwrite=True, campaign_id="0.shadowray")(
    execute_t1496_001_shadowray_vm
)
register_executor("T1546.004", metadata_t1546_004, overwrite=True, campaign_id="0.shadowray")(
    execute_t1546_004_shadowray_vm
)
register_executor("T1588.002", metadata_t1588_002, overwrite=True, campaign_id="0.shadowray")(
    execute_t1588_002_shadowray_fixed
)
register_executor("T1016", metadata_t1016, overwrite=True, campaign_id="0.shadowray")(
    execute_t1016_shadowray_fixed
)
