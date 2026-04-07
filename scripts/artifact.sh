#!/bin/bash
# artifact.sh - Interactive helper for the STICKS artifact
# NOTE:
#   Canonical non-interactive pipeline is:
#     ./run_campaign.sh <campaign_id> [--provider ...]
#   This script remains as an interactive wrapper for convenience.
#
# Usage: ./artifact.sh [command]
#   ./artifact.sh menu     - Interactive menu (default)
#   ./artifact.sh doctor   - Check dependencies and health
#   ./artifact.sh list     - List available campaigns
#   ./artifact.sh run      - Run campaign (interactive selection)
#   ./artifact.sh status   - Check lab status
#   ./artifact.sh evidence - Collect and display evidence
#   ./artifact.sh destroy  - Destroy lab environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_NAME="STICKS Artifact"
VERSION="release-candidate"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'
BOLD='\033[1m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${CYAN}[STEP]${NC} $1"; }
log_header() { echo -e "${BOLD}$1${NC}"; }

show_banner() {
    clear
    echo ""
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║              STICKS Artifact - Release Candidate           ║"
    echo "║     Limits of Semantic CTI for Multi-Stage APT Emulation     ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo ""
}

doctor_mode() {
    log_header "ARTIFACT HEALTH CHECK"
    echo ""
    
    local errors=0
    local warnings=0
    
    # Check 1: Python
    log_step "Checking Python..."
    if command -v python3 &> /dev/null; then
        local py_version=$(python3 --version 2>&1)
        log_info "✓ $py_version"
    else
        log_error "✗ Python3 not found"
        ((errors++))
    fi
    
    # Check 2: Required Python packages
    log_step "Checking Python packages..."
    if python3 -c "import yaml, json, pathlib" 2>/dev/null; then
        log_info "✓ Required packages available"
    else
        log_warn "⚠ Some Python packages may be missing"
        ((warnings++))
    fi
    
    # Check 3: Vagrant
    log_step "Checking Vagrant..."
    if command -v vagrant &> /dev/null; then
        local vg_version=$(vagrant --version 2>&1)
        log_info "✓ $vg_version"
    else
        log_warn "⚠ Vagrant not found (required for full-lab mode)"
        ((warnings++))
    fi
    
    # Check 4: VirtualBox
    log_step "Checking VirtualBox..."
    if command -v VBoxManage &> /dev/null; then
        local vb_version=$(VBoxManage --version 2>&1 | head -1)
        log_info "✓ VirtualBox $vb_version"
    else
        log_warn "⚠ VirtualBox not found (required for full-lab mode)"
        ((warnings++))
    fi
    
    # Check 5: Directory structure
    log_step "Checking directory structure..."
    local required_dirs=("lab" "sticks" "measurement" "artifact" "release")
    for dir in "${required_dirs[@]}"; do
        if [[ -d "$SCRIPT_DIR/$dir" ]]; then
            log_info "✓ $dir/"
        else
            log_error "✗ $dir/ missing"
            ((errors++))
        fi
    done
    
    # Check 6: SUT Profiles
    log_step "Checking SUT profiles..."
    local profiles=("0.c0011" "0.pikabot_realistic" "0.lateral_test")
    for profile in "${profiles[@]}"; do
        if [[ -f "$SCRIPT_DIR/lab/sut_profiles/${profile}.yml" ]]; then
            log_info "✓ $profile"
        else
            log_error "✗ $profile profile missing"
            ((errors++))
        fi
    done
    
    # Check 7: Entrypoint scripts
    log_step "Checking entrypoints..."
    local scripts=("setup.sh" "run_campaign.sh" "collect_evidence.sh" "reset.sh" "destroy.sh")
    for script in "${scripts[@]}"; do
        if [[ -f "$SCRIPT_DIR/$script" && -x "$SCRIPT_DIR/$script" ]]; then
            log_info "✓ $script"
        else
            log_warn "⚠ $script missing or not executable"
            ((warnings++))
        fi
    done
    
    # Summary
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    if [[ $errors -eq 0 && $warnings -eq 0 ]]; then
        log_info "✓ ALL CHECKS PASSED - Artifact ready for use"
        return 0
    elif [[ $errors -eq 0 ]]; then
        log_warn "⚠ $warnings warning(s) - Local-test mode available, full-lab may have issues"
        return 0
    else
        log_error "✗ $errors error(s), $warnings warning(s) - Fix before proceeding"
        return 1
    fi
}

list_campaigns() {
    log_header "AVAILABLE CAMPAIGNS"
    echo ""
    
    local profiles_dir="$SCRIPT_DIR/lab/sut_profiles"
    local count=0
    
    for profile in "$profiles_dir"/*.yml; do
        [[ -f "$profile" ]] || continue
        local name=$(basename "$profile" .yml)
        [[ "$name" == _* ]] && continue
        
        ((count++))
        local desc=$(grep "^description:" "$profile" 2>/dev/null | head -1 | cut -d':' -f2- | sed 's/^[[:space:]]*//' || echo "No description")
        local hosts=$(grep "min_hosts:" "$profile" 2>/dev/null | head -1 | awk '{print $2}' || echo "?")
        
        echo "  ${BOLD}$count.${NC} $name"
        echo "     Description: $desc"
        echo "     Required hosts: $hosts"
        echo "     Profile: $profile"
        echo ""
    done
    
    if [[ $count -eq 0 ]]; then
        log_error "No campaigns found in $profiles_dir"
        return 1
    fi
    
    echo "────────────────────────────────────────────────────────────────"
    echo "To run: ./artifact.sh run"
    echo ""
}

get_campaign_choice() {
    local profiles=()
    local profiles_dir="$SCRIPT_DIR/lab/sut_profiles"
    
    for profile in "$profiles_dir"/*.yml; do
        [[ -f "$profile" ]] || continue
        local name=$(basename "$profile" .yml)
        [[ "$name" == _* ]] && continue
        profiles+=("$name")
    done
    
    echo ""
    log_header "SELECT CAMPAIGN"
    echo ""
    
    for i in "${!profiles[@]}"; do
        local idx=$((i + 1))
        echo "  $idx. ${profiles[$i]}"
    done
    echo "  0. Cancel"
    echo ""
    
    while true; do
        read -p "Enter choice [1-${#profiles[@]}, 0]: " choice
        
        if [[ "$choice" == "0" ]]; then
            return 1
        fi
        
        if [[ "$choice" =~ ^[0-9]+$ && $choice -ge 1 && $choice -le ${#profiles[@]} ]]; then
            local idx=$((choice - 1))
            SELECTED_CAMPAIGN="${profiles[$idx]}"
            return 0
        fi
        
        log_error "Invalid choice. Please try again."
    done
}

show_campaign_details() {
    local campaign_id=$1
    local profile="$SCRIPT_DIR/lab/sut_profiles/${campaign_id}.yml"
    
    log_header "CAMPAIGN: $campaign_id"
    echo ""
    
    # Parse profile for details
    if [[ -f "$profile" ]]; then
        local desc=$(grep "^description:" "$profile" | head -1 | cut -d':' -f2- | sed 's/^[[:space:]]*//' || echo "N/A")
        local hosts=$(grep "min_hosts:" "$profile" | head -1 | awk '{print $2}' || echo "N/A")
        local duration=$(grep "estimated_duration_minutes:" "$profile" | head -1 | awk '{print $2}' || echo "N/A")
        
        echo "  Description: $desc"
        echo "  Required VMs: $hosts"
        echo "  Estimated Duration: ${duration} minutes"
        echo ""
        echo "  Fidelity Expectations:"
        sed -n '/fidelity_expectations:/,/^[a-z]/p' "$profile" | grep -E "^\s+T[0-9]" | head -10 | while read -r line; do
            local tech=$(echo "$line" | awk '{print $1}')
            local fid=$(echo "$line" | awk '{print $2}' | tr -d '"')
            echo "    $tech: $fid"
        done
        echo ""
    fi
}

run_mode() {
    show_banner
    
    # Get campaign selection
    if ! get_campaign_choice; then
        log_info "Cancelled by user"
        return 0
    fi
    
    local campaign_id=$SELECTED_CAMPAIGN
    show_campaign_details "$campaign_id"
    
    echo ""
    echo "────────────────────────────────────────────────────────────────"
    read -p "Proceed with execution? [Y/n]: " confirm
    
    if [[ ! "$confirm" =~ ^[Yy]$ && ! -z "$confirm" ]]; then
        log_info "Execution cancelled"
        return 0
    fi
    
    echo ""
    log_step "Starting execution pipeline..."
    
    # Run SUT health check first
    log_step "Running SUT health check..."
    if ! python3 sut_health_checker.py "$campaign_id" "$SCRIPT_DIR/lab/sut_profiles/${campaign_id}.yml"; then
        log_warn "SUT health check failed, but continuing..."
    fi
    
    # Choose execution mode
    echo ""
    echo "Select execution mode:"
    echo "  1. local-test (fast, no VMs - for validation)"
    echo "  2. full-lab (with Vagrant VMs - for real evaluation)"
    echo ""
    read -p "Enter choice [1-2, default=1]: " mode_choice
    
    if [[ "$mode_choice" == "2" ]]; then
        run_full_lab "$campaign_id"
    else
        run_local_test "$campaign_id"
    fi
}

run_local_test() {
    local campaign_id=$1
    
    log_step "Running LOCAL-TEST mode"
    echo "  Campaign: $campaign_id"
    echo "  Mode: Simulated execution (no VMs)"
    echo ""
    
    cd "$SCRIPT_DIR"
    
    if ! python3 local_campaign_runner.py --campaign "$campaign_id"; then
        log_error "Execution failed"
        return 1
    fi
    
    echo ""
    log_info "✓ Execution complete"
    show_evidence_summary
}

run_full_lab() {
    local campaign_id=$1
    
    log_step "Running FULL-LAB mode"
    echo "  Campaign: $campaign_id"
    echo "  Mode: Real VMs with Vagrant"
    echo ""
    
    # Check prerequisites
    if ! command -v vagrant &> /dev/null; then
        log_error "Vagrant not found. Install from https://www.vagrantup.com/"
        return 1
    fi
    
    if ! command -v VBoxManage &> /dev/null; then
        log_error "VirtualBox not found. Install from https://www.virtualbox.org/"
        return 1
    fi
    
    cd "$SCRIPT_DIR"
    
    # Delegate to canonical non-interactive pipeline
    log_step "Delegating to canonical pipeline: run_campaign.sh"
    if ! ./run_campaign.sh "$campaign_id"; then
        log_error "Canonical pipeline failed"
        return 1
    fi
    
    echo ""
    log_info "✓ Full pipeline complete (canonical flow)"
    show_evidence_summary
}

show_evidence_summary() {
    echo ""
    log_header "EVIDENCE SUMMARY"
    echo ""
    
    local evidence_dir="$SCRIPT_DIR/release/evidence"
    
    if [[ ! -d "$evidence_dir" ]]; then
        log_error "No evidence directory found"
        return 1
    fi
    
    # Find latest evidence
    local latest=$(find "$evidence_dir" -name "summary.json" -type f -exec ls -t {} + | head -1)
    
    if [[ -z "$latest" ]]; then
        log_warn "No evidence files found"
        return 1
    fi
    
    # Show summary
    if command -v python3 &> /dev/null; then
        python3 << PYEOF
import json
import sys

try:
    with open("$latest") as f:
        data = json.load(f)
    
    print(f"Campaign: {data.get('campaign_id', 'N/A')}")
    print(f"Mode: {data.get('execution_mode', 'N/A')}")
    print(f"Total Techniques: {data.get('total_techniques', 0)}")
    print(f"Successful: {data.get('successful', 0)}")
    print(f"Failed: {data.get('failed', 0)}")
    print(f"")
    print("Fidelity Distribution:")
    for fid, count in data.get('fidelity_distribution', {}).items():
        print(f"  {fid}: {count}")
except Exception as e:
    print(f"Error reading evidence: {e}")
PYEOF
    fi
    
    echo ""
    log_info "Evidence location: $latest"
}

collect_evidence_mode() {
    log_header "COLLECTING EVIDENCE"
    echo ""
    
    cd "$SCRIPT_DIR"
    ./collect_evidence.sh
    
    show_evidence_summary
}

destroy_mode() {
    log_header "DESTROY LAB ENVIRONMENT"
    echo ""
    
    read -p "Are you sure? This will remove all VMs and data. [y/N]: " confirm
    
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        cd "$SCRIPT_DIR"
        ./destroy.sh
    else
        log_info "Cancelled"
    fi
}

show_menu() {
    while true; do
        show_banner
        
        echo "  ${BOLD}MAIN MENU${NC}"
        echo ""
        echo "  1. Doctor - Check artifact health"
        echo "  2. List - Show available campaigns"
        echo "  3. Run - Execute a campaign"
        echo "  4. Evidence - View collected evidence"
        echo "  5. Destroy - Clean up lab environment"
        echo ""
        echo "  0. Exit"
        echo ""
        echo "────────────────────────────────────────────────────────────────"
        
        read -p "Enter choice [0-5]: " choice
        
        case $choice in
            1)
                doctor_mode
                read -p "Press Enter to continue..."
                ;;
            2)
                list_campaigns
                read -p "Press Enter to continue..."
                ;;
            3)
                run_mode
                read -p "Press Enter to continue..."
                ;;
            4)
                collect_evidence_mode
                read -p "Press Enter to continue..."
                ;;
            5)
                destroy_mode
                read -p "Press Enter to continue..."
                ;;
            0)
                echo ""
                log_info "Thank you for using STICKS Artifact"
                echo ""
                exit 0
                ;;
            *)
                log_error "Invalid choice"
                sleep 1
                ;;
        esac
    done
}

main() {
    # Handle direct commands
    case "${1:-menu}" in
        doctor)
            doctor_mode
            ;;
        list|campaigns)
            list_campaigns
            ;;
        run|execute)
            run_mode
            ;;
        status)
            doctor_mode
            ;;
        evidence|results)
            collect_evidence_mode
            ;;
        destroy|clean)
            destroy_mode
            ;;
        menu|*)
            show_menu
            ;;
    esac
}

main "$@"
