#!/bin/bash
# run_campaign.sh - Execute STICKS campaign with full evidence collection
# Usage: ./run_campaign.sh [campaign_id]
#   campaign_id: 0.c0011 (default) | 0.pikabot_distribution_february_2024

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STICKS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CAMPAIGN_ID="${1:-0.c0011}"

echo "======================================================================"
echo "🎯 STICKS Campaign Execution"
echo "======================================================================"
echo "Campaign: $CAMPAIGN_ID"
echo "======================================================================"

# Verificar Python
cd "$STICKS_ROOT"

# Executar campanha
echo ""
echo "🚀 Executando campanha..."
cd "$STICKS_ROOT/sticks/data/abilities_registry"

if [[ "$CAMPAIGN_ID" == "0.c0011" ]]; then
    python3 campaign_runner.py
elif [[ "$CAMPAIGN_ID" == "0.pikabot_distribution_february_2024" ]]; then
    python3 campaign_runner_0pikabot.py
else
    echo "❌ Campanha não suportada: $CAMPAIGN_ID"
    echo "Campanhas disponíveis:"
    echo "  - 0.c0011 (baseline Linux)"
    echo "  - 0.pikabot_distribution_february_2024 (requer Windows)"
    exit 1
fi

echo ""
echo "======================================================================"
echo "✅ Execução completa!"
echo ""
echo "Para inspecionar resultados:"
echo "  ./inspect_last_execution.sh $CAMPAIGN_ID"
echo "======================================================================"
