#!/usr/bin/env bash
# Single front door for reviewers. Every path below is one command; the Python
# environment is created and installed on first use. Nothing here needs a
# service to be started by hand.
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

usage() {
  cat <<'EOF'
STICKS -- one command per question.  Usage: bash run.sh <command> [options]

  command    what it establishes                                   time      needs
  ---------  ----------------------------------------------------  --------  ----------------------
  demo       one archived step across three arms                   1 s       python3 >= 3.11
  review     offline gate: regenerates every frozen record,        ~4 min    python3 >= 3.11
             checks every claim and hash, runs the test suite
  emulate    admit a campaign you choose (default C0045); planning 2 s       python3 >= 3.11
             only, nothing is executed
  doctor     read-only host check for the laboratory, printing     5 s       -
             the exact fix for anything that would stop it
  lab        brings up the whole laboratory (CALDERA, attacker,    5-60 min  Apple-silicon macOS
             target VMs), runs one campaign, observes the target   network-  (validated host), QEMU,
             independently, destroys the VMs, seals and verifies   bound     vagrant-qemu,
             the receipt                                                     socket_vmnet, network,
                                                                             25 GiB free
  workbench  local web interface to inspect admission              -         python3 >= 3.11
  all        demo + review + doctor + lab (C0026)                  10-65 min as for lab

Options:
  emulate [CAMPAIGN] [emulate.py options]
  lab [--campaign 0.c0026|0.c0010|0.costaricto] [--run-root /absolute/new/dir]
      Without --run-root the evidence goes to ~/sticks-runs/<campaign>-<UTC time>.

What the laboratory does NOT establish: historical replay, an enterprise
multi-host pivot, or support for arbitrary campaigns (see README, "Review and
live execution paths").
EOF
}

python_bin() {
  source "$ROOT_DIR/scripts/python_env.sh"
  sticks_resolve_python "$ROOT_DIR" "$ROOT_DIR/requirements.txt"
}

banner() { echo; echo "==> $*"; }

cmd_demo() { "$(python_bin)" scripts/demo.py; }
cmd_review() {
  local python
  python="$(python_bin)" || return 1
  "$python" scripts/doctor.py --path review || return 3
  STICKS_PYTHON="$python" bash run_review_check.sh
}
cmd_doctor() { "$(python_bin)" scripts/doctor.py --path "${1:-lab}"; }
cmd_workbench() { "$(python_bin)" scripts/run_realization_workbench.py --host 127.0.0.1 --port 8765; }

cmd_emulate() {
  local campaign="${1:-C0045}"
  [[ $# -gt 0 ]] && shift
  "$(python_bin)" scripts/emulate.py "$campaign" "$@"
}

cmd_lab() {
  local campaign="0.c0026" run_root=""
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --campaign|--run-root)
        if [[ $# -lt 2 || -z "${2:-}" || "${2:-}" == --* ]]; then
          echo "$1 requires a value; see bash run.sh help" >&2
          return 2
        fi
        if [[ "$1" == --campaign ]]; then campaign="$2"; else run_root="$2"; fi
        shift 2
        ;;
      *) echo "unknown lab option: $1" >&2; usage >&2; return 2 ;;
    esac
  done
  if [[ -z "$run_root" ]]; then
    run_root="$HOME/sticks-runs/${campaign#0.}-$(date -u +%Y%m%dT%H%M%SZ)"
    mkdir -p "$(dirname "$run_root")"
  fi
  local python child_status
  python="$(python_bin)" || return 2
  source "$ROOT_DIR/scripts/shell_lifecycle.sh"
  STICKS_PYTHON="$python" sticks_run_stage bash artifact/run.sh --campaign "$campaign" --run-root "$run_root"
  child_status=$?
  [[ "$STICKS_STOP_STATUS" -eq 0 ]] || return "$STICKS_STOP_STATUS"
  return "$child_status"
}

cmd_all() {
  local failed=()
  banner "demo";   cmd_demo   || failed+=(demo)
  banner "review"; cmd_review || failed+=(review)
  banner "doctor"; if cmd_doctor lab; then
    banner "lab (C0026)"; cmd_lab "$@" || failed+=(lab)
  else
    failed+=(doctor); echo "lab skipped: apply the fix printed above, then bash run.sh lab" >&2
  fi
  echo
  if [[ ${#failed[@]} -eq 0 ]]; then
    echo "==> all passed: demo, review, doctor, lab"
  else
    echo "==> failed: ${failed[*]}"; return 1
  fi
}

command="${1:-help}"
[[ $# -gt 0 ]] && shift
case "$command" in
  demo|review|emulate|doctor|lab|workbench|all) "cmd_$command" "$@" ;;
  help|-h|--help) usage ;;
  *) echo "unknown command: $command" >&2; usage >&2; exit 2 ;;
esac
