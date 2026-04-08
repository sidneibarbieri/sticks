#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/python_env.sh"
PYTHON_BIN="$(sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt")"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

echo "[artifact/run] executing canonical smoke campaign..."
"$PYTHON_BIN" scripts/run_campaign.py --campaign 0.c0011

echo "[artifact/run] regenerating tables..."
"$PYTHON_BIN" scripts/generate_tables.py

echo "[artifact/run] done"
