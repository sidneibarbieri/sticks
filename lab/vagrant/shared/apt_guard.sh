#!/bin/bash
# apt_guard.sh - Deterministic apt/dpkg helpers for reproducible VM provisioning

set -euo pipefail

apt_guard_log() { echo "[APT-GUARD] $1"; }
apt_guard_error() { echo "[APT-GUARD] ERROR: $1" >&2; }

APT_TRANSPORT_OPTIONS=(
    -o Acquire::Retries=3
    -o Acquire::http::Timeout=30
    -o Acquire::https::Timeout=30
    -o DPkg::Lock::Timeout=300
)

disable_periodic_apt_jobs() {
    export DEBIAN_FRONTEND=noninteractive

    cat > /etc/apt/apt.conf.d/99sticks-no-periodic <<'EOF'
APT::Periodic::Enable "0";
APT::Periodic::Update-Package-Lists "0";
APT::Periodic::Unattended-Upgrade "0";
EOF

    systemctl stop unattended-upgrades.service >/dev/null 2>&1 || true
    systemctl disable unattended-upgrades.service >/dev/null 2>&1 || true
}

wait_for_apt_ready() {
    local timeout_seconds="${1:-300}"
    local start_time
    start_time="$(date +%s)"

    while pgrep -f unattended-upgrade >/dev/null 2>&1 \
        || pgrep -x apt-get >/dev/null 2>&1 \
        || pgrep -x apt >/dev/null 2>&1 \
        || pgrep -x dpkg >/dev/null 2>&1; do
        if (( $(date +%s) - start_time >= timeout_seconds )); then
            apt_guard_error "Timed out waiting for apt/dpkg locks to clear"
            return 1
        fi

        apt_guard_log "Waiting for apt/dpkg locks to clear..."
        sleep 5
    done
}

apt_update_quiet() {
    wait_for_apt_ready || return $?
    apt-get "${APT_TRANSPORT_OPTIONS[@]}" update -qq
}

apt_install_quiet() {
    wait_for_apt_ready || return $?
    apt-get "${APT_TRANSPORT_OPTIONS[@]}" install -y -qq "$@"
}

apt_install_minimal() {
    wait_for_apt_ready || return $?
    apt-get "${APT_TRANSPORT_OPTIONS[@]}" install -y -qq --no-install-recommends "$@"
}

apt_package_installed() {
    local status
    status="$(dpkg-query -W -f='${Status}' "$1" 2>/dev/null)" || return 1
    [[ "$status" == "install ok installed" ]]
}

apt_install_missing_minimal() {
    local package
    local -a missing_packages=()
    for package in "$@"; do
        if ! apt_package_installed "$package"; then
            missing_packages+=("$package")
        fi
    done
    if ((${#missing_packages[@]} == 0)); then
        apt_guard_log "Required packages already installed; skipping apt network access"
        return 0
    fi
    apt_update_quiet || return $?
    apt_install_minimal "${missing_packages[@]}"
}
