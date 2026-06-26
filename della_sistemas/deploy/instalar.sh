#!/bin/bash
# Script de instalação do D'ELLA Sistemas no VPS
# Rodar com: sudo bash deploy/instalar.sh

set -e
echo "=== Instalando D'ELLA Sistemas ==="

# 1. Copiar serviço systemd
cp /var/www/della-sistemas/projetos-claude/della_sistemas/deploy/della-sistemas.service \
   /etc/systemd/system/della-sistemas.service

# 2. Copiar configuração Nginx
cp /var/www/della-sistemas/projetos-claude/della_sistemas/deploy/della-sistemas.nginx \
   /etc/nginx/sites-available/della-sistemas

# 3. Ativar site no Nginx (se ainda não estiver ativo)
if [ ! -f /etc/nginx/sites-enabled/della-sistemas ]; then
    ln -s /etc/nginx/sites-available/della-sistemas /etc/nginx/sites-enabled/della-sistemas
fi

# 4. Diretório de logs (criado pelo systemd via RuntimeDirectory, mas logs extras aqui)
mkdir -p /home/neto/logs/della-sistemas
chown neto:neto /home/neto/logs/della-sistemas

# 5. Testar configuração Nginx
nginx -t

# 6. Recarregar nginx
systemctl reload nginx

# 7. Habilitar e iniciar serviço
systemctl daemon-reload
systemctl enable della-sistemas
systemctl start della-sistemas
systemctl status della-sistemas --no-pager

echo ""
echo "=== Instalação concluída! ==="
echo "Agora gere o SSL: sudo certbot --nginx -d sistemas.dellainstore.com"
