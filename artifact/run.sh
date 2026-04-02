#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "[artifact/run] executing canonical smoke campaign..."
python3 scripts/run_campaign.py --campaign 0.c0011

echo "[artifact/run] regenerating tables..."
python3 scripts/generate_tables.py

echo "[artifact/run] done"
