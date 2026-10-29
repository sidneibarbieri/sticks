#!/bin/bash
# Destroy VMs declared by one campaign, or all managed VMs with explicit --all.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
source "$SCRIPT_DIR/python_env.sh"
PYTHON_BIN="$(sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt")"
CAMPAIGN_ID=""
CAMPAIGN_FILTER_SUPPLIED=false
DESTROY_ALL=false
TARGET_VMS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --campaign)
            [[ $# -ge 2 ]] || { echo "Missing campaign ID" >&2; exit 2; }
            CAMPAIGN_ID="$2"
            CAMPAIGN_FILTER_SUPPLIED=true
            shift 2
            ;;
        --all)
            DESTROY_ALL=true
            shift
            ;;
        --help|-h)
            echo "Usage: ./destroy_lab.sh (--campaign ID | --all)"
            exit 0
            ;;
        *)
            echo "Unknown option: $1" >&2
            exit 2
            ;;
    esac
done

if [[ "$CAMPAIGN_FILTER_SUPPLIED" == "$DESTROY_ALL" ]]; then
    echo "Specify exactly one of --campaign ID or --all" >&2
    exit 2
fi

if [[ "$CAMPAIGN_FILTER_SUPPLIED" == true && -z "$CAMPAIGN_ID" ]]; then
    echo "Invalid campaign ID: empty value" >&2
    exit 2
fi

if [[ -n "$CAMPAIGN_ID" ]]; then
    if [[ ! "$CAMPAIGN_ID" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ || "$CAMPAIGN_ID" == *..* ]]; then
        echo "Invalid campaign ID: $CAMPAIGN_ID" >&2
        exit 2
    fi

    topology="$("$PYTHON_BIN" - "$ROOT_DIR" "$CAMPAIGN_ID" <<'PYEOF'
import sys
from pathlib import Path

import yaml

root_dir = Path(sys.argv[1])
campaign_id = sys.argv[2]
profile_path = root_dir / "data" / "sut_profiles" / f"{campaign_id}.yml"
if not profile_path.is_file():
    sys.exit(f"SUT profile not found for campaign {campaign_id}: {profile_path}")

with profile_path.open(encoding="utf-8") as handle:
    profile = yaml.safe_load(handle) or {}

required_vms = profile.get("requirements", {}).get("required_vms", [])
if not isinstance(required_vms, list) or not required_vms:
    sys.exit(f"Missing requirements.required_vms in {profile_path}")

aliases = {
    "target-base": "target-linux-1",
    "target-1": "target-linux-1",
    "target": "target-linux-1",
    "target-2": "target-linux-2",
}
managed_vms = {"caldera", "attacker", "target-linux-1", "target-linux-2"}
resolved = []
for vm_name in required_vms:
    managed_name = aliases.get(vm_name, vm_name)
    if managed_name not in managed_vms:
        sys.exit(f"Unsupported VM in {profile_path}: {vm_name}")
    if managed_name not in resolved:
        resolved.append(managed_name)

print("\n".join(resolved))
PYEOF
    )"
    while IFS= read -r vm_name; do
        TARGET_VMS+=("$vm_name")
    done <<< "$topology"
fi

if [[ ${#TARGET_VMS[@]} -eq 0 ]]; then
    if [[ "$DESTROY_ALL" != true ]]; then
        echo "No managed VMs declared for campaign: $CAMPAIGN_ID" >&2
        exit 2
    fi
    for vm_name in caldera attacker target-linux-1 target-linux-2; do
        vm_dir="$ROOT_DIR/lab/vagrant/$vm_name"
        [[ -f "$vm_dir/Vagrantfile" ]] || continue
        TARGET_VMS+=("$vm_name")
    done
fi

failures=0
for vm_name in "${TARGET_VMS[@]}"; do
    vm_dir="$ROOT_DIR/lab/vagrant/$vm_name"
    if [[ ! -f "$vm_dir/Vagrantfile" ]]; then
        echo "[DESTROY-LAB] Missing Vagrantfile for $vm_name" >&2
        failures=1
        continue
    fi

    echo "[DESTROY-LAB] Destroying $vm_name"
    if ! (cd "$vm_dir" && vagrant destroy -f); then
        echo "[DESTROY-LAB] Failed to destroy $vm_name" >&2
        failures=1
    fi
done

exit "$failures"
