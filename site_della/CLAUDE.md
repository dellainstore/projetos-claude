# D'ELLA Instore — Site E-commerce
**CLAUDE.md compacto — quick start. Histórico completo em [`CLAUDE_BACKUP_2026-04-28.md`](CLAUDE_BACKUP_2026-04-28.md)**

---

## Visão Geral

Loja virtual de moda feminina premium **D'ELLA Instore**.

| | |
|---|---|
| Stack | Django 5.1 + PostgreSQL + Gunicorn + Nginx |
| Frontend | HTML/CSS/JS + Tailwind CDN |
| VPS | `159.203.101.232` (Ubuntu, 1 vCore, 1.9GB RAM) |
| Domínio principal | `www.dellainstore.com` (HTTPS, Let's Encrypt — **PRODUÇÃO**) |
| Redirecionamentos | `dellainstore.com`, `www.dellainstore.com.br`, `dellainstore.com.br` → `www.dellainstore.com` |
| Domínio testes (removido) | `novo.dellainstore.com.br` (DNS deletado da UOL em 30/04/2026) |
| Repositório | `dellainstore/projetos-claude` |
| Localização | `/var/www/della-sistemas/projetos-claude/site_della/` |

---

## Ambiente

```bash
cd /var/www/della-sistemas/projetos-claude/site_della
source venv/bin/activate
```

Banco: `della_site` / `della_user`.

### Deploy / fluxo padrão após mudanças

```bash
# 1. Se mudou CLASSES TAILWIND em templates/JS, rebuilda o CSS:
npm run build:css      # gera static/css/tailwind.css (apenas classes usadas)

# 2. Após mudanças em CSS/JS (incl. tailwind rebuilt):
python manage.py collectstatic --noinput --settings=core.settings.production

# 3. Recarregar workers (sem sudo):
kill -HUP $(ps aux | grep gunicorn | grep della_site | grep -v grep | head -1 | awk '{print $2}')

# 4. Migrations:
python manage.py makemigrations
python manage.py migrate --settings=core.settings.production

# 5. Restart completo (settings.py / Nginx):
sudo systemctl restart gunicorn_della_site
sudo nginx -t && sudo systemctl reload nginx
```

Em desenvolvimento: `npm run watch:css` rebuilda o tailwind a cada save de template.

WhiteNoise gera hash no nome (`della.<hash>.css/js`) — qualquer mudança força browsers (incl. Safari iOS) a baixar versão nova.

### Tailwind — build local

- Tailwind v3 instalado via `npm` (Node 20). Config em `tailwind.config.js` (paths: `templates/**`, `apps/**/templates/**`, `static/js/**`, `static/admin/js/**`)
- Entrada: `static/src/tailwind.css` (apenas `@tailwind base/components/utilities`)
- Saída: `static/css/tailwind.css` (gerado, ~10KB minificado, **gitignored**)
- `<link rel="stylesheet" href="{% static 'css/tailwind.css' %}">` no `base.html` (sem CDN)
- ⚠️ **Esquecer `npm run build:css` antes do collectstatic** = classes novas não aparecem no CSS, estilo "some". Se isso acontecer, primeira coisa a verificar
- Classes geradas dinamicamente em JS (ex: `el.className = 'bg-' + cor`) não são detectadas pelo purge — adicionar ao `safelist` do `tailwind.config.js` se necessário

### Logs

```bash
sudo journalctl -u gunicorn_della_site -f
```

---

## Estrutura

```
site_della/
├── core/settings/{base,production,development}.py
├── apps/
│   ├── produtos/         # Categoria, Produto, Variacao, CorPadrao, TamanhoPadrao, ProdutoCorFoto, Avaliacao, TabelaMedidas
│   ├── conteudo/         # BannerPrincipal, MiniBanner, LookDaSemana, PaginaEstatica, InstagramPost
│   ├── pedidos/          # Pedido, ItemPedido, Cupom, CodigoVendedor, CarrinhoAbandonado
│   ├── pagamentos/       # PagSeguro, Stone, Pix
│   ├── bling/            # OAuth + integração ERP
│   ├── usuarios/         # Cliente (auth custom sem username), Endereco, Wishlist
│   └── core_utils/       # sanitize, cache_utils, templatetags
├── templates/{base,home,produtos,checkout,pedidos,usuarios,emails,admin}/
├── static/{css/della.css, js/della.js, admin/{css,js}/della_admin.*}
└── scripts/{atualizar_site.sh, gunicorn_della_site.service, nginx_della_site.conf}
```

---

## Models — campos críticos (resumo)

### `produtos`
- **Categoria**: `nome, slug, parent (FK self), ordem, ativa`. Dois níveis (mãe + filhas). Ao salvar, **se ativa muda no pai → propaga para todas as subs** (cascata em `Categoria.save()`).
- **Produto**: `categoria (FK), nome, slug, descricao, composicao, preco, preco_promocional, peso (gramas), bling_id, sku`. Nome salvo **uppercase**. Descrição/composição preservam quebras de linha.
- **CorPadrao**: `nome (único), codigo_hex, codigo_hex_secundario` (bolinha bicolor via conic-gradient).
- **TamanhoPadrao**: `nome, ordem`.
- **Variacao**: `produto, cor (FK), tamanho (FK), estoque, sku_variacao, bling_variacao_id, ativa, preco, preco_promocional, disponibilidade (imediata/sob_demanda), prazo_confeccao_dias`.
- **ProdutoImagem**: `produto, imagem (validada por magic bytes), alt, principal, ordem`. 1ª foto do strip = principal.
- **ProdutoCorFoto**: `produto, cor (FK), imagem (FK→ProdutoImagem)` — vincula foto a cor; ao clicar bolinha no site, galeria troca.

### `pedidos`
- **Pedido**: `numero (YYYY-NNNN sequencial), cliente, dados copiados, subtotal, desconto, frete, total, status, gateway, codigo_rastreio, bling_pedido_id, cupom (FK), codigo_vendedor (FK), frete_servico_id, frete_prazo_dias, observacao_interna`.
  - **Properties para painel cliente**: `status_publico` (display amigável: `pagamento_confirmado` → "Em separação"), `data_pago`/`data_envio`/`data_entrega`/`data_cancelamento` (lê primeiro `HistoricoPedido` do status), `pode_confirmar_entrega` (status='enviado'), `link_rastreio` (`https://www.linkcorreios.com.br/?id={codigo}`).
- **Cupom**: `codigo, tipo (percentual/fixo), valor, quantidade_total, vezes_usado, um_por_cliente, valido_de, valido_ate, ativo`. Métodos `esta_valido(cpf)` e `calcular_desconto(subtotal)`.
- **CodigoVendedor**: `codigo (manual), nome, ativo`.
- **CarrinhoAbandonado**: 1 por cliente (unique). `itens_json`, controle de envio de e-mail.

### `usuarios`
- **Cliente**: auth custom (e-mail como login, sem username), `nome, sobrenome, cpf, telefone, genero, precisa_ativar` (para clientes migrados do site antigo).

### `conteudo`
- **BannerPrincipal**: vídeo OU foto. Campos opcionais de texto removidos — banners agora são só visuais com `url_botao` clicável.
- **LookDaSemana**: foto + 3 pontos com FK Produto + FK ProdutoImagem (foto específica por ponto). Posições editadas por editor visual JS no admin.

---

## Admin — convenções obrigatórias

### Padrão para qualquer ModelAdmin novo

```python
class Media:
    js = ('admin/js/admin_linhas.js',)

def get_actions(self, request):
    actions = super().get_actions(request)
    return {k: v for k, v in actions.items() if k == 'delete_selected'}

def acoes_linha(self, obj):
    edit_url = reverse('admin:APP_MODEL_change', args=[obj.pk])
    delete_url = reverse('admin:APP_MODEL_delete', args=[obj.pk])
    return format_html(
        '<a href="{}" class="della-btn-edit">✎ Editar</a>'
        '<a href="{}" class="della-btn-delete" onclick="return confirm(\'Excluir?\')">✕ Excluir</a>',
        edit_url, delete_url,
    )
acoes_linha.short_description = 'Ações'
# Adicionar em list_display + list_display_links = ('<campo_link>',)
```

**NUNCA** estilos inline nos botões — sempre as classes `della-btn-edit` / `della-btn-delete`.

### Cache invalidation no admin

Todo admin que afeta conteúdo cacheado **deve** implementar `save_model` e `delete_model` chamando a função correspondente em `apps/core_utils/cache_utils.py` (`invalidar_categorias`, `invalidar_banners`, `invalidar_look`, `invalidar_pagina`, `invalidar_categoria_produtos`, etc).

### Tema do admin

- Visual customizado (preto + dourado, Playfair + Jost) em `static/admin/css/della_admin.css`
- Dark mode do Django **desabilitado** via override de `{% block dark-mode-vars %}` em `templates/admin/base_site.html`
- Sidebar sempre branca, scroll persistido em todas as páginas via `sessionStorage`
- Após mudar CSS do admin: `collectstatic` + HUP gunicorn

### Form de Produto — Categoria pai + Subcategoria

`apps/produtos/forms.py` tem:
- Widget `CategoriaSubSelect` que adiciona `data-parent` em cada `<option>` de subcategoria
- Form `ProdutoAdminForm` com campo virtual `categoria_pai` antes de `categoria` (relabel "Subcategoria")
- `ProdutoAdmin.formfield_for_foreignkey` aplica widget custom + queryset filtrado em `parent__isnull=False`

JS em `produto_admin.js → initCategoriaPaiFiltro()` filtra dinamicamente o dropdown.

⚠️ **Importante:** o admin passa `ModelChoiceIteratorValue` (não int) como `value` em `create_option`. Use `int(str(value))` — `int(value)` falha silenciosamente.

### Variações — bloco sticky

Faixa "VARIAÇÕES" + cabeçalho de colunas + scrollbar horizontal são sticky no viewport. Override em `templates/admin/edit_inline/tabular.html` move o `<h2>` para fora do `.tabular.inline-related`. JS constrói clone de thead em `.della-thead-clone-wrap`. **Bug crítico evitado:** `#variacoes-group .tabular.inline-related > fieldset.module { overflow: visible }` — sem isso aparece scrollbar dupla.

### Fotos do produto — card strip + foto por cor

- **Strip de cards** arrastáveis (`della-fotos-panel`) substitui tabela numérica
- 1ª foto na ordem = `principal=True` automaticamente no save
- Upload via "Escolher imagens" ou drag-and-drop sobre o strip
- **Foto por Cor**: botão câmera (`della-var-foto-btn`) na linha de variação abre picker visual. Modal tem botão "Remover vínculo" (vermelho) quando já existe vínculo
- Inline `fotos_por_cor-group` é oculto via CSS — vínculo gerenciado por JS, Django processa no save
- Backend: `ProdutoAdmin.save_related` salva imagens primeiro → resolve refs `pending:imagens-N` → salva fotos por cor

---

## Cache (FileBasedCache em `BASE_DIR/cache/`)

Helper centralizado: `apps/core_utils/cache_utils.py`. **Nunca hardcodar chaves** — sempre importar de lá.

| Chave | TTL | Invalidado por |
|---|---|---|
| `MENU_CATEGORIAS` | 4h | `CategoriaAdmin.save_model/delete_model` |
| `HOME_BANNERS`, `HOME_MINI_BANNERS`, `HOME_LOOK` | 1h | Admins respectivos |
| `HOME_DESTAQUES` | 2h | `ProdutoAdmin.save_model/delete_model` |
| `HOME_DEPOIMENTOS` | 6h | (expira sozinho) |
| `LOJA_CONFIG` | 24h | `ConfiguracaoLojaAdmin` |
| `pagina_estatica_{slug}` | 6h | `PaginaEstaticaAdmin` |
| `produtos_relacionados_{cat_id}` | 3h | ProdutoAdmin + CategoriaAdmin |
| `tabela_medidas_{cat_id}` | 12h | `CategoriaAdmin` |
| `pagseguro_public_key` | 1h | manual: `cache.delete('pagseguro_public_key')` |

Cron de verificação a cada 6h: `python manage.py verificar_cache --settings=core.settings.production` (compara com banco e remove órfãos).

---

## Integrações ativas — estado atual

### Bling ERP

- OAuth2 (token 1h, refresh 30 dias). Botões "Atualizar Token" / "Re-autorizar" no admin
- Webhook v3 com HMAC validado por `BLING_CLIENT_SECRET` (não existe `BLING_WEBHOOK_SECRET` separado)
- Pedido criado no checkout → situação `754756` (Em andamento - Site, custom D'ELLA, **não** `6` Em aberto)
- Pagamento confirmado **NÃO** muda situação no Bling (decisão de negócio: avanço operacional manual)
- Cancelamento → situação `12` (Cancelado) + restaura estoque
- Itens enviados como `NOME (COR) (TAMANHO)` ex: `BODY BASIC ANACA (BRANCO POLAR) (P)`. Código = `item.sku` (não `bling_variacao_id`)
- Payload inclui `produto.id` (= `bling_variacao_id`) para vincular ao catálogo Bling
- **`numero` NÃO enviado** — Bling auto-incrementa o sequencial interno (último = 9704). Só `numeroLoja` (= `pedido.numero` do site, ex: `2026-0001`) vai no payload, evitando colisão com pedidos antigos
- Transporte: `logistica: {nome: 'Melhor Envio - Correios'}`, dimensões caixa padrão D'ELLA (0.5kg, 17×8×28cm), `fretePorConta` automático
- Mapeamento vendedores: `VENDEDORES_BLING` em `services.py`. Padrão = Crislainy (`7616577942`)
- Observação interna fixa (dados bancários + Simples Nacional) em todo pedido
- PII redatada nos logs (`_redact_payload_pii`)
- `BlingLog.resposta` preserva `exc.data` em caso de erro (antes era `{}` — perdia `error.fields`)
- Falso warning "code 50 — mesma situação" (ao forçar Em andamento - Site após criação) é silenciado
- **Webhook Bling: usa `situacao.valor`** (categoria padrão Bling: 0=Em aberto, 1=Atendido, 2=Cancelado, 3=Em andamento) em vez de IDs específicos. Funciona com qualquer custom da loja. Apenas `valor=2` muda status do site para `cancelado` + restaura estoque. Outras transições (Atendido = NF/etiqueta) só capturam código de rastreio
- Management command: `limpar_bling_logs --dias 180`

### PagSeguro (PagBank)

- **Estado atual: PRODUÇÃO** (`PAGSEGURO_SANDBOX=False`) — Checkout Transparente liberado pelo suporte PagBank após envio dos logs mascarados
- Token de produção e sandbox no `.env`
- Endpoint público-key: `GET /public-keys/card` (não `/CREDIT_CARD` legado)
- SDK URL atualizada: `https://assets.pagseguro.com.br/checkout-sdk-js/rc/dist/browser/pagseguro.min.js`
- Cartão: tokenização frontend via `PagSeguro.encryptCard()` — PAN nunca toca servidor
- PIX dinâmico via `POST /orders` (com fallback para QR estático local se ACCESS_DENIED)
- Webhook reconsulta `GET /orders/{id}` autenticado antes de atualizar pedido (segurança contra forjamento)
- **Estorno automático**: `cancelar_pedido_pagseguro(pedido)` em `services/pagseguro.py` chama `POST /charges/{charge_id}/cancel` com body `{"amount": {"value": <centavos>}}` (mesmo para estorno total — sem body retorna 40002 invalid_parameter)
- Admin action **"⚠ Cancelar + Estornar PagBank (irreversível)"** com intermediate page de confirmação (`templates/admin/pedidos/confirmar_estorno.html`). Action "→ Cancelado" simples permanece pra casos sem estorno
- Logs de homologação em `projetos-claude/logs/pagseguro_*_masked.{json,txt}`. Script `scripts/mascarar_logs_pagseguro.py` mascara PII (nome/email/CPF/telefone/endereço/CEP) preservando JSON
- Comando de cartão `exportar_log_pagseguro_cartao` detecta ambiente automaticamente (antes era `'sandbox'` hardcoded)

### Melhor Envio

- `MELHOR_ENVIO_SANDBOX=False` (produção)
- CEP origem: `MELHOR_ENVIO_CEP_ORIGEM` (`04537070` Show Room)
- Caixa padrão: `DIMENSOES_PADRAO = {width:17, height:8, length:28, weight:0.5}` mas peso real soma `produto.peso × quantidade`
- `insurance_value: 0` (seguro removido para baratear)
- Ajuste operacional: `+1 dia prazo, +R$3,00 preço` em toda opção retornada
- Retry CEP 422: tenta `cep[:5] + '000'` se a API rejeitar
- IDs serviço: `'1'` = PAC, `'2'` = SEDEX (max_length=20 no field)

### Brevo (e-mail)

- `django-anymail[brevo]` via API HTTP (porta 443) — Digital Ocean bloqueia SMTP
- `BREVO_API_KEY` no `.env`. Domínio `dellainstore.com.br` autenticado (DKIM1, DKIM2, DMARC)
- `DEFAULT_FROM_EMAIL = "D'ELLA Instore <contato@dellainstore.com.br>"`
- Pedido novo: `bcc=['financeiro@dellainstore.com.br']` em `pedidos/emails.py`
- Plano Free: 300 e-mails/dia
- "via gy.d.sender-sib.com" no Outlook = Return-Path Brevo. Para remover precisa configurar Custom Return-Path no painel

### Google Analytics (GA4)

- `GA_MEASUREMENT_ID=G-ELSG6BRW0M` no `.env`
- Injetado condicionalmente em `templates/base.html` — só carrega quando `della_consent.analytics === true`
- Leitura do cookie via regex no `DOMContentLoaded` (mesmo timing que della.js seta `window.dellaConsent`)
- Evento `della:consent` escutado para carregar GA quando usuário aceita durante a visita
- CSP liberado em `core/settings/base.py`: `script-src`, `img-src` e `connect-src` com `www.googletagmanager.com`, `www.google-analytics.com`, `analytics.google.com`
- Troca de domínio futura: apenas atualizar a URL no painel GA — o `G-ELSG6BRW0M` permanece o mesmo
- **Bug corrigido**: chave do cookie é `analytics` (não `analise`). Verificar sempre em `static/js/della.js → salvarConsent()`

### Cookie Consent + Meta Pixel

**Cookie Consent (LGPD):**
- Banner fixo no rodapé com botões "Customizar" e "Aceitar tudo"
- Modal com 3 categorias (Necessários sempre on, Análise, Marketing) — toggles ligados por padrão ao abrir
- Cookie `della_consent` JSON (versionado) com validade 6 meses, `SameSite=Lax; Secure`
- Link "Preferências de Cookies" no rodapé reabre o modal
- Newsletter popup suprimido enquanto o cookie banner estiver visível
- ⚠️ Mobile: `flex: 0 0 auto !important` no texto/ações para evitar bug do flex-grow esticando vertical
- Evento global `della:consent` disparado em toda mudança

**Meta Pixel:** `META_PIXEL_ID=1626695288613433`
- Snippet **NÃO** está no HTML — `carregarMetaPixel()` em `della.js` injeta dinamicamente APENAS se `consent.marketing === true`
- Eventos: `PageView` (auto), `ViewContent` (produto), `AddToCart` (handler genérico), `InitiateCheckout` (checkout), `Purchase` (confirmação)
- Eventos custom via `<script type="application/json" data-meta-event="EventName">{...}</script>` nos templates → `dispararMetaEventosCustom()` lê e dispara
- `Purchase` usa deduplicação browser/server com `event_id = purchase_<numero_do_pedido>`; o front dispara uma vez por pedido via `sessionStorage`
- Conversion API ativa no backend para `ViewContent`, `AddToCart`, `InitiateCheckout` e `Purchase` via `apps/core_utils/meta.py`, respeitando `della_consent.marketing === true` e usando `META_CONVERSIONS_API_TOKEN`
- `ViewContent` e `InitiateCheckout` recebem `event_id` gerado no backend e reutilizado no browser; `AddToCart` gera o `event_id` no JS e envia o mesmo valor no AJAX para deduplicar com a CAPI
- Feed público do catálogo Meta em `/feed-meta.xml` com IDs iguais aos `content_ids` do Pixel (`produto.id`)
- Feed corrigido para Meta Commerce Manager: URLs de produto/imagem forçadas para `https` via `SITE_URL`, XML validado e `google_product_category` com caracteres escapados (`&amp;`, `&gt;`)
- `.env` de produção atualizado com `META_CONVERSIONS_API_TOKEN` e `META_GRAPH_API_VERSION=v19.0`
- Valores monetários sempre com `{% load l10n %}` + `|unlocalize` (ponto decimal); strings com `|escapejs`
- CSP libera `connect.facebook.net` (script-src) e `www.facebook.com` (img-src)
- Painel Meta: nenhuma "Categoria Especial" + "Correspondência avançada automática" ativa

**Validação do catálogo Meta (2026-04-28):**
- Importação manual no Commerce Manager concluída com `67` produtos, `0` falhas e `0` problemas
- Feed validado localmente com parser XML após correções
- URLs de imagem do feed respondem `200 OK` publicamente em `https://novo.dellainstore.com.br/media/...`
- Contagem local: `68` produtos ativos / `67` com imagem principal; o feed publica `67` itens
- Se as miniaturas não aparecerem imediatamente no Commerce Manager, a hipótese atual é atraso de processamento da Meta, não erro do feed
- Próxima checagem, se necessário: tela `Catálogo > Produtos` / detalhes do item / diagnósticos de mídia no Commerce Manager

### Instagram

- Posts importados via admin (System User token Meta Business, `INSTAGRAM_ACCESS_TOKEN`)
- Imagens baixadas localmente (`media/instagram/`) — sem dependência de URLs expiráveis do CDN
- Site exibe máx. 12 posts (2×6 grid edge-to-edge na home, sem gap)
- Vídeos usam `thumbnail_url` (não `media_url` que é .mp4)
- Botões no admin: "↻ Atualizar (últimos 30)" e "↓ Importar histórico completo" (desde 01/01/2025)

### E-mails transacionais — status completo

`apps/pedidos/emails.py` — funções disponíveis:

| Função | Quando | Template |
|---|---|---|
| `enviar_confirmacao_pedido(pedido)` | Checkout criado | `emails/confirmacao_pedido.html` |
| `enviar_confirmacao_pagamento(pedido)` | Status → `pagamento_confirmado` | `emails/pagamento_confirmado.html` |
| `enviar_notificacao_envio(pedido)` | Status → `enviado` | `emails/envio_rastreio.html` |
| `enviar_cancelamento(pedido, estornado=False)` | Status → `cancelado` | `emails/cancelamento_pedido.html` |
| `enviar_email_carrinho_abandonado(ca)` | Admin action / cron | `emails/carrinho_abandonado.html` |

Todas as transições de status do `PedidoAdmin._mudar_status` disparam o e-mail correspondente automaticamente. A action `cancelar_e_estornar_pagseguro` chama `enviar_cancelamento(..., estornado=True)`.

### PIX (chave própria, fallback)

- `PIX_CHAVE=29049870000137` (CNPJ)
- Usado como fallback quando PagBank retorna ACCESS_DENIED
- QR estático EMV com expiração de 10min (countdown na tela)

---

## Fluxo de status do pedido (cliente vs operação)

| Evento | Status banco | Cliente vê | Bling |
|---|---|---|---|
| Pedido criado, aguardando pagamento | `aguardando_pagamento` | "Aguardando pagamento" | (ainda não criado) |
| PagBank webhook PAID/AUTHORIZED | `pagamento_confirmado` | **"Em separação"** | `754756` Em andamento - Site |
| Operador embala/emite NF/etiqueta no Bling | inalterado | continua "Em separação" + rastreio aparece | "Atendido - Site" (custom, `valor=1`) |
| Operador posta nos Correios + clica "→ Enviado" no admin | `enviado` | "Enviado" + rastreio clicável | inalterado |
| Cliente clica "Confirmar entrega" OU 7 dias após envio (cron) | `entregue` | "Entregue" | inalterado |
| Bling cancela (qualquer custom com `valor=2`) OU "→ Cancelar + Estornar PagBank" | `cancelado` | Card vermelho "Pedido cancelado" | `12` Cancelado |

### Painel do cliente — `usuarios/detalhe_pedido.html`

- **Timeline horizontal** de 4 etapas (Pagamento ✓ → Em separação → Enviado → Entregue) com cores dourado=concluído, cinza=pendente, ícone+data por etapa. Mobile (≤600px) vira vertical empilhada
- **Rastreio clicável** → `https://www.linkcorreios.com.br/?id={codigo_rastreio}` em nova aba
- **Botão "Confirmar entrega"** aparece se `pedido.pode_confirmar_entrega` (status=enviado). View `confirmar_entrega` em `usuarios/views.py` muda status + cria `HistoricoPedido`
- **Status cancelado**: substitui timeline por card vermelho com data e mensagem sobre estorno automático
- **Bug histórico corrigido**: template usava `item.variacao.get_tipo_display`/`item.variacao.nome` (não existem) — agora usa `item.variacao_desc` (snapshot histórico)

### Auto-entrega após 7 dias

Management command: `python manage.py marcar_entrega_automatica --settings=core.settings.production` (suporta `--dias N` e `--dry-run`). Roda em cron diário sugerido às 03:00. Marca `enviado → entregue` quando `data_envio <= now - 7 dias` + cria `HistoricoPedido` com observação.

### Webhook Bling — comportamento atual

- Atualiza `codigo_rastreio` se vier no payload (`transporte.codigoRastreamento` ou `codigoRastreamento`)
- **Não muda status do site** para nenhuma outra transição (Em andamento → Atendido). Bling "Atendido" significa NF/etiqueta gerada, mas pedido pode ainda não ter sido postado nos Correios — o gatilho real de "Enviado" é a postagem (operador no admin)
- Apenas `valor=2` (Cancelado) muda status para `cancelado` + restaura estoque

---

## LGPD — segurança implementada

| Camada | O que faz |
|---|---|
| HTTPS + HSTS 1 ano + preload | Let's Encrypt, renovação automática via certbot.timer |
| Cookies | `Secure`, `HttpOnly` (sessionid), `SameSite=Lax` |
| Headers | X-Frame-Options DENY, X-Content-Type-Options nosniff, Referrer-Policy strict-origin-when-cross-origin, CSP restritivo |
| Cookie Consent | Banner LGPD com opt-in granular (necessário/análise/marketing) |
| `django-axes` | 5 tentativas → 1h lockout por IP+user |
| `django-csp` | CSP com domínios explícitos |
| Magic bytes | `validate_image_upload` em uploads de foto/vídeo |
| Webhooks | HMAC obrigatório (Bling) + reconsulta autenticada (PagBank) |
| IDOR | `_pode_acessar_pedido` em todas views de Pedido (pagamentos/views.py) |
| PII em logs | `_redact_payload_pii` em Bling — CPF/email/telefone/endereço viram `[REDACTED]` |
| Tokens admin | `access_token_mascarado`/`refresh_token_mascarado` no Bling admin |
| `bleach` | Sanitização de HTML em PaginaEstatica via `{{ ...|clean_html }}` |
| Upload limite | `client_max_body_size 50M` global; 500M só na rota de import de fotos ZIP |

---

## Modo Manutenção

Toggle em **Admin → Configurações da Loja → 🚧 Modo Manutenção**.

- Ativado: visitantes veem `templates/manutencao.html` (503). Admin (`/painel/`) e staff logado acessam normalmente
- Desativado: site funciona normalmente
- Cache de 30s — leva até 30 segundos para propagar após salvar
- Middleware: `apps/core_utils/maintenance.py → manutencao_middleware`
- Cache key: `MANUTENCAO_ATIVA` em `apps/core_utils/cache_utils.py`
- Registrado em `MIDDLEWARE` após `AuthenticationMiddleware` (precisa do user para checar `is_staff`)

### Nginx de produção

Config em `scripts/nginx_producao.conf`. Domínios e redirecionamentos:
- `http://*` → `https://www.dellainstore.com` (301)
- `https://dellainstore.com` → `https://www.dellainstore.com` (301)
- `https://www.dellainstore.com.br` → `https://www.dellainstore.com` (301)
- `https://dellainstore.com.br` → `https://www.dellainstore.com` (301)
- SSL: `/etc/letsencrypt/live/www.dellainstore.com/` (cobre todos os 4 domínios)

---

## Bugs corrigidos (sessão 2025-04-30)

- **Título duplicado no estorno**: `confirmar_estorno.html` agora tem `{% block content_title %}{% endblock %}` para suprimir o título automático do Django admin
- **Ativação de conta (`precisa_ativar`)**: ao ativar, zera `telefone` e deleta todos os `Endereco` do cliente. Redireciona para `editar_perfil` com aviso para atualizar dados antes de comprar
- **CEP — cidade e estado não puxavam**: bug de mismatch de nomes — backend retorna `cidade`/`estado`, mas o JS buscava `d.localidade`/`d.uf` (nomes da ViaCEP). Corrigido em `templates/usuarios/endereco_form.html`
- **CEP — auto-busca no blur**: campo CEP agora busca automaticamente ao sair do campo (tab / clique fora), sem precisar clicar na lupa
- **Estorno PIX PagBank**: `cancelar_pedido_pagseguro` agora detecta `qr_codes` com status `PAID` (PIX pago) e tenta cancelar via o ID do qr_code. Se não suportado, exibe mensagem clara orientando estorno manual no painel PagBank

## Decisões — NÃO regredir

- **Logo D'ELLA = imagem** (`static/images/brand/logo-della.webp`). NÃO usar texto tipografado pra "D'ELLA"
- **Coluna "Loja" do rodapé foi removida** — não restaurar. "Trocas" mora em "Ajuda"
- **Hero da home: altura `calc(98svh - var(--navbar-total))`** (quase tela cheia)
- **Mini banners: `aspect-ratio: 3/4` + `max-height: 80vh`** com `background-position: center top` (foto ancorada pelo topo)
- **Cookie consent é gate obrigatório** — qualquer tracking novo deve só carregar com `dellaConsent.marketing === true`
- **Meta Pixel snippet NÃO no HTML** — sempre injetado por JS condicional. Senão dispara sem consent (LGPD)
- **Estoque oficial = `Variacao.estoque` local** até saneamento do estoque no Bling. Importador Bling não sincroniza estoque automático
- **PIX dinâmico via PagBank** quando possível (fallback estático local). Webhook PagBank reconsulta `/orders/{id}` antes de atualizar
- **Bling: pedido criado fica em `Em andamento - Site` mesmo com pagamento confirmado** — avanço manual no painel Bling
- **Bling: situação custom D'ELLA `754756`**, NÃO usar `6` (Em aberto)
- **Bling: NÃO enviar `numero` no payload** — Bling auto-incrementa o sequencial interno. Enviar `numero=pedido.numero` (string `YYYY-NNNN`) causa colisão com pedidos antigos. Só `numeroLoja` vai no payload
- **Webhook Bling: usar `situacao.valor`** (categoria 0/1/2/3), NÃO IDs específicos. Apenas `valor=2` muda status do site. "Atendido" no Bling NÃO significa "Enviado" pro cliente — só captura rastreio
- **Itens no Bling: formato `NOME (COR) (TAMANHO)`** — não `NOME — Cor / Tam. X`
- **`item.sku` como `codigo` no Bling**, NÃO `bling_variacao_id` (que é ID interno)
- **`PedidoAdmin.get_actions`**: preservar `delete_selected` + todas em `self.actions`. Filtrar pra só `delete_selected` (template do CLAUDE.md) **quebra** as actions custom — esse padrão só vale pra admins simples sem actions próprias
- **PagBank estorno: `POST /charges/{id}/cancel` exige body** `{"amount": {"value": <centavos>}}` mesmo para estorno total. Sem body retorna `40002 invalid_parameter`
- **Templates de itens de pedido: usar `item.variacao_desc`**, NÃO `item.variacao.get_tipo_display`/`item.variacao.nome` (atributos inexistentes — Variação tem `cor` e `tamanho` como FKs). `variacao_desc` é snapshot histórico que sobrevive a alterações
- **Status cliente vs interno: `status_publico` traduz** `pagamento_confirmado` → "Em separação". Internamente granular pro admin; pro cliente, simplificado
- **Categoria pai inativa → todas subs inativam** (cascata no `Categoria.save()`)
- **Variável `value` no admin = `ModelChoiceIteratorValue`** — sempre `int(str(value))`, não `int(value)`
- **Font Awesome 6 Free**: `fas` para a maioria; `far` apenas para heart/user/star/circle-check/circle-xmark. NUNCA `fa-regular fa-X` se não existir variant grátis (vira retângulo vazio)
- **Cache-busting via WhiteNoise hash** — qualquer mudança em CSS/JS requer `collectstatic` + HUP
- **Tailwind = build local, NÃO CDN** — `cdn.tailwindcss.com` foi removido. Sempre `npm run build:css` antes de `collectstatic` se mudou classes em templates/JS. Não restaurar o `<script src="https://cdn.tailwindcss.com">` (perderia performance + voltaria dependência externa)
- **Cookie banner mobile**: `flex: 0 0 auto !important` no texto/ações (evita bug flex-grow esticando vertical)
- **Newsletter popup**: suprimido enquanto cookie banner visível (evita 2 popups sobrepostos)
- **GA4 — chave do consent é `analytics`** (não `analise`). Verificar em `della.js → salvarConsent()` se implementar outro tracking
- **GA4 — carregar no `DOMContentLoaded`**: della.js seta `window.dellaConsent` dentro do DOMContentLoaded — qualquer script que dependa disso deve usar o mesmo evento, não rodar inline imediatamente
- **CEP — endpoint `/carrinho/cep/{cep}/` retorna `cidade` e `estado`** (não `localidade`/`uf` da ViaCEP). Nunca usar os nomes ViaCEP diretamente no frontend

---

## Variáveis de ambiente (`.env`)

```
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=www.dellainstore.com,dellainstore.com,www.dellainstore.com.br,dellainstore.com.br,novo.dellainstore.com.br,159.203.101.232
DB_*=...
BREVO_API_KEY=...
PAGSEGURO_TOKEN=...           ← produção
PAGSEGURO_TOKEN_SANDBOX=...
PAGSEGURO_SANDBOX=False       ← PRODUÇÃO ativa
BLING_CLIENT_ID=...
BLING_CLIENT_SECRET=...        ← também usado para HMAC do webhook v3
BLING_REDIRECT_URI=https://www.dellainstore.com/bling/callback/
WHATSAPP_NUMBER_1=...
INSTAGRAM_ACCESS_TOKEN=...
INSTAGRAM_ACCOUNT_ID=...
MELHOR_ENVIO_TOKEN=...
MELHOR_ENVIO_SANDBOX=False
MELHOR_ENVIO_CEP_ORIGEM=04537070
PIX_CHAVE=29049870000137
SITE_URL=https://www.dellainstore.com
META_PIXEL_ID=1626695288613433
GA_MEASUREMENT_ID=G-ELSG6BRW0M
```

---

## Design system

| Token | Valor |
|---|---|
| Preto / Branco / Dourado | `#0a0a0a` / `#fafafa` / `#c9a96e` |
| Dourado claro / Cinza claro | `#e8d5b0` / `#f5f5f3` |
| Fonte títulos / corpo | `Playfair Display` / `Jost` |
| Navbar total height | `--navbar-total: 96px` (60 topo + 36 categorias) |
| Mobile (≤768px) | `--navbar-total = 60px` |
| Transição padrão | `all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94)` |

---

## Pendências

| Item | Observação |
|---|---|
| **Google Search Console** — verificar propriedade `https://www.dellainstore.com` via GA4 | Fazer quando abrir o site |
| **Meta Business** — verificar domínio `dellainstore.com` | Fazer quando abrir o site — meta tag já está no `base.html` e `manutencao.html` |
| **Estoque Bling → site** (sync automático) | Aguardar saneamento do estoque no Bling |
| **Polling automático tracking Correios** | Só fazer se o acompanhamento manual não bastar na prática |
| Webhook Stone HMAC (`X-Stone-Signature`) | Quando ativar Stone |
| Remover `'unsafe-inline'` do CSP (mover scripts inline para arquivos / nonce) | Melhoria futura — Tailwind já saiu do CDN, restam scripts GA4 e cleanup inline em `base.html` |
| LGPD — anonimização de pedidos > 5 anos (prazo fiscal) | Melhoria futura |
---

## Pendências resolvidas

| Item | |
|---|---|
| Migração para `www.dellainstore.com` (DNS + Nginx + certbot + .env) | ✅ |
| Modo manutenção com toggle no admin | ✅ |
| Bling reautorizado com novo domínio | ✅ |
| PagBank — webhook URL automático via `SITE_URL` | ✅ |
| GA4 — fluxo de dados atualizado para `www.dellainstore.com` | ✅ |
| Meta Commerce Manager — feed atualizado para `https://www.dellainstore.com/feed-meta.xml` | ✅ |
| Meta — API de Conversões (`ViewContent`, `AddToCart`, `InitiateCheckout`, `Purchase`) | ✅ |
| Meta — Catálogo de produtos (`/feed-meta.xml`) | ✅ |
| Google Analytics GA4 (`G-ELSG6BRW0M`) com consent | ✅ |
| Cron auto-entrega — `marcar_entrega_automatica` às 03:00 | ✅ |
| Backup diário pg_dump → OneDrive `Della/Backups/site_della/` às 02:00 | ✅ |
| Bug preview foto admin (usuário não-superuser) | ✅ |
| Bugs de CEP, estorno PIX, ativação de conta | ✅ |
| Remover registro `novo.dellainstore.com.br` do DNS da UOL | ✅ |
| Compilar Tailwind local (remove dependência do CDN; `cdn.tailwindcss.com` removido do CSP) | ✅ |

---

## Onde está o quê (atalho rápido)

| O que | Arquivo |
|---|---|
| JS principal do site | `static/js/della.js` |
| CSS principal do site | `static/css/della.css` |
| Tailwind config + entrada | `tailwind.config.js` + `static/src/tailwind.css` |
| Tailwind CSS gerado (gitignored) | `static/css/tailwind.css` (rodar `npm run build:css`) |
| JS admin de produto | `static/admin/js/produto_admin.js` |
| CSS admin | `static/admin/css/della_admin.css` |
| Form admin produto (CategoriaSubSelect, ProdutoCorFotoForm) | `apps/produtos/forms.py` |
| ProdutoAdmin (importação CSV/ZIP, exportar, save_related) | `apps/produtos/admin.py` |
| Bling services | `apps/bling/services.py` |
| Bling webhook (situacao.valor) | `apps/bling/views.py` (`_processar_webhook_pedido`) |
| PagSeguro services (estorno + chave + ordem) | `apps/pagamentos/services/pagseguro.py` |
| Melhor Envio | `apps/pagamentos/services/melhorenvio.py` |
| Cache utils | `apps/core_utils/cache_utils.py` |
| Sanitize / magic bytes | `apps/core_utils/sanitize.py` |
| Context processor (categorias, WhatsApp, META_PIXEL_ID, GA_MEASUREMENT_ID) | `apps/produtos/context_processors.py` |
| Settings produção (CSP, integrations) | `core/settings/{base,production}.py` |
| Storage WhiteNoise leniente | `core/storage.py` |
| Painel cliente — detalhe pedido (timeline) | `templates/usuarios/detalhe_pedido.html` |
| View confirmar entrega cliente | `apps/usuarios/views.py:confirmar_entrega` |
| Admin action estorno PagBank + intermediate | `apps/pedidos/admin.py:cancelar_e_estornar_pagseguro` + `templates/admin/pedidos/confirmar_estorno.html` |
| Mascarar PII em logs PagBank | `scripts/mascarar_logs_pagseguro.py` |
| Auto-entrega após 7 dias | `apps/pedidos/management/commands/marcar_entrega_automatica.py` |
| Middleware modo manutenção | `apps/core_utils/maintenance.py` |
| Template página manutenção | `templates/manutencao.html` |
| Toggle manutenção no admin | `Admin → Configurações da Loja → Modo manutenção` |

---

## Como Continuar numa Nova Conversa

```
"Continuando o desenvolvimento do site Della Instore. Leia o arquivo
/var/www/della-sistemas/projetos-claude/site_della/CLAUDE.md e me aguarde
para o próximo ajuste."
```

Se precisar de detalhe histórico de algum bug/auditoria/sessão antiga, consultar [`CLAUDE_BACKUP_2026-04-28.md`](CLAUDE_BACKUP_2026-04-28.md) (1886 linhas, todas as decisões e bugs documentados).
