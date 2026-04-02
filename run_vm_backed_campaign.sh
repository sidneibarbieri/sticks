#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"
campaign="${1:-0.c0011}"
python3 scripts/run_lab_campaign.py --campaign "$campaign"
