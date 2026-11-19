#!/usr/bin/env bash
# Keep the owning shell alive until its stage and scoped cleanup have finished.
STICKS_ACTIVE_CHILD=""
STICKS_STOP_STATUS=0
STICKS_STOP_SENT_TO=""

sticks_child_is_running() {
  local owned_pid
  for owned_pid in $(jobs -pr); do
    [[ "$owned_pid" == "$1" ]] && return 0
  done
  return 1
}

sticks_forward_stop() {
  if [[ -z "$STICKS_ACTIVE_CHILD" || "$STICKS_STOP_SENT_TO" == "$STICKS_ACTIVE_CHILD" ]]; then
    return 0
  fi
  if sticks_child_is_running "$STICKS_ACTIVE_CHILD"; then
    STICKS_STOP_SENT_TO="$STICKS_ACTIVE_CHILD"
    # Background Bash jobs can inherit SIGINT ignored; SIGTERM enters Python cleanup.
    if ! kill -TERM "$STICKS_ACTIVE_CHILD"; then
      echo "[lab-stop] could not forward stop to owned child $STICKS_ACTIVE_CHILD" >&2
    fi
  fi
}

sticks_request_stop() {
  if [[ "$STICKS_STOP_STATUS" -ne 0 ]]; then
    echo "[lab-stop] stop already recorded; no second signal forwarded" >&2
    return 0
  fi
  STICKS_STOP_STATUS="$1"
  echo "[lab-stop] stop requested; waiting for the owned stage and cleanup" >&2
  sticks_forward_stop
}

_sticks_run_child() {
  local allow_cleanup="$1" initial_stop="$STICKS_STOP_STATUS" child_status
  shift
  if [[ "$allow_cleanup" -eq 0 && "$initial_stop" -ne 0 ]]; then
    return "$initial_stop"
  fi
  STICKS_STOP_SENT_TO=""
  "$@" &
  STICKS_ACTIVE_CHILD=$!
  if [[ "$initial_stop" -eq 0 && "$STICKS_STOP_STATUS" -ne 0 ]]; then
    sticks_forward_stop
  fi
  while true; do
    if wait "$STICKS_ACTIVE_CHILD"; then child_status=0; else child_status=$?; fi
    sticks_child_is_running "$STICKS_ACTIVE_CHILD" || break
  done
  STICKS_ACTIVE_CHILD=""
  return "$child_status"
}

sticks_run_stage() { _sticks_run_child 0 "$@"; }
sticks_run_cleanup_stage() { _sticks_run_child 1 "$@"; }

trap 'sticks_request_stop 130' INT
trap 'sticks_request_stop 143' TERM
