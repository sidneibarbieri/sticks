#!/bin/bash
# artifact_up.sh - Legacy compatibility wrapper
#
# This script is kept only for backward compatibility.
# Canonical pipeline:
#   ./run_campaign.sh <campaign_id> [--provider ...]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

CAMPAIGN_ID=""
PROVIDER=""
DESTROY_AFTER=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --campaign)
            CAMPAIGN_ID="${2:-}"
            shift 2
            ;;
        --provider)
            PROVIDER="${2:-}"
            shift 2
            ;;
        --destroy)
            DESTROY_AFTER=true
            shift
            ;;
        --help|-h)
            echo "Legacy wrapper. Use: ./run_campaign.sh <campaign_id> [--provider ...]"
            exit 0
            ;;
        *)
            echo "[artifact_up.sh] Unknown option: $1" >&2
            exit 1
            ;;
    esac
done

if [[ -z "$CAMPAIGN_ID" ]]; then
    echo "[artifact_up.sh] Missing --campaign <id>" >&2
    echo "Use: ./run_campaign.sh <campaign_id>" >&2
    exit 1
fi

echo "[artifact_up.sh] DEPRECATED: delegating to canonical pipeline run_campaign.sh"
if [[ -n "$PROVIDER" ]]; then
    "$ROOT_DIR/run_campaign.sh" "$CAMPAIGN_ID" --provider "$PROVIDER"
else
    "$ROOT_DIR/run_campaign.sh" "$CAMPAIGN_ID"
fi

if [[ "$DESTROY_AFTER" == true ]]; then
    "$ROOT_DIR/destroy_lab.sh"
fi
