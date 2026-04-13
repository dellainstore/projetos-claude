#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup_django.sh — Inicializa o Django após o banco estar no ar
# Execute: bash scripts/setup_django.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

source venv/bin/activate

echo ""
echo "══════════════════════════════════════════"
echo "  Della Instore — Setup Django            "
echo "══════════════════════════════════════════"
echo ""

echo -e "${YELLOW}[1/4]${NC} Aplicando migrations..."
python manage.py migrate
echo -e "${GREEN}[OK]${NC} Banco atualizado"

echo -e "${YELLOW}[2/4]${NC} Coletando arquivos estáticos..."
python manage.py collectstatic --noinput
echo -e "${GREEN}[OK]${NC} Static coletado"

echo -e "${YELLOW}[3/4]${NC} Criando superusuário admin..."
echo ""
python manage.py createsuperuser
echo -e "${GREEN}[OK]${NC} Superusuário criado"

echo -e "${YELLOW}[4/4]${NC} Verificação final..."
python manage.py check --deploy 2>&1 | grep -E "ERROR|WARNING|OK|issues"

echo ""
echo "══════════════════════════════════════════"
echo -e "${GREEN}Django pronto!${NC}"
echo ""
echo "Inicie o servidor de desenvolvimento:"
echo "  source venv/bin/activate"
echo "  python manage.py runserver 0.0.0.0:8000"
echo "══════════════════════════════════════════"
echo ""
