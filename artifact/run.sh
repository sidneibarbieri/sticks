#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage() {
  echo "Usage: bash artifact/run.sh --run-root /absolute/new/run"
  echo "This command materializes infrastructure; --help only describes the path."
  echo "Runs C0026 in fresh QEMU VMs, observes the target independently, tears down, and seals evidence."
}
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 2 || "$1" != "--run-root" ]]; then
  usage >&2
  exit 2
fi
RUN_ROOT="$2"
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/python_env.sh"
PYTHON_BIN="$(sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt")"
"$PYTHON_BIN" scripts/run_isolated_lab_campaign.py --campaign 0.c0026 --provider qemu --run-root "$RUN_ROOT" --keep-lab
"$PYTHON_BIN" scripts/complete_c0026_run.py --run-root "$RUN_ROOT"
echo "[artifact/run] observed, torn down, and sealed: $RUN_ROOT"
