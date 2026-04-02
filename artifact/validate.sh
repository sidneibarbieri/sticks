#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

latest_run_dir="$(python3 - <<'PY'
from pathlib import Path

candidates = list(Path("release/evidence").glob("0.c0011_*"))
if not candidates:
    print("")
else:
    latest = max(candidates, key=lambda path: path.name)
    print(latest)
PY
)"

if [[ -z "$latest_run_dir" ]]; then
  echo "[artifact/validate] missing evidence directory for 0.c0011" >&2
  exit 1
fi

latest_summary="$latest_run_dir/summary.json"
latest_manifest="$latest_run_dir/manifest.json"

if [[ ! -f "$latest_summary" ]]; then
  echo "[artifact/validate] missing summary for 0.c0011" >&2
  exit 1
fi

if [[ ! -f "$latest_manifest" ]]; then
  echo "[artifact/validate] missing manifest for 0.c0011" >&2
  exit 1
fi

for table_path in \
  results/tables/corpus_table.tex \
  results/tables/fidelity_table.tex \
  results/tables/execution_table.tex
do
  if [[ ! -f "$table_path" ]]; then
    echo "[artifact/validate] missing table: $table_path" >&2
    exit 1
  fi
done

python3 - <<'PY'
import json
from pathlib import Path

candidates = list(Path("release/evidence").glob("0.c0011_*"))
if not candidates:
    raise SystemExit("missing evidence directory for 0.c0011")

latest_dir = max(candidates, key=lambda path: path.name)
summary_path = latest_dir / "summary.json"
manifest_path = latest_dir / "manifest.json"

summary = json.loads(summary_path.read_text())
manifest = json.loads(manifest_path.read_text())

required_summary_keys = {"campaign_id", "technique_results"}
required_manifest_keys = {"campaign_id", "timestamp", "evidence_directory"}

missing_summary = sorted(required_summary_keys - set(summary))
missing_manifest = sorted(required_manifest_keys - set(manifest))

if missing_summary:
    raise SystemExit(f"missing summary keys: {missing_summary}")
if missing_manifest:
    raise SystemExit(f"missing manifest keys: {missing_manifest}")

print(f"[artifact/validate] summary: {summary_path}")
print(f"[artifact/validate] manifest: {manifest_path}")
print("[artifact/validate] json structure OK")
PY

echo "[artifact/validate] done"
