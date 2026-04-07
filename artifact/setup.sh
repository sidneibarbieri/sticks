#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

echo "[artifact/setup] checking python..."
command -v python3 >/dev/null

if [[ ! -d ".venv" ]]; then
  echo "[artifact/setup] creating virtual environment..."
  python3 -m venv .venv
fi

echo "[artifact/setup] installing dependencies..."
source .venv/bin/activate
python3 -m pip install -r requirements.txt

echo "[artifact/setup] validating imports..."
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" python3 -c "import loaders.campaign_loader; import runners.campaign_runner"

if command -v vagrant >/dev/null 2>&1; then
  echo "[artifact/setup] vagrant detected"
else
  echo "[artifact/setup] vagrant not detected; optional lab helpers may be unavailable"
fi

if command -v qemu-system-aarch64 >/dev/null 2>&1; then
  echo "[artifact/setup] qemu detected"
else
  echo "[artifact/setup] qemu not detected; optional qemu helpers may be unavailable"
fi

echo "[artifact/setup] done"
