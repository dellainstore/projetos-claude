# D'ELLA Instore — Site E-commerce
**Quick start. Histórico completo em [`CLAUDE_BACKUP_2026-05-05.md`](CLAUDE_BACKUP_2026-05-05.md)**

| | |
|---|---|
| Stack | Django 5.1 + PostgreSQL + Gunicorn + Nginx |
| Frontend | HTML/CSS/JS + Tailwind local (`static/css/tailwind.css`) |
| VPS | `159.203.101.232` — `www.dellainstore.com` (PRODUÇÃO) |
| Redirecionamentos | `dellainstore.com`, `*.dellainstore.com.br` → `www.dellainstore.com` |
| Repositório | `dellainstore/projetos-claude` |
| Caminho | `/var/www/della-sistemas/projetos-claude/site_della/` |

---

## Ambiente e Deploy

```bash
cd /var/www/della-sistemas/projetos-claude/site_della
source venv/bin/activate
```

Banco: `della_site` / `della_user`

```bash
npm run build:css          # se mudou classes Tailwind (obrigatório antes do collectstatic)
python manage.py collectstatic --noinput --settings=core.settings.production
python manage.py makemigrations && python manage.py migrate --settings=core.settings.production
kill -HUP $(ps aux | grep gunicorn | grep della_site | grep -v grep | head -1 | awk '{print $2}')

# Restart completo:
sudo systemctl restart gunicorn_della_site && sudo nginx -t && sudo systemctl reload nginx

# Validar:
python manage.py check --settings=core.settings.production
```

Logs: `sudo journalctl -u gunicorn_della_site -f`

### Tailwind

- Build local (Node 20). Entrada: `static/src/tailwind.css` → Saída: `static/css/tailwind.css` (gitignored)
- Em dev: `npm run watch:css`
- ⚠️ Classes geradas dinamicamente em JS precisam estar no `safelist` do `tailwind.config.js`
- **NÃO restaurar CDN** — removido intencionalmente

### Backups automáticos (rclone OneDrive)

| Quando | Script | Destino | Retenção |
|---|---|---|---|
| 02:00 diário | `scripts/backup_db.sh` | `onedrive:Della/Backups/site_della/` | 30 dias |
| 03:30 diário | `scripts/backup_codigo.sh` | `onedrive:Della/Backups/codigo/` | 14 dias |

### Token GitHub (Fine-grained PAT)

- Expira: `2026-08-01`. Escopo: Contents R+W em `dellainstore/projetos-claude`
- Lembrete automático 14 dias antes via Brevo (`scripts/enviar_lembrete_token.sh`, cron 09:00)
- Renovar: atualizar `TOKEN_EXPIRY` no script + `git remote set-url origin https://dellainstore:NOVO_TOKEN@github.com/dellainstore/projetos-claude.git`

### Cron jobs

Tabela completa em [`OPERACIONAL.md`](OPERACIONAL.md).

**Sintaxe — usar `./venv/bin/python` direto, NÃO `source`:**
- `cron` roda em `/bin/sh` (dash) que **não conhece o comando `source`** — falha silenciosamente
- Forma correta: `cd /path/to/site && ./venv/bin/python manage.py <cmd> --settings=core.settings.production`
- Forma errada: `cd ... && source venv/bin/activate && python manage.py ...` (não cria log, comando nunca roda)

### Logs

- **Nginx access do site:** `/var/log/nginx/della_site_access.log` (não o padrão `/var/log/nginx/access.log`)
- **Nginx error:** `/var/log/nginx/error.log`
- **Gunicorn access/error:** `logs/gunicorn_access.log` / `logs/gunicorn_error.log`
- **Django ERRORs:** `logs/django_error.log` (rotativo 5MB × 3, level=ERROR)
- **Bling webhook:** `logs/bling_webhook.log` (rotativo 5MB × 3, level=INFO, logger `apps.bling`)
- **Cron stock sync:** `logs/sync_estoque_bling.log`

---

## Arquitetura — Service Layer (refatoração 2026-05-10, commit `b380669`)

A lógica de negócio do checkout foi extraída de `views.py` para serviços separados. Não alterar essa estrutura sem motivo.

### `apps/pedidos/services/checkout.py`

| Símbolo | Tipo | Responsabilidade |
|---|---|---|
| `EstoqueInsuficiente` | Exception | Levantada dentro de `transaction.atomic()` — faz rollback automático do pedido |
| `ResultadoCalculo` | `@dataclass` | Retorno tipado do calculador: `subtotal`, `desconto`, `frete`, `total`, `cupom_obj`, `vendedor_obj` |
| `CalculadorPedido.calcular()` | Classe | Valida cupom, busca vendedor, calcula total. Chamada em `_processar_checkout()` |
| `criar_itens_pedido(pedido, cart)` | Função | Cria `ItemPedido` + decrementa estoque com `select_for_update()`. Deve estar dentro de `transaction.atomic()` |

### `apps/pedidos/carrinho.py` — `calcular_qtd_disponivel()`

```python
def calcular_qtd_disponivel(variacao, qtd_desejada, qtd_no_carrinho=0):
    """Centraliza a regra de limite de estoque para adicionar e atualizar carrinho."""
```

- `pronta_entrega`: limita a `min(qtd_desejada, estoque - qtd_no_carrinho)`
- `sob_demanda`: sem limite, retorna `qtd_desejada`
- Usada em `adicionar_ao_carrinho` (views.py) e `atualizar_carrinho` (views.py)

### Lógica que permanece em `views.py`

`_processar_checkout()` ainda orquestra: extrair form → chamar `CalculadorPedido` → criar pedido → chamar `criar_itens_pedido` → PagSeguro/PIX → e-mail → Bling → Meta CAPI.

---

## Estrutura de Apps

Pastas em `apps/`:

| App | Responsabilidade |
|---|---|
| `bling/` | Integração com Bling ERP — OAuth, tokens, sync de pedidos/produtos/estoque, webhooks, logs |
| `conteudo/` | Conteúdo editorial — banners da home, mini banners, look da semana, páginas estáticas, configuração da loja, Instagram |
| `core_utils/` | Utilitários compartilhados — cache helpers, sanitização, Meta CAPI, modo manutenção, template tags, admin views |
| `pagamentos/` | Gateways e meios de pagamento — PagBank/PagSeguro, PIX, cupons, carrinho abandonado, código de vendedor |
| `pedidos/` | Carrinho, checkout, pedidos, histórico, eventos de rastreio Correios e e-mails transacionais |
| `produtos/` | Catálogo — categorias, produtos, variações (cor/tamanho), fotos, tabela de medidas, avaliações, wishlist, newsletter |
| `usuarios/` | Cliente customizado (`AbstractBaseUser`), endereços e autenticação |

---

## Fluxo de Status do Pedido

| Status banco | Cliente vê | O que dispara |
|---|---|---|
| `aguardando_pagamento` | "Aguardando pagamento" | Checkout criado |
| `pagamento_confirmado` | **"Em separação"** | PagBank webhook PAID |
| `enviado` | "Enviado" + rastreio | Cron detecta postagem nos Correios |
| `entregue` | "Entregue" | Cron Correios ou 7 dias após envio |
| `cancelado` | Card vermelho | Bling `valor=2` ou admin |

- `status_publico` traduz `pagamento_confirmado` → "Em separação"
- Rastreio clicável: `https://www.linkcorreios.com.br/?id={codigo_rastreio}`
- Auto-entrega: `python manage.py marcar_entrega_automatica --settings=core.settings.production`

---

## E-mails Transacionais

`apps/pedidos/emails.py` + `templates/emails/*.html`

| Função | Quando |
|---|---|
| `enviar_confirmacao_pedido` | Checkout criado |
| `enviar_confirmacao_pagamento` | Status → `pagamento_confirmado` |
| `enviar_notificacao_envio` | Status → `enviado` |
| `enviar_cancelamento` | Status → `cancelado` |
| `enviar_confirmacao_entrega` | Status → `entregue` |
| `enviar_saiu_para_entrega` | Correios: saiu para entrega |
| `enviar_email_carrinho_abandonado` | Admin action / cron |

```bash
python manage.py enviar_emails_teste --email SEU@EMAIL --tipo saiu_entrega --settings=core.settings.production
```

---

## Integrações — Quirks Críticos

### Bling ERP
- Situação custom D'ELLA: `754756` (Em andamento - Site) — **NÃO** usar `6`
- **NÃO enviar `numero`** no payload — só `numeroLoja` (ex: `2026-0001`). Enviar `numero` causa colisão com pedidos antigos
- Webhook: usa `situacao.valor` (0/1/2/3). Só `valor=2` muda status → `cancelado`. "Atendido" Bling ≠ "Enviado" para o cliente
- Itens: formato `NOME (COR) (TAMANHO)`. Código = `item.sku` (não `bling_variacao_id`)
- Pagamento confirmado **NÃO** muda situação no Bling (avanço manual)
- HMAC do webhook validado por `BLING_CLIENT_SECRET` (não existe `BLING_WEBHOOK_SECRET` separado)

#### Sync de estoque Bling → Site (migration `0020`)

**Modelo `Variacao` — campos novos:**

| Campo | Tipo | Padrão | Descrição |
|---|---|---|---|
| `usa_sync_bling` | BooleanField | `False` | Ativa sync automático do estoque pelo Bling |
| `comportamento_sem_estoque` | CharField | `indisponivel` | O que fazer quando estoque zera: `indisponivel` ou `sob_demanda` |

**Comportamento `comportamento_sem_estoque`:**
- `indisponivel` — variação some do site quando estoque = 0 (ex: bodys)
- `sob_demanda` — quando estoque = 0, cai automaticamente em modo sob demanda com `prazo_confeccao_dias` (ex: peças de couro). Requer `prazo_confeccao_dias` preenchido

**Properties atualizadas em `Variacao`:**
- `modo_efetivo` → `'pronta_entrega'` / `'sob_demanda'` / `'indisponivel'` (fonte da verdade)
- `pronta_entrega`, `sob_demanda`, `disponivel` derivam de `modo_efetivo`
- `disponibilidade_label` usa `sob_demanda` — funciona para sob demanda real e fallback

**Como o sync funciona:**
- API: `GET /estoques/saldos?idsProdutos[]={bling_variacao_id}` → `data[0].depositos[].saldoVirtual`
- Depósito: **Show Room - Della** (`BLING_DEPOSITO_ID=7521173180`) — somente este depósito
- `saldoVirtual` = físico − reservas de pedidos "Em andamento" (site + loja física)
- Pedidos "Em aberto" e "Cancelado" **não** reduzem `saldoVirtual` — o Bling já trata isso
- Pedidos "Atendido Londrina/Anacã" não afetam Show Room pois estão em outros depósitos

**Quando o sync dispara:**
1. **Webhook v1 (real, em produção)** — Bling envia em formato PLANO no root: `{eventId, event, data, version}`. Eventos `order.*` e `stock.*`. Sem validação HMAC (ações idempotentes; sync é fonte da verdade)
2. **Webhook v3 (preparado, ainda não disponível na conta)** — formato `{estrutura, data}` aninhado. HMAC obrigatório. Estruturas: `pedidoVenda`, `notaFiscal`, `estoque`
3. **Cron `0 * * * *`** — rede de segurança a cada hora: todas as variações com `usa_sync_bling=True`
4. **Pós-pedido site** — imediatamente após `enviar_pedido_bling()` criar pedido no Bling

**Webhook — formatos descobertos:**
- **Real (v1 plano):** `{"eventId":"...", "event":"order.created", "data":{...}, "version":"v1"}`
- **Aninhado (logs internos suporte Bling):** `{"event":{"event":"order.created", "data":{...}}}`. O handler aceita ambos por segurança
- **HMAC:** o Bling v1 ENVIA `X-Bling-Signature-256`, mas não validamos por enquanto (TODO futuro). v3 valida obrigatório
- **IPs do Bling AWS observados:** `34.193.190.53`, `98.85.207.13` (lista no painel Bling pode estar incompleta)
- **User-Agent:** `bling-webhook` — útil para grep nos logs nginx

**Bloqueio no admin (Variacao):**
- `VariacaoInlineForm` (`apps/produtos/forms.py`) marca o campo `estoque` como `readonly` quando `usa_sync_bling=True` na instância salva
- `clean()` do form força `estoque = instance.estoque` se o checkbox vier marcado no POST (impede burlar via dev tools)
- `static/admin/js/variacao_sync_lock.js` libera/bloqueia o campo dinamicamente conforme o checkbox (sem precisar salvar antes de editar)

**Sync automático ao ativar (`apps/bling/signals.py`):**
- Signal `pre_save` + `post_save` na `Variacao` detecta transição `usa_sync_bling: False → True`
- Quando ativa, dispara `sincronizar_estoque_bling([instance])` na hora — sem precisar esperar cron/webhook
- Falha silenciosa em log (warning) se Bling estiver fora do ar — cron pega depois
- Registrado via `BlingConfig.ready()` em `apps/bling/apps.py`

**Management commands:**
```bash
# Testar sem salvar
python manage.py sincronizar_estoque_bling --dry-run --settings=core.settings.production
# Sincronizar variações específicas
python manage.py sincronizar_estoque_bling --variacao-id 42 55 --settings=core.settings.production
# Listar depósitos com ID (requer escopo 'depositos' no OAuth)
python manage.py identificar_deposito_bling --settings=core.settings.production
```

**Configuração `.env`:**
```
BLING_DEPOSITO_ID=7521173180   # Show Room - Della (depósito padrão)
```

**Decisão:** `bling_variacao_id` em `Variacao` = cada tamanho/cor é um **produto separado** no Bling (não variação agrupada). O campo `bling_variacao_id` guarda o ID desse produto filho.

**NÃO regredir:**
- `BLING_DEPOSITO_ID` deve sempre ser o Show Room — nunca somar todos os depósitos
- Webhook de pedido físico: NÃO logar como warning quando `bling_id` não encontrado — é comportamento esperado para vendas físicas
- Webhook estoque: usar a API como fonte da verdade (`sincronizar_estoque_bling(variacoes)`), NÃO confiar no payload do webhook diretamente — o payload do Bling pode ser parcial dependendo do evento
- Webhook v1: aceitar formato PLANO (real) E aninhado (logs suporte) — não simplificar para um só
- Logger `apps.bling`: deve ter handler `file_bling` em `core/settings/production.py` apontando para `logs/bling_webhook.log` — sem ele os `logger.info` do webhook somem (todo handler de produção é específico, não tem catch-all)

### PagSeguro (PagBank) — PRODUÇÃO (`PAGSEGURO_SANDBOX=False`)
- Estorno: `POST /charges/{charge_id}/cancel` com `{"amount": {"value": <centavos>}}` — **sem body retorna `40002`**
- Webhook reconsulta `GET /orders/{id}` autenticado antes de atualizar pedido (segurança)

### Correios CWS
- CNPJ: `29049870000137`. JWT cacheado (`correios_jwt_token`)
- Cron (`:30`): detecta postagem → muda para `enviado`; detecta entrega → muda status + e-mail
- Testar: `python manage.py rastrear_pedidos_correios --dry-run --settings=core.settings.production`

### Melhor Envio
- Webhook ME não dispara para etiquetas geradas via Bling (app diferente). Fallback = cron 7 dias
- Ajuste operacional: `+1 dia prazo, +R$3,00 preço` em toda opção

### Brevo
- `DEFAULT_FROM_EMAIL = "D'ELLA Instore <contato@dellainstore.com.br>"`
- `bcc=['financeiro@dellainstore.com.br']` em novos pedidos. Plano Free: 300/dia

### Meta Pixel / CAPI
- Snippet **NÃO** no HTML — injetado por JS só se `consent.marketing === true` (LGPD)
- CAPI ativa: `apps/core_utils/meta.py`. Feed catálogo: `/feed-meta.xml`

### GA4
- Carrega só quando `della_consent.analytics === true`
- **Bug corrigido**: chave do cookie é `analytics` (não `analise`) — verificar em `della.js → salvarConsent()`

---

## Decisões — NÃO Regredir

- **Logo D'ELLA = imagem** `static/images/brand/logo-della.webp` — não usar texto tipografado
- **Tailwind = build local, NÃO CDN** — sempre `npm run build:css` antes de `collectstatic`
- **Meta Pixel: NÃO no HTML** — sempre JS condicional (LGPD)
- **Estoque oficial = `Variacao.estoque` local** — importador Bling não sincroniza estoque automático (sync seletivo via `usa_sync_bling=True` por variação)
- **CEP endpoint** `/carrinho/cep/{cep}/` retorna `cidade`/`estado` — não `localidade`/`uf` da ViaCEP
- **`item.variacao_desc`** (snapshot histórico) — nunca `item.variacao.get_tipo_display`/`.nome`
- **Categoria pai inativa → subs inativam** (cascata em `Categoria.save()`)
- **`value` no admin = `ModelChoiceIteratorValue`** — sempre `int(str(value))`, não `int(value)`
- **Font Awesome 6 Free**: `fas` maioria; `far` só para heart/user/star/circle-check/circle-xmark
- **Cache-busting via WhiteNoise hash** — qualquer mudança CSS/JS requer `collectstatic` + HUP
- **CSRF token = meta tag, NÃO só cookie** — `<meta name="csrf-token" content="{{ csrf_token }}">` está no `<head>` de `base.html`. Todo JS que faz POST deve ler: `document.querySelector('meta[name="csrf-token"]')?.content || document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ''`. Motivo: quando o browser serve a página do cache (sem novo GET ao servidor), o cookie pode estar desincronizado → 403 silencioso. `della.js` e `produto-detalhe.js` já usam esse padrão.
- **Seleção de variação obrigatória — feedback visual** — ao clicar "Adicionar ao carrinho" sem selecionar tamanho/cor, o JS adiciona `.selecao-obrigatoria` ao `.produto-variacoes` correspondente, disparando animação de tremida + outline vermelho (keyframe `della-shake` em `static/css/della.css`). O void reflow entre `classList.remove / add` é intencional para reiniciar a animação.
- **`imagem_hover` NÃO faz fallback** para 2ª foto de cor diferente — retornar `None`
- **`.hero-mute-btn` tem `display:flex`** — manter `.hero-mute-btn[hidden] { display:none !important; }`
- **Zoom: NÃO criar wrapper `div`** dentro de `.galeria-principal` — usar o container diretamente
- **Zoom: NÃO ativar sobre `.galeria-nav`** — verificar `e.target.closest('.galeria-nav')`
- **Scroll durante drag admin: `wheel` + `rAF`** — drag nativo bloqueia scroll padrão
- **`MAX_UPLOAD_SIZE_MB = 15`** — NÃO baixar para 5 MB (fotos sumiram silenciosamente)
- **Erros inline de fotos são invisíveis** (`display:none !important`) — novas validações server-side precisam de contrapartida client-side em `produto_admin_por_cor.js`
- **`PedidoAdmin.get_actions`**: preservar `delete_selected` + todas as actions — filtrar só `delete_selected` quebra as actions custom
- **Cookie banner mobile**: `flex: 0 0 auto !important` no texto/ações (evita bug flex-grow)
- **Newsletter popup suprimido** enquanto cookie banner visível
- **Hero altura**: `calc(98svh - var(--navbar-total))` — não alterar
- **Mini banners**: `aspect-ratio: 3/4` + `max-height: 80vh` + `background-position: center top`

---

## Admin — Padrão

- Coluna `acoes_linha` (Editar/Excluir) com classes `della-btn-edit` / `della-btn-delete` — referência: qualquer `ModelAdmin` em `apps/*/admin.py`
- `Media.js = ('admin/js/admin_linhas.js',)` no admin que usar o padrão
- Nunca estilos inline nos botões — sempre as classes acima
- Todo admin que afeta cache deve implementar `save_model`/`delete_model` chamando `cache_utils.py`
- Após mudar CSS/JS do admin: `collectstatic` + HUP

---

## Cache

Helper: `apps/core_utils/cache_utils.py`. Nunca hardcodar chaves.

| Chave | TTL |
|---|---|
| `MENU_CATEGORIAS` | 4h |
| `HOME_BANNERS`, `HOME_MINI_BANNERS`, `HOME_LOOK` | 1h |
| `HOME_DESTAQUES` | 2h |
| `HOME_DEPOIMENTOS` | 6h |
| `LOJA_CONFIG` | 24h |
| `pagina_estatica_{slug}` | 6h |
| `produtos_relacionados_{cat_id}` | 3h |
| `tabela_medidas_{cat_id}` | 12h |

---

## Pendências Ativas

| Item | Observação |
|---|---|
| **Google Search Console** | Verificar propriedade `https://www.dellainstore.com` via GA4 |
| **Meta Business** | Verificar domínio `dellainstore.com` — meta tag já está no `base.html` |
| **Webhooks Bling v1** | Implementado e funcionando (formato plano). Sync em segundos. Logs: `logs/bling_webhook.log` |
| **Testar rastreio Correios** | Validar cron com pedido real. `--dry-run` disponível |
| **Webhook Stone HMAC** | Quando ativar Stone |
| **Remover `style-src 'unsafe-inline'`** | Exige migrar 525+ `style="..."`. Avaliar `nonce` |
| **[PENDENTE] Sync Fotos Drive ↔ Site** | Ver seção abaixo |

### [PENDENTE] Sync Fotos Drive ↔ Site

**Objetivo:** Gerenciar fotos dos produtos no Google Drive e sincronizar com o site.

**Estrutura criada no Drive (2026-05-09):**
```
Projetos Claude/
└── FOTOS SITE/
    ├── BODY ADRIANA/
    │   ├── PRETO/
    │   ├── MARROM/
    │   └── MARINHO/
    ├── BIQUINI FRANZIDO/
    │   ├── MARROM/
    │   ├── VERDE/
    │   └── PRETO/
    ... (68 produtos × N cores = ~170 pastas de cor)
```

**Workflow pretendido:**
1. Adicionar/substituir fotos diretamente nas pastas de cor no Drive
2. Rodar `python manage.py sync_fotos_drive` para importar para o site
3. O comando atualiza `ProdutoImagem` no banco automaticamente

**O que falta desenvolver:**

**Etapa A — Upload inicial (Site → Drive): [PENDENTE]**
- 317 fotos / 112 MB em `/media/produtos/` prontas para upload
- Manifest gerado em `/tmp/fotos_drive_manifest.json` com mapeamento `{produto, cor, produto_folder_id, file_path, filename}`
- Estrutura de pastas temporária criada em `/tmp/fotos_upload/` com as 315 fotos organizadas (exceto BODY VELUDO C/TULE — 2 fotos separadas)
- **Método definido:** usar MCP Google Drive (`mcp__claude_ai_Google_Drive__create_file` com `base64Content`) — rclone com service account não funciona (erro 403 `storageQuotaExceeded`; service account não tem cota no Drive pessoal)
- **IDs de subpastas de cor:** parcialmente coletados via `search_files` (continuar de onde parou)
- **BODY VELUDO C/TULE:** o "/" no nome quebra path local; tratar separadamente. Pasta MARSALA ID: `1TxdYweiFxYu4facALjukK8q8T3OCDeQF`

**Etapa B — Importação (Drive → Site):**
- Management command `sync_fotos_drive` que:
  - Lista arquivos em cada pasta produto/cor no Drive
  - Compara com `ProdutoImagem` existentes (por nome de arquivo ou hash)
  - Baixa arquivos novos/modificados para `/media/produtos/{slug}/`
  - Cria/atualiza registros `ProdutoImagem` no banco
  - Associa cor automaticamente pela pasta pai (ex: pasta `PRETO` → `CorPadrao.objects.get(nome='PRETO')`)
- Opção `--dry-run` para verificar sem salvar
- Logar resultados em `logs/sync_fotos_drive.log`

**IDs Drive (referência):**
- Pasta raiz FOTOS SITE: `1epmiXgDToKffzg5_R-B59wHYmYI_TI5G`
- Pasta pai Projetos Claude: `1vsu44CENG30PCXenBjoNEnOC_SXxls4f`

---

Histórico completo de bugs, auditorias e decisões: [`CLAUDE_BACKUP_2026-05-05.md`](CLAUDE_BACKUP_2026-05-05.md). Operação (cron, prompts de continuidade): [`OPERACIONAL.md`](OPERACIONAL.md).
