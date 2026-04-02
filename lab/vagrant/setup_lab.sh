#!/bin/bash
# setup_lab.sh - Setup the STICKS testbed for ACM CCS artifact review
# Usage: ./setup_lab.sh [topology]
#   topology: baseline (default) | with-windows

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STICKS_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TOPOLOGY="${1:-baseline}"

echo "======================================================================"
echo "🚀 STICKS Artifact Setup - ACM CCS Review"
echo "======================================================================"
echo "Topology: $TOPOLOGY"
echo "======================================================================"

# Verificar dependências
check_dependency() {
    if ! command -v "$1" &> /dev/null; then
        echo "❌ $1 não encontrado. Instale $1 primeiro."
        exit 1
    fi
    echo "✅ $1 encontrado"
}

echo ""
echo "📋 Verificando dependências..."
check_dependency vagrant
check_dependency virtualbox
check_dependency python3

# Verificar recursos
echo ""
echo "💾 Verificando recursos..."
if [[ "$TOPOLOGY" == "with-windows" ]]; then
    REQUIRED_RAM=12  # GB
    echo "   Requer ~${REQUIRED_RAM}GB RAM (com Windows VM)"
else
    REQUIRED_RAM=8   # GB
    echo "   Requer ~${REQUIRED_RAM}GB RAM (baseline)"
fi

# Ir para diretório vagrant
cd "$SCRIPT_DIR"

# Destruir VMs antigas se existirem (clean slate)
echo ""
echo "🧹 Limpando ambiente anterior..."
vagrant destroy -f 2>/dev/null || true

# Subir VMs
echo ""
echo "🖥️  Subindo VMs..."
if [[ "$TOPOLOGY" == "with-windows" ]]; then
    SUT_TYPE=multi-host vagrant up
else
    vagrant up
fi

# Verificar status
echo ""
echo "🔍 Verificando status..."
vagrant status

echo ""
echo "======================================================================"
echo "✅ Setup completo!"
echo ""
echo "Próximos passos:"
echo "  1. Acesse Caldera: http://localhost:8888"
echo "  2. API Key RED: ADMIN123"
echo "  3. Execute campanha: cd .. && python3 -m data.abilities_registry.campaign_runner"
echo ""
echo "Para destruir o lab: vagrant destroy -f"
echo "======================================================================"
