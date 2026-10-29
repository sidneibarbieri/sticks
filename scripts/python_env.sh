#!/usr/bin/env bash
set -euo pipefail

sticks_python_check_core_deps() {
  local candidate="$1"
  "$candidate" - <<'PY'
import importlib

for module in ("pydantic", "yaml", "click", "pytest"):
    importlib.import_module(module)
PY
}

sticks_python_has_core_deps() {
  sticks_python_check_core_deps "$1" >/dev/null 2>&1
}

sticks_resolve_python() {
  local root_dir="$1"
  local requirements_file="${2:-$root_dir/requirements.txt}"
  local venv_dir="${root_dir}/.venv"
  local venv_python="${venv_dir}/bin/python3"

  if [[ -n "${STICKS_PYTHON:-}" ]]; then
    if [[ ! -x "$STICKS_PYTHON" ]]; then
      echo "[python-env][FAIL] STICKS_PYTHON must name an executable interpreter" >&2
      return 1
    fi
    if ! sticks_python_check_core_deps "$STICKS_PYTHON"; then
      echo "[python-env][FAIL] STICKS_PYTHON lacks required core dependencies; no fallback attempted" >&2
      return 1
    fi
    printf '%s\n' "$STICKS_PYTHON"
    return 0
  fi

  if [[ -x "$venv_python" ]]; then
    if sticks_python_has_core_deps "$venv_python"; then
      printf '%s\n' "$venv_python"
      return 0
    fi
    echo "[python-env] repairing repo-local virtual environment at $venv_dir" >&2
    PIP_DISABLE_PIP_VERSION_CHECK=1 "$venv_python" -m pip install -r "$requirements_file" >&2
    printf '%s\n' "$venv_python"
    return 0
  fi

  if command -v python3 >/dev/null 2>&1; then
    local system_python
    system_python="$(command -v python3)"
    if sticks_python_has_core_deps "$system_python"; then
      printf '%s\n' "$system_python"
      return 0
    fi

    echo "[python-env] creating repo-local virtual environment at $venv_dir" >&2
    "$system_python" -m venv "$venv_dir" >&2
    PIP_DISABLE_PIP_VERSION_CHECK=1 "$venv_python" -m pip install -r "$requirements_file" >&2
    printf '%s\n' "$venv_python"
    return 0
  fi

  echo "[python-env][FAIL] python3 is required but was not found on PATH" >&2
  return 1
}
