#!/usr/bin/env bash
# inspect_last_execution.sh - Inspeciona a execução mais recente de campanha
# Uso: ./inspect_last_execution.sh [campaign_id]
# Exemplo: ./inspect_last_execution.sh 0.c0011

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EVIDENCE_DIR="${SCRIPT_DIR}/../../data/campaign_evidence"

CAMPAIGN_ID="${1:-}"

if [[ -z "$CAMPAIGN_ID" ]]; then
    # Lista campanhas disponíveis
    echo "📁 Campanhas disponíveis:"
    find "$EVIDENCE_DIR" -maxdepth 1 -type d -name '*_*' | sort -t_ -k3,3 -k4,4 | tail -5 | while read -r dir; do
        basename "$dir"
    done
    echo ""
    echo "Uso: $0 <campaign_id>"
    echo "Exemplo: $0 0.c0011"
    exit 1
fi

# Encontra o diretório mais recente para a campanha
LATEST_DIR=$(find "$EVIDENCE_DIR" -maxdepth 1 -type d -name "${CAMPAIGN_ID}_*" | sort -t_ -k3,3 -k4,4 | tail -1)

if [[ -z "$LATEST_DIR" ]]; then
    echo "❌ Nenhuma evidência encontrada para campanha: $CAMPAIGN_ID"
    exit 1
fi

echo "==================================================================="
echo "📊 INSPEÇÃO DE EXECUÇÃO: $(basename "$LATEST_DIR")"
echo "==================================================================="
echo ""

# Valida estrutura
MANIFEST="$LATEST_DIR/manifest.json"
SUMMARY="$LATEST_DIR/summary.json"
PER_TECHNIQUE="$LATEST_DIR/per_technique"

if [[ ! -f "$MANIFEST" ]]; then
    echo "❌ manifest.json não encontrado"
    exit 1
fi

if [[ ! -f "$SUMMARY" ]]; then
    echo "❌ summary.json não encontrado"
    exit 1
fi

# Exibe resumo
python3 - <<PY
import json
import sys

with open("$SUMMARY") as f:
    data = json.load(f)

print(f"Campaign: {data['campaign_name']}")
print(f"Status: {data['status'].upper()}")
print(f"Técnicas: {data['successful_techniques']}/{data['total_techniques']} bem-sucedidas")
print(f"Duração: {data['execution_duration_seconds']:.1f}s")
print(f"Início: {data['start_time']}")
print("")

# Tabela de técnicas
print("📋 TÉCNICAS EXECUTADAS:")
print("-" * 70)
for t in data['manifest']['techniques']:
    icon = "✅" if t['status'] == 'success' else "❌"
    mode = t['execution_mode']
    print(f"{icon} {t['technique_id']:<12} ({mode:<18}) - {t['technique_name']}")
print("-" * 70)
PY

echo ""
echo "📁 Artefatos criados:"
python3 - <<PY
import json
with open("$MANIFEST") as f:
    data = json.load(f)
for artifact in data['artifacts_created'][:10]:
    print(f"  • {artifact}")
if len(data['artifacts_created']) > 10:
    print(f"  ... e mais {len(data['artifacts_created']) - 10} artefatos")
PY

echo ""
echo "📂 Diretório completo: $LATEST_DIR"
echo "==================================================================="
