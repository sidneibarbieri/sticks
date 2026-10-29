#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
usage() {
  echo "Usage: bash artifact/validate.sh --run-root /absolute/completed/run"
  echo "Verifies the typed final receipt, source and evidence hashes, independent observations, and teardown."
}
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi
if [[ $# -ne 2 || "$1" != "--run-root" ]]; then
  usage >&2
  exit 2
fi
cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/python_env.sh"
PYTHON_BIN="$(sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt")"
"$PYTHON_BIN" scripts/finalize_isolated_lab_run.py --run-root "$2" --verify
