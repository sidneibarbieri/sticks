#!/bin/bash
# Provision the pinned Caldera runtime used by STICKS VM campaigns.

set -euo pipefail

. /tmp/apt_guard.sh

CALDERA_DIR="/opt/caldera"
CALDERA_VERSION="5.3.0"
CALDERA_COMMIT="b24f6e7a99cab19cbf417009bda9b9c6c81abc31"
ATOMIC_COMMIT="388942adbd9641f4dfdcf079d7efe9a75ec0ac43"
STICKS_CALDERA_WITH_ATOMIC="${STICKS_CALDERA_WITH_ATOMIC:-0}"
case "$STICKS_CALDERA_WITH_ATOMIC" in
    0) CALDERA_PLUGINS="sandcat,stockpile,response,gameboard,training,access,manx,magma" ;;
    1) CALDERA_PLUGINS="sandcat,stockpile,response,gameboard,training,access,atomic,manx,magma" ;;
    *) echo "STICKS_CALDERA_WITH_ATOMIC must be 0 or 1" >&2; exit 2 ;;
esac
export STICKS_CALDERA_WITH_ATOMIC
NODE_VERSION="22.22.3"
NODE_ARCHIVE_CACHE="/tmp/sticks-node-v22.22.3-linux.tar.xz"
RUNTIME_REQUIREMENTS_FILE="/tmp/caldera-runtime-requirements.txt"

node_architecture() {
    case "$(uname -m)" in
        aarch64) echo "arm64" ;;
        x86_64) echo "x64" ;;
        *) echo "Unsupported Node architecture: $(uname -m)" >&2; return 1 ;;
    esac
}

node_archive_sha256() {
    case "$1" in
        arm64) echo "1c4a9933a5e45bc88f54f70b5f91232c127ec49f1a5989d23fb85824c7adf9b7" ;;
        x64) echo "2e5d13569282d016861fae7c8f935e741693c269101a5bebcf761a5376d1f99f" ;;
        *) return 1 ;;
    esac
}

install_node() {
    local architecture archive_name archive_path node_dir expected_sha
    architecture="$(node_architecture)"
    archive_name="node-v${NODE_VERSION}-linux-${architecture}.tar.xz"
    archive_path="$NODE_ARCHIVE_CACHE"
    node_dir="/opt/node-v${NODE_VERSION}-linux-${architecture}"
    expected_sha="$(node_archive_sha256 "$architecture")"

    if [[ ! -f "$archive_path" ]]; then
        curl -fL --retry 5 --retry-delay 2 --max-time 1200 \
            "https://nodejs.org/dist/v${NODE_VERSION}/${archive_name}" \
            -o "$archive_path"
    fi
    printf '%s  %s\n' "$expected_sha" "$archive_path" | sha256sum -c -
    if [[ ! -x "$node_dir/bin/node" ]]; then
        tar -xJf "$archive_path" -C /opt
    fi
    NODE_BIN_DIR="$node_dir/bin"
    export PATH="$NODE_BIN_DIR:$PATH"
    node --version
}

wait_for_dns() {
    local host="$1" max_attempts="$2" retry_seconds="$3" attempt
    for ((attempt = 1; attempt <= max_attempts; attempt++)); do
        if getent ahosts "$host" >/dev/null 2>&1; then
            return 0
        fi
        if ((attempt < max_attempts)); then
            sleep "$retry_seconds"
        fi
    done
    echo "[CALDERA] DNS did not resolve $host after $max_attempts attempts" >&2
    return 1
}

install_caldera_source() {
    if [[ ! -d "$CALDERA_DIR/.git" ]]; then
        wait_for_dns github.com 30 5
        timeout 600 git clone --depth 1 --branch "$CALDERA_VERSION" \
            https://github.com/mitre/caldera.git "$CALDERA_DIR"
    fi
    cd "$CALDERA_DIR"
    if [[ "$(git rev-parse HEAD)" != "$CALDERA_COMMIT" ]]; then
        echo "Caldera checkout differs from the pinned 5.3.0 commit" >&2
        return 1
    fi
    local submodules=(
        plugins/access plugins/gameboard plugins/magma plugins/manx
        plugins/response plugins/sandcat plugins/stockpile plugins/training
    )
    if [[ "$STICKS_CALDERA_WITH_ATOMIC" == "1" ]]; then
        submodules+=(plugins/atomic)
    fi
    wait_for_dns github.com 30 5
    timeout 600 git submodule update --init --recursive --depth 1 "${submodules[@]}"
}

install_atomic_inputs() {
    local atomic_dir="$CALDERA_DIR/plugins/atomic/data/atomic-red-team"
    if [[ ! -d "$atomic_dir/.git" ]]; then
        wait_for_dns github.com 30 5
        git init "$atomic_dir"
        git -C "$atomic_dir" remote add origin https://github.com/redcanaryco/atomic-red-team.git
        timeout 600 git -C "$atomic_dir" -c http.lowSpeedLimit=1000 -c http.lowSpeedTime=60 \
            fetch --depth 1 origin "$ATOMIC_COMMIT"
        git -C "$atomic_dir" checkout --detach FETCH_HEAD
    fi
    if [[ "$(git -C "$atomic_dir" rev-parse HEAD)" != "$ATOMIC_COMMIT" ]]; then
        echo "Atomic Red Team inputs differ from the pinned commit" >&2
        return 1
    fi
    test -f "$atomic_dir/atomic_red_team/enterprise-attack.json"
    test -d "$atomic_dir/atomics"
    echo "[CALDERA] Atomic inputs verified: $ATOMIC_COMMIT"
}

configure_caldera() {
    python3 - <<'PY'
from pathlib import Path

import os
import yaml

default_path = Path("/opt/caldera/conf/default.yml")
local_path = Path("/opt/caldera/conf/local.yml")
with default_path.open(encoding="utf-8") as default_file:
    configuration = yaml.safe_load(default_file)
configuration["plugins"] = [
    "sandcat", "stockpile", "response", "gameboard", "training",
    "access", "manx", "magma",
]
if os.environ["STICKS_CALDERA_WITH_ATOMIC"] == "1":
    configuration["plugins"].insert(6, "atomic")
with local_path.open("w", encoding="utf-8") as local_file:
    yaml.safe_dump(configuration, local_file, sort_keys=False)
PY
}

create_caldera_service() {
    cat > /etc/systemd/system/caldera.service <<EOF
[Unit]
Description=MITRE Caldera Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/caldera
Environment=PATH=${NODE_BIN_DIR}:/usr/lib/go-1.22/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=/usr/bin/python3 /opt/caldera/server.py -E local --plugins ${CALDERA_PLUGINS}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable caldera
}

wait_for_caldera_http() {
    local attempt
    for attempt in $(seq 1 60); do
        if systemctl is-active --quiet caldera \
            && curl -fsS --max-time 3 http://127.0.0.1:8888/ -o /dev/null 2>/dev/null; then
            echo "[CALDERA] HTTP ready on 127.0.0.1:8888"
            return 0
        fi
        sleep 5
    done
    echo "[CALDERA] HTTP did not become ready" >&2
    journalctl -u caldera -n 80 --no-pager >&2
    return 1
}

disable_periodic_apt_jobs
apt_update_quiet
apt_install_minimal python3-pip git curl xz-utils golang-1.22-go
install_caldera_source
if [[ "$STICKS_CALDERA_WITH_ATOMIC" == "1" ]]; then
    install_atomic_inputs
fi
test -f "$RUNTIME_REQUIREMENTS_FILE"
pip3 install --retries 5 --timeout 60 --prefer-binary -r "$RUNTIME_REQUIREMENTS_FILE"
install_node
cd "$CALDERA_DIR/plugins/magma"
timeout 900 npm ci --no-audit --no-fund \
    --fetch-retries=5 \
    --fetch-retry-mintimeout=10000 \
    --fetch-retry-maxtimeout=60000 \
    --fetch-timeout=120000
npm run build
test -d "$CALDERA_DIR/plugins/magma/dist/assets"
configure_caldera
create_caldera_service
systemctl restart caldera
wait_for_caldera_http
