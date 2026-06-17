#!/bin/bash
# apply_bugfix_infra.sh — aplica as correções de infraestrutura do bugfix 2026-05-15
# Execute com: sudo bash scripts/apply_bugfix_infra.sh

set -e

echo "==> [1/4] Atualizando Gunicorn: 2 → 3 workers..."
sed -i 's/--workers 2 \\/--workers 3 \\/' /etc/systemd/system/gunicorn_della_site.service
grep "workers" /etc/systemd/system/gunicorn_della_site.service

echo "==> [2/4] Adicionando bloco PHP no Nginx..."
# Insere o bloco PHP antes do bloco de arquivos sensíveis
NGINX_CONF=/etc/nginx/sites-available/della_site
if grep -q "\.php\$" "$NGINX_CONF"; then
    echo "    Bloco PHP já existe, pulando."
else
    sed -i 's|    # ─── Bloqueia acesso a arquivos sensíveis|    # ─── Bloqueia bots PHP (scanners de vulnerabilidade) ─────────────────────\n    location ~* \\.php\\$ {\n        return 444;\n        access_log off;\n        log_not_found off;\n    }\n\n    # ─── Bloqueia acesso a arquivos sensíveis|' "$NGINX_CONF"
    echo "    Bloco PHP inserido."
fi

echo "==> [3/4] Recarregando systemd e reiniciando Gunicorn..."
systemctl daemon-reload
systemctl restart gunicorn_della_site
sleep 2
systemctl status gunicorn_della_site --no-pager | head -8

echo "==> [4/4] Testando e recarregando Nginx..."
nginx -t && systemctl reload nginx

echo ""
echo "==> Concluído! Verifique:"
echo "    sudo systemctl status gunicorn_della_site"
echo "    curl -s -o /dev/null -w '%{http_code}' https://www.dellainstore.com/test.php"
echo "    (deve retornar 0 ou conexão fechada — não 503)"
