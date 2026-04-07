#!/usr/bin/env bash
# run_baseline.sh - Executa campanha baseline de forma reproduzível
# Uso: ./run_baseline.sh [campaign_id]
# Exemplo: ./run_baseline.sh 0.c0011

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

CAMPAIGN_ID="${1:-0.c0011}"

# Mapeia campaign_id para runner
if [[ "$CAMPAIGN_ID" == "0.c0011" ]]; then
    RUNNER="$SCRIPT_DIR/campaign_runner.py"
elif [[ "$CAMPAIGN_ID" == "0.pikabot_distribution_february_2024" ]]; then
    RUNNER="$SCRIPT_DIR/campaign_runner_0pikabot.py"
else
    echo "❌ Campanha não suportada: $CAMPAIGN_ID"
    echo "Campanhas disponíveis: 0.c0011, 0.pikabot_distribution_february_2024"
    exit 1
fi

echo "==================================================================="
echo "🚀 BASELINE LOCAL EXECUTION"
echo "==================================================================="
echo "Campaign: $CAMPAIGN_ID"
echo "Runner: $(basename "$RUNNER")"
echo "==================================================================="
echo ""

# Executa o runner
if [[ -f "$RUNNER" ]]; then
    python3 "$RUNNER"
else
    echo "❌ Runner não encontrado: $RUNNER"
    exit 1
fi

echo ""
echo "==================================================================="
echo "✅ Execução completa"
echo "Para inspecionar resultados: ./inspect_last_execution.sh $CAMPAIGN_ID"
echo "==================================================================="
