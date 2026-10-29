#!/bin/bash
# up_lab.sh - Bring up lab infrastructure for STICKS campaigns
# Usage: ./up_lab.sh --campaign 0.c0011

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
EVIDENCE_DIR="${STICKS_EVIDENCE_DIR:-$ROOT_DIR/release/evidence}"
QEMU_BOX="perk/ubuntu-2204-arm64"
SOCKET_VMNET_SOCKET="${STICKS_SOCKET_VMNET_SOCKET:-/opt/homebrew/var/run/socket_vmnet}"
CAMPAIGN_ID=""
PROVIDER=""
STRICT_PREPARED="${STICKS_STRICT_PREPARED:-0}"
PYTHON_BIN=""

log_info() { echo "[UP-LAB] $1"; }
log_error() { echo "[UP-LAB] ERROR: $1" >&2; }
log_warn() { echo "[UP-LAB] WARN: $1"; }

show_help() {
    cat << EOF
STICKS Lab Infrastructure - Up Script

Usage: ./up_lab.sh [OPTIONS]

Options:
    --campaign ID    Campaign ID to provision for (required)
    --provider NAME  Vagrant provider (qemu|virtualbox) [default: qemu]
    --help          Show this help

Examples:
    ./up_lab.sh --campaign 0.c0011
    ./up_lab.sh --campaign 0.c0011 --provider virtualbox

EOF
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --campaign)
                CAMPAIGN_ID="$2"
                shift 2
                ;;
            --provider)
                PROVIDER="$2"
                shift 2
                ;;
            --help|-h)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done
}

validate_campaign_id() {
    if [[ ! "$CAMPAIGN_ID" =~ ^[0-9]+\.[A-Za-z0-9][A-Za-z0-9_-]*$ ]]; then
        log_error "Invalid campaign ID: expected a versioned identifier such as 0.c0011"
        exit 1
    fi
}

detect_default_provider() {
    if [[ -n "$PROVIDER" ]]; then
        return
    fi

    local os_name
    local arch_name
    os_name="$(uname -s)"
    arch_name="$(uname -m)"

    if [[ "$os_name" == "Darwin" && "$arch_name" == "arm64" ]]; then
        PROVIDER="qemu"
    else
        PROVIDER="libvirt"
    fi
}

box_supports_qemu_import() {
    vagrant box list | awk -v box_name="$QEMU_BOX" '
        $1 == box_name && ($2 == "(qemu," || $2 == "(libvirt,") && $0 ~ /\(arm64\)\)$/ {
            found = 1
        }
        END { exit(found ? 0 : 1) }
    '
}

require_socket_vmnet() {
    local python_bin="${PYTHON_BIN:-python3}"
    if [[ -S "$SOCKET_VMNET_SOCKET" ]]; then
        if "$python_bin" - "$SOCKET_VMNET_SOCKET" <<'PY'
import socket
import sys

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
    connection.settimeout(2)
    connection.connect(sys.argv[1])
PY
        then
            if [[ "$SOCKET_VMNET_SOCKET" == "/opt/homebrew/var/run/socket_vmnet" ]]; then
                require_single_socket_vmnet_daemon
            fi
            return 0
        fi
    fi

    log_error "socket_vmnet is not running at: $SOCKET_VMNET_SOCKET"
    log_error "The QEMU lab requires this daemon for its multi-VM private subnet."
    log_error "Install it, start it for 192.168.56.0/24, then set STICKS_SOCKET_VMNET_SOCKET if needed."
    exit 1
}

require_single_socket_vmnet_daemon() {
    local daemon_count
    local python_bin="${PYTHON_BIN:-python3}"
    daemon_count="$("$python_bin" - "/opt/homebrew/opt/socket_vmnet/bin/socket_vmnet" <<'PY'
import subprocess
import sys

binary = sys.argv[1]
processes = subprocess.run(
    ["ps", "-axo", "pid=,command="],
    check=True,
    capture_output=True,
    text=True,
).stdout.splitlines()
daemon_pids = []
for process in processes:
    fields = process.strip().split(maxsplit=1)
    if len(fields) == 2 and fields[1].startswith(binary + " "):
        daemon_pids.append(fields[0])
print(" ".join(daemon_pids))
PY
)"
    local -a daemon_pids=()
    read -r -a daemon_pids <<< "$daemon_count"
    if [[ ${#daemon_pids[@]} -ne 1 ]]; then
        log_error "Expected exactly one socket_vmnet daemon; found ${#daemon_pids[@]}: ${daemon_count:-none}"
        log_error "Stop duplicate daemons, retain one listener for ${SOCKET_VMNET_SOCKET}, then retry."
        exit 1
    fi
    log_info "[ok] socket_vmnet has one active daemon (pid ${daemon_pids[0]})"
}

check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v vagrant &> /dev/null; then
        log_error "Vagrant not found. Run ./setup.sh first."
        exit 1
    fi

    # Check for QEMU provider (macOS ARM64 preferred)
    if [[ "$PROVIDER" == "qemu" ]]; then
        local plugin_version
        plugin_version="$(vagrant plugin list | awk '$1 == "vagrant-qemu" {gsub(/^\(/, "", $2); gsub(/,/, "", $2); print $2; exit}')"
        if [[ "$plugin_version" != "0.6.3" ]]; then
            log_error "The validated multi-VM QEMU lab requires vagrant-qemu 0.6.3."
            log_error "Install the provider with: vagrant plugin install vagrant-qemu --plugin-version 0.6.3"
            exit 1
        fi
        if ! "$PYTHON_BIN" "$SCRIPT_DIR/apply_vagrant_qemu_socket_vmnet_fix.py" --check; then
            log_error "The vagrant-qemu socket_vmnet transport has not been prepared."
            log_error "Run: $PYTHON_BIN $SCRIPT_DIR/apply_vagrant_qemu_socket_vmnet_fix.py"
            exit 1
        fi
        log_info "[ok] QEMU provider ready"
        if ! box_supports_qemu_import; then
            log_error "Required ARM64 box is not installed: ${QEMU_BOX}"
            log_error "Install the pinned libvirt-format box; vagrant-qemu imports its qcow2 image."
            exit 1
        fi
        require_socket_vmnet
    fi

    # Check for libvirt provider
    if [[ "$PROVIDER" == "libvirt" ]]; then
        if ! vagrant plugin list | grep -q vagrant-libvirt; then
            log_warn "vagrant-libvirt plugin not found. Installing..."
            vagrant plugin install vagrant-libvirt || {
                log_error "Failed to install vagrant-libvirt plugin"
                log_error "On macOS, install: brew install libvirt"
                log_error "Then: vagrant plugin install vagrant-libvirt"
                exit 1
            }
        fi
        log_info "[ok] libvirt provider ready"
    fi

    # Check for VirtualBox provider
    if [[ "$PROVIDER" == "virtualbox" ]]; then
        if ! command -v VBoxManage &> /dev/null; then
            log_error "VirtualBox not found. Install from https://www.virtualbox.org/"
            exit 1
        fi
        log_info "[ok] VirtualBox ready"
    fi
}

determine_topology() {
    log_info "Determining topology for campaign: $CAMPAIGN_ID"

    VMS=()
    while IFS= read -r vm_name; do
        [[ -n "$vm_name" ]] || continue
        VMS+=("$vm_name")
    done < <(
        "$PYTHON_BIN" - "$CAMPAIGN_ID" "$ROOT_DIR" <<'PYEOF'
import sys
from pathlib import Path
import yaml

campaign_id = sys.argv[1]
root_dir = Path(sys.argv[2])
profile_path = root_dir / "data" / "sut_profiles" / f"{campaign_id}.yml"

if not profile_path.exists():
    print(f"SUT profile not found for campaign {campaign_id}: {profile_path}", file=sys.stderr)
    sys.exit(1)

with open(profile_path, "r", encoding="utf-8") as f:
    raw = yaml.safe_load(f) or {}

required_vms = raw.get("requirements", {}).get("required_vms", [])
if not required_vms:
    print(
        f"Missing requirements.required_vms in {profile_path}",
        file=sys.stderr,
    )
    sys.exit(1)

alias = {
    "target-base": "target-linux-1",
    "target-1": "target-linux-1",
    "target": "target-1",
    "target-2": "target-linux-2",
}

resolved = []
for vm in required_vms:
    resolved_vm = alias.get(vm, vm)
    if resolved_vm not in resolved:
        resolved.append(resolved_vm)

for vm in resolved:
    print(vm)
PYEOF
    )

    if [[ ${#VMS[@]} -eq 0 ]]; then
        log_error "Could not resolve VM topology for campaign: $CAMPAIGN_ID"
        exit 1
    fi

    log_info "Topology resolved from SUT profile: ${VMS[*]} (${#VMS[@]} VMs)"
}

bring_up_vm() {
    local vm_name=$1
    local vm_dir="$ROOT_DIR/lab/vagrant/$vm_name"

    log_info "Bringing up VM: $vm_name..."

    if [[ ! -d "$vm_dir" ]]; then
        log_error "VM directory not found: $vm_dir"
        return 1
    fi

    cd "$vm_dir"

    # Check if already running
    if vagrant status 2>/dev/null | grep -q "running"; then
        log_info "  $vm_name already running; applying idempotent provisioning"
        vagrant provision 2>&1 | while read line; do
            echo "  [$vm_name] $line"
        done

        if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
            log_info "[ok] $vm_name is provisioned"
            return 0
        fi

        log_error "[fail] $vm_name provisioning failed"
        return 1
    fi

    # Bring up with specified provider
    vagrant up --provider "$PROVIDER" 2>&1 | while read line; do
        echo "  [$vm_name] $line"
    done

    if [[ ${PIPESTATUS[0]} -eq 0 ]]; then
        log_info "[ok] $vm_name is up"
        return 0
    else
        log_error "[fail] $vm_name failed to start"
        return 1
    fi
}

wait_for_caldera() {
    log_info "Waiting for Caldera service from the attacker network position..."

    local max_attempts=12
    local attempt=1
    local private_url="http://192.168.56.10:8888/"
    local attacker_dir="$ROOT_DIR/lab/vagrant/attacker"

    while [[ $attempt -le $max_attempts ]]; do
        if (
            cd "$attacker_dir"
            vagrant ssh -c "curl -fsS --connect-timeout 3 --max-time 5 $private_url -o /dev/null"
        ); then
            log_info "[ok] Caldera HTTP is reachable from the attacker network position"
            return 0
        fi

        log_info "  Attempt $attempt/$max_attempts - waiting 5s..."
        sleep 5
        attempt=$((attempt + 1))
    done

    log_error "Caldera server did not become ready within timeout"
    log_error "Checked the declared private endpoint from the attacker: $private_url"
    return 1
}

verify_network() {
    log_info "Verifying network connectivity..."

    for vm in "${VMS[@]}"; do
        local ip=""
        case "$vm" in
            caldera) ip="192.168.56.10" ;;
            attacker) ip="192.168.56.20" ;;
            target-linux-1) ip="192.168.56.30" ;;
            target-linux-2) ip="192.168.56.31" ;;
        esac

        if ping -c 1 -W 2 "$ip" &>/dev/null; then
            log_info "[ok] $vm ($ip) reachable"
        else
            log_warn "[fail] $vm ($ip) not responding to ping (may be normal)"
        fi
    done
}

main() {
    parse_args "$@"
    detect_default_provider
    PYTHON_BIN="$(sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt")"

    if [[ -z "$CAMPAIGN_ID" ]]; then
        log_error "Campaign ID required. Use --campaign ID"
        show_help
        exit 1
    fi

    validate_campaign_id

    log_info "========================================"
    log_info "STICKS Lab Infrastructure - UP"
    log_info "Campaign: $CAMPAIGN_ID"
    log_info "Provider: $PROVIDER"
    log_info "========================================"

    check_dependencies
    determine_topology

    log_info "Bringing up VMs..."
    for vm in "${VMS[@]}"; do
        bring_up_vm "$vm" || {
            log_error "Failed to bring up $vm"
            log_error "Check vagrant status and logs"
            exit 1
        }
    done

    transport_args=()
    for vm in "${VMS[@]}"; do
        transport_args+=(--vm "$vm")
    done
    "$PYTHON_BIN" "$SCRIPT_DIR/verify_socket_vmnet_transport.py" "${transport_args[@]}"

    # Wait for Caldera if it's in the topology
    if [[ " ${VMS[*]} " =~ " caldera " ]]; then
        wait_for_caldera
    fi

    # Apply the declared SUT profile before readiness is certified.  A health
    # report from the base VM is not evidence that the configured SUT is ready.
    if [[ "$STRICT_PREPARED" == "1" ]]; then
        log_info "Using prepared strict images; profile application is forbidden"
    else
        log_info "========================================"
        log_info "Applying SUT profile..."
        log_info "========================================"
        "$PYTHON_BIN" "$ROOT_DIR/apply_sut_profile.py" --campaign "$CAMPAIGN_ID" --base-dir "$ROOT_DIR" --provider "$PROVIDER"
    fi

    # 3-level health check (VM ready → Service ready → Campaign ready). This
    # is the final fail-closed pre-flight before any campaign command runs.
    log_info "========================================"
    log_info "Running 3-level health check..."
    log_info "========================================"
    "$PYTHON_BIN" "$ROOT_DIR/lab/health_check.py" --campaign "$CAMPAIGN_ID" --provider "$PROVIDER" --output "$EVIDENCE_DIR"
    log_info "[ok] Health check PASSED"

    log_info "========================================"
    log_info "[ok] Lab infrastructure is UP and CONFIGURED"
    log_info "========================================"
    log_info "Provider: $PROVIDER"
    log_info "Campaign: $CAMPAIGN_ID"
    log_info "VMs: ${VMS[*]}"
    log_info ""
    log_info "Next steps:"
    log_info "  1. Run campaign: python3 $ROOT_DIR/scripts/run_campaign.py --campaign $CAMPAIGN_ID"
    log_info "  2. Collect evidence: ls -la $ROOT_DIR/release/evidence/"
    log_info "  3. Destroy: $SCRIPT_DIR/destroy_lab.sh --campaign $CAMPAIGN_ID"
}

main "$@"
