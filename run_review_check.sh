#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ "${1:-}" == "--legacy" ]]; then
  shift
  echo "[review] running the secondary legacy measurement check" >&2
  cd "$ROOT_DIR/measurement/sut"
  exec bash release_check.sh "$@"
fi

if [[ $# -ne 0 ]]; then
  echo "usage: bash run_review_check.sh [--legacy]" >&2
  exit 2
fi

source "$ROOT_DIR/scripts/python_env.sh"
PYTHON_BIN="$(sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt")"

if [[ -n "${PAPER_DIR:-}" ]]; then
  MANUSCRIPT_PATH="$PAPER_DIR/main.tex"
  if [[ ! -f "$MANUSCRIPT_PATH" ]]; then
    echo "[review][FAIL] PAPER_DIR does not contain main.tex: $PAPER_DIR" >&2
    exit 2
  fi
  exec "$PYTHON_BIN" "$ROOT_DIR/scripts/reproduce.py" --manuscript "$MANUSCRIPT_PATH"
fi

exec "$PYTHON_BIN" "$ROOT_DIR/scripts/reproduce.py"
