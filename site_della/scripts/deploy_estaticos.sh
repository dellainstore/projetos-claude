#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# deploy_estaticos.sh — Deploy rapido de mudancas de frontend (CSS / JS)
#
# Use este script SEMPRE que mexer em static/css/*, static/js/* ou em qualquer
# evento client-side (GA4 dellaTrackGA, Meta Pixel fbq). Faz os 3 passos que
# NUNCA podem ser separados:
#
#   1. npm run build:css   (gera static/css/tailwind.css)
#   2. collectstatic       (gera os hashes WhiteNoise em staticfiles/)
#   3. restart gunicorn     (recarrega o staticfiles.json em memoria)
#
# POR QUE OS 3 JUNTOS: o WhiteNoise (ManifestStaticFilesStorage) le o
# staticfiles.json UMA vez, no boot do worker. Se voce roda collectstatic mas
# nao reinicia, os workers seguem apontando para o hash ANTIGO do arquivo e o
# navegador recebe o JS velho. Foi exatamente assim que o evento GA4 add_to_cart
# (que vive SO no JS) ficou zerado mesmo estando no codigo: o collectstatic
# rodou, o restart nao, e a venda pegou o della.js anterior, sem o handler.
#
# Para deploy completo (com pip install + migrate), use atualizar_site.sh.
# Execute: bash scripts/deploy_estaticos.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
VENV="$PROJECT_DIR/venv/bin/activate"
SETTINGS="core.settings.production"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cd "$PROJECT_DIR"
source "$VENV"

echo ""
echo "══════════════════════════════════════════"
echo "  Della Instore — Deploy de estáticos     "
echo "══════════════════════════════════════════"
echo ""

echo -e "${YELLOW}[1/3]${NC} Buildando CSS (Tailwind)..."
npm run build:css
echo -e "${GREEN}[OK]${NC}"

echo -e "${YELLOW}[2/3]${NC} Coletando arquivos estáticos..."
python manage.py collectstatic --noinput --settings=$SETTINGS
echo -e "${GREEN}[OK]${NC}"

echo -e "${YELLOW}[3/3]${NC} Reiniciando Gunicorn (recarrega o manifest)..."
sudo systemctl restart gunicorn_della_site
sleep 2
if sudo systemctl is-active --quiet gunicorn_della_site; then
  echo -e "${GREEN}[OK]${NC} Gunicorn ativo"
else
  echo -e "${RED}[ERRO]${NC} Gunicorn não subiu — rode: sudo journalctl -u gunicorn_della_site -n 50"
  exit 1
fi

echo ""
echo -e "${GREEN}Estáticos atualizados. Confira o hash servido:${NC}"
echo "  curl -s https://www.dellainstore.com/ | grep -oE 'js/della\.[a-f0-9]+\.js'"
echo ""
