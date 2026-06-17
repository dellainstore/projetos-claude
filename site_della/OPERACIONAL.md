# D'ELLA Instore — Operacional

Informações de operação do site (cron, agendamentos, prompts de continuidade). Contexto de desenvolvimento fica em [`CLAUDE.md`](CLAUDE.md).

---

## Cron jobs

| Quando | Comando / Script | O que faz |
|---|---|---|
| `0 * * * *` | `cancelar_pedidos_expirados` + `enviar_emails_carrinho_abandonado` | Cancela pedidos não pagos expirados e dispara e-mails de carrinho abandonado |
| `30 * * * *` | `rastrear_pedidos_correios` | Consulta Correios CWS — postagem muda status para `enviado`; entrega muda para `entregue` + e-mail |
| `*/15 * * * *` | `sincronizar_estoque_bling` | Sincroniza saldo do depósito Show Room para variações com `usa_sync_bling=True` |
| `0 */6 * * *` | `verificar_cache` | Verifica integridade dos caches (`MENU_CATEGORIAS`, `HOME_*`, etc.) |
| `0 2 * * *` | `scripts/backup_db.sh` | Backup do banco `della_site` para `onedrive:Della/Backups/site_della/` (retenção 30 dias) |
| `0 3 * * *` | `marcar_entrega_automatica` | Marca como `entregue` pedidos com 7+ dias após envio (fallback caso Correios não notifique) |
| `30 3 * * *` | `scripts/backup_codigo.sh` | Backup do código para `onedrive:Della/Backups/codigo/` (retenção 14 dias) |
| `0 9 * * *` | `scripts/enviar_lembrete_token.sh` | Lembrete (Brevo) 14 dias antes da expiração do token GitHub (`TOKEN_EXPIRY`) |
| `0 8 * * *` | `emitir_cupons_aniversario` *(adicionar quando criar template no admin)* | Emite cupons para aniversariantes do dia + envia e-mail. Sem template ativo (`origem=aniversario`), command sai cedo sem efeito. |

Management commands rodam com `--settings=core.settings.production`.

### Cron de aniversário — comando completo

```
0 8 * * * cd /var/www/della-sistemas/projetos-claude/site_della && ./venv/bin/python manage.py emitir_cupons_aniversario --settings=core.settings.production >> logs/cupons_aniversario.log 2>&1
```

Adicione no crontab (`crontab -e`) **depois** de criar o template no admin: Cupons → adicionar → `origem=aniversario`, `tipo=percentual`, `valor=15`, `dias_validade_pos_emissao=15`, `ativo=true`. Para testar antes de cadastrar o cron:

```
python manage.py emitir_cupons_aniversario --dry-run --settings=core.settings.production
python manage.py emitir_cupons_aniversario --data-base 2026-12-25 --dry-run --settings=core.settings.production
```

---

## Como Continuar numa Nova Conversa

Cole para o Claude:

```
Continuando o desenvolvimento do site Della Instore. Leia o arquivo
/var/www/della-sistemas/projetos-claude/site_della/CLAUDE.md e me aguarde
para o próximo ajuste.
```

Para tarefas operacionais (cron, deploy, backups), peça para ler também `OPERACIONAL.md`.

---

## Renovação do token GitHub

Token Fine-grained PAT — escopo Contents R+W em `dellainstore/projetos-claude`.

Quando o lembrete chegar (cron `0 9 * * *`, 14 dias antes):

1. Gerar novo PAT em GitHub → Settings → Developer settings → Fine-grained tokens
2. Atualizar `TOKEN_EXPIRY` em `scripts/enviar_lembrete_token.sh`
3. `git remote set-url origin https://dellainstore:NOVO_TOKEN@github.com/dellainstore/projetos-claude.git`

---

## Backups — restauração rápida

Backups ficam no OneDrive via rclone:

- Banco: `onedrive:Della/Backups/site_della/` (30 dias)
- Código: `onedrive:Della/Backups/codigo/` (14 dias)

Para restaurar, listar com `rclone ls onedrive:Della/Backups/...` e baixar com `rclone copy`.
