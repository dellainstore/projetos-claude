#!/bin/bash
# Restringe as portas 80/443 (nginx) para so aceitar conexoes vindas dos
# ranges oficiais do Cloudflare. Depois disso, ninguem mais consegue bater
# direto no IP da VPS (159.203.101.232) para acessar o site -- todo trafego
# tem que passar pelo Cloudflare (WAF, rate limit de borda, bot fight mode).
#
# Motivo (2026-08-21): confirmado que "curl -H 'Host: www.dellainstore.com'
# https://159.203.101.232/" respondia 200 direto, sem passar pelo Cloudflare.
# Um scanner (185.177.72.5) usou exatamente essa brecha pra fazer 1152
# requisicoes em 13 minutos varrendo wordlist de segredos expostos, sem ser
# filtrado pelo Cloudflare nem banido a tempo pelo fail2ban.
#
# SSH (porta 22, ou a porta customizada se ja tiver trocado) NAO e tocado.
#
# Rodar como root/sudo, de preferencia com sessao SSH ja aberta (nao via
# painel web) para poder corrigir na hora se algo sair errado:
#
#   sudo bash scripts/firewall_cloudflare_only.sh
#
# Ranges oficiais: https://www.cloudflare.com/ips-v4 e /ips-v6
# (mesma lista ja usada em /etc/nginx/conf.d/cloudflare-realip.conf --
# se o Cloudflare publicar mudanca de range, atualizar os dois arquivos)

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Rode como root (sudo bash $0)" >&2
  exit 1
fi

CF_V4=(
  173.245.48.0/20
  103.21.244.0/22
  103.22.200.0/22
  103.31.4.0/22
  141.101.64.0/18
  108.162.192.0/18
  190.93.240.0/20
  188.114.96.0/20
  197.234.240.0/22
  198.41.128.0/17
  162.158.0.0/15
  104.16.0.0/13
  104.24.0.0/14
  172.64.0.0/13
  131.0.72.0/22
)

CF_V6=(
  2400:cb00::/32
  2606:4700::/32
  2803:f800::/32
  2405:b500::/32
  2405:8100::/32
  2a06:98c0::/29
  2c0f:f248::/32
)

BACKUP="/root/ufw_status_antes_cloudflare_only_$(date +%Y%m%d_%H%M%S).txt"
echo "== Backup do estado atual do ufw em $BACKUP =="
ufw status verbose > "$BACKUP"
cat "$BACKUP"

echo
echo "== 1/3: liberando 80/443 para os ranges do Cloudflare (IPv4 + IPv6) =="
for r in "${CF_V4[@]}"; do
  ufw allow from "$r" to any port 80,443 proto tcp comment 'Cloudflare'
done
for r in "${CF_V6[@]}"; do
  ufw allow from "$r" to any port 80,443 proto tcp comment 'Cloudflare'
done

echo
echo "== 2/3: removendo as regras antigas que abriam 80/443 pra Anywhere =="
# Tenta remover nos formatos mais comuns; ignora se algum nao existir.
ufw delete allow 80/tcp    2>/dev/null || true
ufw delete allow 443/tcp   2>/dev/null || true
ufw delete allow 80        2>/dev/null || true
ufw delete allow 443       2>/dev/null || true
ufw delete allow 'Nginx Full'      2>/dev/null || true
ufw delete allow 'Nginx HTTP'      2>/dev/null || true
ufw delete allow 'Nginx HTTPS'     2>/dev/null || true
ufw delete allow 'Nginx Full (v6)' 2>/dev/null || true

echo
echo "== 3/3: estado final =="
ufw status verbose

echo
echo "Pronto. Confirme:"
echo "  1) O site continua no ar:      curl -sI https://www.dellainstore.com/healthz"
echo "  2) O IP direto agora NAO responde mais (deve dar timeout):"
echo "     curl -sk -m 5 -H 'Host: www.dellainstore.com' https://159.203.101.232/"
echo
echo "Se algo travar o acesso por engano, o backup das regras esta em:"
echo "  $BACKUP"
echo "e o SSH continua liberado normalmente para reverter."
