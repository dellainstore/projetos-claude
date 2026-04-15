#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# atualizar_site.sh — Atualiza o site após alterações no código
# Execute: bash scripts/atualizar_site.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_DIR/venv/bin/activate"
SETTINGS="core.settings.production"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

cd "$PROJECT_DIR"
source "$VENV"

echo ""
echo "══════════════════════════════════════════"
echo "  Della Instore — Atualização do site     "
echo "══════════════════════════════════════════"
echo ""

echo -e "${YELLOW}[1/4]${NC} Instalando dependências..."
pip install -r requirements.txt --quiet
echo -e "${GREEN}[OK]${NC}"

echo -e "${YELLOW}[2/4]${NC} Aplicando migrations..."
python manage.py migrate --settings=$SETTINGS
echo -e "${GREEN}[OK]${NC}"

echo -e "${YELLOW}[3/4]${NC} Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --settings=$SETTINGS
echo -e "${GREEN}[OK]${NC}"

echo -e "${YELLOW}[4/4]${NC} Reiniciando Gunicorn..."
sudo systemctl restart gunicorn_della_site
sleep 2
sudo systemctl is-active gunicorn_della_site && echo -e "${GREEN}[OK]${NC} Gunicorn ativo" || echo "ERRO no Gunicorn"

echo ""
echo -e "${GREEN}Site atualizado com sucesso!${NC}"
echo ""
