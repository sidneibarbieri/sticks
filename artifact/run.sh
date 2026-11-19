#!/usr/bin/env bash
# One typed laboratory cycle with scoped completion and receipt verification.
# Stop requests wait for the owned stage; incomplete metadata never certifies cleanup.
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'EOF'
Usage: bash artifact/run.sh --run-root /absolute/new/run [--campaign ID]
This command materializes infrastructure (QEMU virtual machines); --help only describes the path.

Campaigns with a typed laboratory contract:
  0.c0026      (default) dispatched through a freshly enrolled CALDERA agent
  0.c0010      dispatched through a freshly enrolled CALDERA agent
  0.costaricto dispatched through the STICKS laboratory transport
C0045 (ShadowRay) uses the strict effect-series runner; see README.

Stages: doctor -> fresh QEMU VMs -> campaign -> independent target observation
        -> teardown -> sealed receipt -> receipt verification (-> CALDERA journal check).
The run root must not exist and must be outside this source tree.
EOF
}

RUN_ROOT=""
CAMPAIGN="0.c0026"
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    --run-root|--campaign)
      if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == --* ]]; then
        echo "$1 requires a value; see bash artifact/run.sh --help" >&2
        exit 2
      fi
      if [[ "$1" == --campaign ]]; then CAMPAIGN="$2"; else RUN_ROOT="$2"; fi
      shift 2
      ;;
    *) usage >&2; exit 2 ;;
  esac
done
[[ -n "$RUN_ROOT" ]] || { usage >&2; exit 2; }

case "$CAMPAIGN" in
  0.c0026) COMPLETE=complete_c0026_run.py; DISPATCH=(--caldera-dispatch) ;;
  0.c0010) COMPLETE=complete_c0010_run.py; DISPATCH=(--caldera-dispatch) ;;
  0.costaricto) COMPLETE=complete_costaricto_run.py; DISPATCH=() ;;
  *) echo "[artifact/run] no typed laboratory contract for $CAMPAIGN" >&2; usage >&2; exit 2 ;;
esac

cd "$ROOT_DIR"
source "$ROOT_DIR/scripts/python_env.sh"
PYTHON_BIN="$(sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt")" || exit 2
# python_env.sh enables errexit; each stage status is handled explicitly below.
set +e
source "$ROOT_DIR/scripts/shell_lifecycle.sh"

stage() { echo; echo "[artifact/run] ($1/5) $2"; }

stage 1 "preflight"
sticks_run_stage "$PYTHON_BIN" scripts/doctor.py --path lab --run-root "$RUN_ROOT"
PREFLIGHT_STATUS=$?
[[ "$STICKS_STOP_STATUS" -eq 0 ]] || exit "$STICKS_STOP_STATUS"
if [[ "$PREFLIGHT_STATUS" -ne 0 ]]; then
  echo "[artifact/run] preflight failed; apply the printed fix and rerun. Nothing was created." >&2
  exit 3
fi

stage 2 "execute $CAMPAIGN in fresh QEMU guests"
sticks_run_stage "$PYTHON_BIN" scripts/run_isolated_lab_campaign.py --campaign "$CAMPAIGN" --provider qemu \
  --run-root "$RUN_ROOT" ${DISPATCH[@]+"${DISPATCH[@]}"} --keep-lab
RUN_STATUS=$?
if [[ $RUN_STATUS -ne 0 && ! -f "$RUN_ROOT/run_context.json" ]]; then
  if [[ -e "$RUN_ROOT" ]]; then
    echo "[artifact/run] incomplete run metadata (status $RUN_STATUS); inspect retained workspace $RUN_ROOT before recovery. Cleanup is not certified." >&2
  else
    echo "[artifact/run] the runner stopped without creating a run directory (status $RUN_STATUS)." >&2
  fi
  [[ "$STICKS_STOP_STATUS" -eq 0 ]] || exit "$STICKS_STOP_STATUS"
  exit "$RUN_STATUS"
fi
# A run context exists: completion must run even after a failed campaign so the
# guests are observed and destroyed and the failure is sealed, never discarded.

stage 3 "observe the target independently, tear down, seal"
sticks_run_cleanup_stage "$PYTHON_BIN" scripts/"$COMPLETE" --run-root "$RUN_ROOT"
COMPLETE_STATUS=$?

SEALED_RECEIPT="$RUN_ROOT/final_run_receipt.json"
JOURNAL_STATUS=0
if [[ -f "$SEALED_RECEIPT" ]]; then
  stage 4 "verify the sealed receipt"
  sticks_run_cleanup_stage "$PYTHON_BIN" scripts/finalize_isolated_lab_run.py --run-root "$RUN_ROOT" --verify
  VERIFY_STATUS=$?
else
  # An interrupted or failed run is retained but never sealed; there is nothing to verify.
  stage 4 "no sealed receipt: completion did not seal this run (see the messages above)"
  VERIFY_STATUS=1
fi

if [[ ! -f "$SEALED_RECEIPT" ]]; then
  stage 5 "CALDERA journal not verified because the run was not sealed"
elif [[ -f "$RUN_ROOT/evidence/caldera-session.json" ]]; then
  stage 5 "verify the CALDERA command journal"
  sticks_run_cleanup_stage "$PYTHON_BIN" scripts/verify_caldera_run_journal.py --evidence "$RUN_ROOT/evidence"
  JOURNAL_STATUS=$?
else
  stage 5 "no CALDERA journal for this transport"
fi

echo
echo "[artifact/run] $CAMPAIGN  run=$RUN_STATUS completion=$COMPLETE_STATUS receipt=$VERIFY_STATUS journal=$JOURNAL_STATUS stop=$STICKS_STOP_STATUS"
echo "[artifact/run] evidence retained at $RUN_ROOT"
[[ "$STICKS_STOP_STATUS" -eq 0 ]] || exit "$STICKS_STOP_STATUS"
for status in $RUN_STATUS $COMPLETE_STATUS $VERIFY_STATUS $JOURNAL_STATUS; do
  [[ $status -eq 0 ]] || exit 1
done
echo "[artifact/run] PASS: executed, observed, torn down, sealed and verified."
