#!/bin/bash
# submission_freeze.sh - Canonical final validation pipeline for camera-ready artifact
# Usage:
#   ./scripts/submission_freeze.sh
#   ./scripts/submission_freeze.sh --skip-smoke

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CAMPAIGN="0.c0010"
SKIP_SMOKE=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --campaign)
      CAMPAIGN="$2"
      shift 2
      ;;
    --skip-smoke)
      SKIP_SMOKE=true
      shift
      ;;
    --help|-h)
      echo "Usage: ./scripts/submission_freeze.sh [--campaign ID] [--skip-smoke]"
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      exit 1
      ;;
  esac
done

cd "$ROOT_DIR"

ts="$(date +%Y%m%d_%H%M%S)"
report="release/submission_freeze_${ts}.md"

{
  echo "# Submission Freeze Report"
  echo ""
  echo "- Timestamp: $(date -Iseconds)"
  echo "- Smoke campaign: $CAMPAIGN"
  echo ""
} > "$report"

echo "[FREEZE] Running doctor checks..."
{
  echo "[doctor] checking dependencies..."
  command -v python3 >/dev/null
  echo "[doctor] checking canonical files..."
  test -f "$ROOT_DIR/scripts/run_campaign.py"
  test -f "$ROOT_DIR/scripts/collect_evidence.sh"
  test -f "$ROOT_DIR/scripts/generate_campaign_matrix.py"
  test -f "$ROOT_DIR/scripts/generate_paper_ready_artifacts.py"
  test -f "$ROOT_DIR/src/executors/fidelity_rubric.py"
  test -d "$ROOT_DIR/data/sut_profiles"
  test -d "$ROOT_DIR/campaigns"
  echo "[doctor] all checks passed"
} >/tmp/sticks_doctor_${ts}.log 2>&1
echo "- Doctor: PASS" >> "$report"

if [[ "$SKIP_SMOKE" == false ]]; then
  echo "[FREEZE] Running canonical smoke campaign: $CAMPAIGN"
  if python3 scripts/run_campaign.py --campaign "$CAMPAIGN" >/tmp/sticks_smoke_${ts}.log 2>&1; then
    echo "- Smoke campaign ($CAMPAIGN): PASS" >> "$report"
  else
    echo "- Smoke campaign ($CAMPAIGN): FAIL" >> "$report"
    echo "[FREEZE] Smoke campaign failed. See /tmp/sticks_smoke_${ts}.log" >&2
    exit 1
  fi
else
  echo "- Smoke campaign: SKIPPED" >> "$report"
fi

echo "[FREEZE] Refreshing fidelity artifacts..."
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" python3 src/executors/fidelity_rubric.py --all --latex --output release/fidelity_tables.tex >/tmp/sticks_fidelity_latex_${ts}.log 2>&1
PYTHONPATH="$ROOT_DIR/src${PYTHONPATH:+:$PYTHONPATH}" python3 src/executors/fidelity_rubric.py --all --json --output release/fidelity_report.json >/tmp/sticks_fidelity_json_${ts}.log 2>&1
echo "- Fidelity artifacts: refreshed" >> "$report"

echo "[FREEZE] Refreshing evidence matrix and paper-ready exports..."
./scripts/collect_evidence.sh >/tmp/sticks_collect_${ts}.log 2>&1
echo "- Matrix + paper-ready exports: refreshed" >> "$report"

echo "[FREEZE] Running sanitization dry-run..."
./scripts/sanitize_repo.sh >/tmp/sticks_sanitize_${ts}.log 2>&1
echo "- Sanitization dry-run: completed" >> "$report"

echo "" >> "$report"
echo "## Generated Artifacts" >> "$report"
echo "- release/campaign_sut_fidelity_matrix.json" >> "$report"
echo "- release/CAMPAIGN_SUT_FIDELITY_MATRIX.md" >> "$report"
echo "- release/fidelity_report.json" >> "$report"
echo "- release/fidelity_tables.tex" >> "$report"
echo "- release/paper_ready_macros.tex" >> "$report"
echo "- release/values.tex" >> "$report"
echo "- release/full_lab_status_table.tex" >> "$report"
echo "- release/CLAIM_EVIDENCE_TRACEABILITY.md" >> "$report"
echo "- release/CLAIMS_FOR_PAPER.md" >> "$report"
echo "" >> "$report"
echo "## Logs" >> "$report"
echo "- /tmp/sticks_doctor_${ts}.log" >> "$report"
echo "- /tmp/sticks_smoke_${ts}.log" >> "$report"
echo "- /tmp/sticks_fidelity_latex_${ts}.log" >> "$report"
echo "- /tmp/sticks_fidelity_json_${ts}.log" >> "$report"
echo "- /tmp/sticks_collect_${ts}.log" >> "$report"
echo "- /tmp/sticks_sanitize_${ts}.log" >> "$report"

echo "[FREEZE] Done: $report"
