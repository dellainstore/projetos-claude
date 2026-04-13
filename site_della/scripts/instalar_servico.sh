#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# instalar_servico.sh — Instala Gunicorn como serviço e configura Nginx
# Execute: sudo bash scripts/instalar_servico.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo ""
echo "══════════════════════════════════════════════"
echo "  Della Instore — Instalação do Serviço       "
echo "══════════════════════════════════════════════"
echo ""

# 1. Garante que o diretório de logs existe com permissão certa
echo -e "${YELLOW}[1/5]${NC} Preparando diretórios..."
mkdir -p "$PROJECT_DIR/logs"
chown neto:www-data "$PROJECT_DIR/logs"
chmod 775 "$PROJECT_DIR/logs"

# Permissão para o Nginx ler os arquivos estáticos e media
chown -R neto:www-data "$PROJECT_DIR/staticfiles" 2>/dev/null || true
chown -R neto:www-data "$PROJECT_DIR/media"
chmod -R 755 "$PROJECT_DIR/staticfiles" 2>/dev/null || true
chmod -R 755 "$PROJECT_DIR/media"
echo -e "${GREEN}[OK]${NC} Diretórios configurados"

# 2. Instala o serviço Gunicorn
echo -e "${YELLOW}[2/5]${NC} Instalando serviço Gunicorn..."
cp "$SCRIPT_DIR/gunicorn_della_site.service" /etc/systemd/system/gunicorn_della_site.service
systemctl daemon-reload
systemctl enable gunicorn_della_site
systemctl start gunicorn_della_site
sleep 2
systemctl is-active gunicorn_della_site && echo -e "${GREEN}[OK]${NC} Gunicorn ativo" || echo "ERRO: Gunicorn não iniciou — verifique: journalctl -u gunicorn_della_site -n 30"

# 3. Instala config Nginx
echo -e "${YELLOW}[3/5]${NC} Configurando Nginx..."
cp "$SCRIPT_DIR/nginx_della_site.conf" /etc/nginx/sites-available/della_site

# Ativa o site (cria symlink)
ln -sf /etc/nginx/sites-available/della_site /etc/nginx/sites-enabled/della_site

# Testa a config antes de recarregar
nginx -t && echo -e "${GREEN}[OK]${NC} Nginx config válida" || { echo "ERRO na config do Nginx"; exit 1; }
systemctl reload nginx
echo -e "${GREEN}[OK]${NC} Nginx recarregado"

# 4. Gera certificado SSL com Certbot
echo ""
echo -e "${YELLOW}[4/5]${NC} Gerando SSL com Certbot..."
echo "Executando: certbot --nginx -d novo.dellainstore.com.br"
certbot --nginx -d novo.dellainstore.com.br
echo -e "${GREEN}[OK]${NC} SSL configurado"

# 5. Verifica tudo
echo -e "${YELLOW}[5/5]${NC} Verificação final..."
systemctl is-active gunicorn_della_site
systemctl is-active nginx

echo ""
echo "══════════════════════════════════════════════"
echo -e "${GREEN}Instalação concluída!${NC}"
echo ""
echo "Comandos úteis:"
echo "  sudo systemctl status gunicorn_della_site"
echo "  sudo systemctl restart gunicorn_della_site"
echo "  sudo journalctl -u gunicorn_della_site -f"
echo "  sudo nginx -t && sudo systemctl reload nginx"
echo "══════════════════════════════════════════════"
echo ""
