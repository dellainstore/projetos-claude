#!/bin/bash
# Envia e-mail lembrete de renovação do token GitHub via Brevo API.
# Roda diariamente via cron, mas só dispara o e-mail na data ALERT_DATE.
#
# Atualizar TOKEN_EXPIRY a cada renovação do token (acrescentar 90 dias).

set -e

# ─── CONFIG (atualizar a cada renovação do token) ─────────────────────────────
TOKEN_EXPIRY="2026-08-01"     # data de expiração do token atual
DAYS_BEFORE=14                 # quantos dias antes alertar
DESTINATARIO="neto.giacomelli@outlook.com"
NOME_DESTINATARIO="Neto"
LOG="/var/www/della-sistemas/projetos-claude/site_della/logs/lembrete_token.log"
# ──────────────────────────────────────────────────────────────────────────────

TODAY=$(date +%Y-%m-%d)
ALERT_DATE=$(date -d "$TOKEN_EXPIRY -$DAYS_BEFORE days" +%Y-%m-%d)

# Permite forçar via flag --force (para teste)
if [ "$1" != "--force" ] && [ "$TODAY" != "$ALERT_DATE" ]; then
    # Não é o dia — sai sem fazer nada
    exit 0
fi

BREVO_API_KEY=$(grep '^BREVO_API_KEY=' /var/www/della-sistemas/projetos-claude/site_della/.env | cut -d'=' -f2-)

if [ -z "$BREVO_API_KEY" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERRO: BREVO_API_KEY não encontrada no .env" >> "$LOG"
    exit 1
fi

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Disparando lembrete de renovação do token..." >> "$LOG"

# Corpo HTML do e-mail
HTML_BODY=$(cat <<'EOF'
<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Renovar token GitHub</title></head>
<body style="font-family: Arial, sans-serif; max-width: 640px; margin: 0 auto; color: #222; line-height: 1.5;">

<h2 style="color: #c9a96e;">🔐 Renovar token GitHub — Della Sistemas</h2>

<p>Oi Neto,</p>

<p>O token do GitHub que está configurado na <strong>VPS</strong> (usado para fazer <code>git push/pull</code> do repositório <code>dellainstore/projetos-claude</code>) <strong>vence em 14 dias (01/08/2026)</strong>.</p>

<p>Quando o token expirar, todo <code>git push</code> e <code>git fetch</code> da VPS vai falhar com erro de autenticação. Backup automático do código também para de funcionar.</p>

<p>Bloqueie 10 minutos para fazer agora. Passo a passo abaixo.</p>

<hr>

<h3>Passo a passo</h3>

<h4>1. Gerar token novo no GitHub</h4>
<ol>
  <li>Acesse <a href="https://github.com/settings/personal-access-tokens">github.com/settings/personal-access-tokens</a></li>
  <li>Clique em <strong>"Generate new token"</strong> (do tipo <strong>Fine-grained</strong>, não Classic)</li>
  <li>Preencha:
    <ul>
      <li><strong>Token name:</strong> <code>vps-della-sistemas</code></li>
      <li><strong>Expiration:</strong> 90 days</li>
      <li><strong>Repository access:</strong> Only select repositories → <code>dellainstore/projetos-claude</code></li>
      <li><strong>Permissions → Repository permissions:</strong>
        <ul>
          <li>Contents: <strong>Read and write</strong></li>
          <li>Metadata: Read-only (já vem marcado)</li>
          <li>Resto: No access</li>
        </ul>
      </li>
    </ul>
  </li>
  <li>Clique em <strong>"Generate token"</strong> e <strong>COPIE o token</strong> que aparece (começa com <code>github_pat_...</code>) — só aparece uma vez!</li>
</ol>

<h4>2. Substituir o token na VPS</h4>
<p>Conecte na VPS via SSH e rode (substituindo <code>SEU_NOVO_TOKEN</code>):</p>
<pre style="background: #f5f5f3; padding: 12px; border-left: 3px solid #c9a96e; overflow-x: auto;">
cd /var/www/della-sistemas/projetos-claude
git remote set-url origin https://dellainstore:SEU_NOVO_TOKEN@github.com/dellainstore/projetos-claude.git
git fetch origin
</pre>

<p>Se <code>git fetch</code> não der erro, deu certo.</p>

<h4>3. Atualizar a data no script de lembrete</h4>
<p>Edite o arquivo <code>/var/www/della-sistemas/projetos-claude/site_della/scripts/enviar_lembrete_token.sh</code> e altere a linha:</p>
<pre style="background: #f5f5f3; padding: 12px; border-left: 3px solid #c9a96e;">
TOKEN_EXPIRY="2026-08-01"
</pre>
<p>Para a nova data de expiração (90 dias depois de hoje). Se preguiça, pode rodar:</p>
<pre style="background: #f5f5f3; padding: 12px; border-left: 3px solid #c9a96e;">
NOVA_DATA=$(date -d "+90 days" +%Y-%m-%d)
sed -i "s/^TOKEN_EXPIRY=.*/TOKEN_EXPIRY=\"$NOVA_DATA\"/" /var/www/della-sistemas/projetos-claude/site_della/scripts/enviar_lembrete_token.sh
</pre>

<h4>4. Revogar o token antigo</h4>
<ol>
  <li>Volte em <a href="https://github.com/settings/personal-access-tokens">github.com/settings/personal-access-tokens</a></li>
  <li>Encontre o token velho (provavelmente <code>vps-della-sistemas</code> com data de criação ~03/05/2026)</li>
  <li>Clique nos <code>...</code> ao lado dele → <strong>"Revoke"</strong></li>
</ol>

<hr>

<h3>Em caso de dúvida</h3>
<p>Abra uma conversa nova com o Claude Code na VPS e cole essa instrução:</p>
<blockquote style="border-left: 3px solid #c9a96e; padding-left: 12px; color: #555;">
"Acabei de gerar um token novo no GitHub. Pode me ajudar a substituir o antigo na VPS e atualizar o script <code>enviar_lembrete_token.sh</code> com a nova data de expiração?"
</blockquote>

<hr>

<p style="color: #888; font-size: 12px;">
Este e-mail foi enviado automaticamente pelo cron da VPS Della Sistemas.<br>
Script: <code>site_della/scripts/enviar_lembrete_token.sh</code><br>
Para parar de receber: remova a entrada do crontab ou altere a TOKEN_EXPIRY no script.
</p>

</body></html>
EOF
)

# Escapar para JSON (newlines e quotes)
HTML_ESCAPED=$(echo "$HTML_BODY" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')

# Payload da Brevo API
PAYLOAD=$(cat <<EOF
{
  "sender": {"name": "Della Sistemas (VPS)", "email": "contato@dellainstore.com.br"},
  "to": [{"email": "$DESTINATARIO", "name": "$NOME_DESTINATARIO"}],
  "subject": "🔐 Renovar token GitHub — VPS Della (vence em 14 dias)",
  "htmlContent": $HTML_ESCAPED
}
EOF
)

# Envia via Brevo
RESPONSE=$(curl -s -w "\n%{http_code}" -X POST "https://api.brevo.com/v3/smtp/email" \
    -H "accept: application/json" \
    -H "api-key: $BREVO_API_KEY" \
    -H "content-type: application/json" \
    -d "$PAYLOAD")

HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" = "201" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] E-mail enviado com sucesso para $DESTINATARIO. Resposta: $BODY" >> "$LOG"
else
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERRO HTTP $HTTP_CODE: $BODY" >> "$LOG"
    exit 1
fi
