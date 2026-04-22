# D'ELLA Instore — Site E-commerce Premium
**CLAUDE.md — Contexto completo para continuação do desenvolvimento**

---

## Visão Geral do Projeto

Loja virtual de moda feminina premium chamada **D'ELLA Instore**.
- **Stack:** Django 5.1 + PostgreSQL + Gunicorn + Nginx
- **Frontend:** HTML/CSS/JS com Tailwind CSS (CDN) + CSS customizado
- **VPS:** Ubuntu, 1 vCore, 1.9GB RAM, IP `159.203.101.232`
- **Domínio de testes (ativo):** `novo.dellainstore.com.br` — site no ar com HTTPS ✓
- **Domínio definitivo:** `www.dellainstore.com` — `.com.br` fará redirect 301 para o `.com`
- **Repositório:** `dellainstore/projetos-claude` no GitHub

---

## Localização do Projeto

```
/var/www/della-sistemas/projetos-claude/site_della/
```

### Estrutura de pastas principal
```
site_della/
├── core/
│   ├── settings/
│   │   ├── base.py          ← settings compartilhado
│   │   ├── production.py    ← HTTPS, HSTS, cookies seguros
│   │   └── development.py   ← debug, e-mail no console
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── produtos/            ← catálogo, categorias, variações, avaliações, CorPadrao, TamanhoPadrao
│   ├── conteudo/            ← BannerPrincipal, MiniBanner, LookDaSemana (uploads via admin)
│   ├── pedidos/             ← carrinho (sessão), checkout, pedidos
│   ├── pagamentos/          ← PagSeguro, Stone, Pix
│   ├── bling/               ← integração ERP Bling OAuth2
│   ├── usuarios/            ← Cliente (auth customizado), Endereço, Wishlist
│   └── core_utils/
│       └── sanitize.py      ← sanitizadores de input
├── templates/
│   ├── base.html            ← navbar 2 linhas (logo+ações / categorias), footer, drawer carrinho
│   ├── home/index.html      ← homepage: hero slider, destaques, mini banners, look, manifesto...
│   ├── produtos/            ← loja, detalhe, busca, wishlist
│   ├── pedidos/             ← carrinho
│   ├── checkout/            ← checkout, confirmação
│   ├── usuarios/            ← login, cadastro, minha conta, endereços, pedidos
│   ├── emails/              ← templates HTML de e-mails transacionais
│   └── admin/produtos/      ← importar.html, produto_changelist.html (customizações do admin)
├── static/
│   ├── css/della.css        ← todo CSS customizado da marca
│   └── js/della.js          ← JS principal
├── staticfiles/             ← arquivos coletados pelo collectstatic
├── media/                   ← uploads (banners/, mini-banners/, look-semana/, produtos/)
├── logs/                    ← logs do gunicorn
└── scripts/
    ├── instalar_servico.sh
    ├── atualizar_site.sh        ← atualiza após mudanças (migrations + collectstatic)
    ├── check_security.sh
    ├── gunicorn_della_site.service
    └── nginx_della_site.conf    ← client_max_body_size 50M (atualizar no /etc/nginx/ com sudo)
```

---

## Ambiente Virtual

```bash
cd /var/www/della-sistemas/projetos-claude/site_della
source venv/bin/activate
```

---

## Banco de Dados

- **Banco:** `della_site` | **Usuário:** `della_user`
- **Migrations aplicadas até:**
  - `produtos.0008_corpadrao_codigo_hex_secundario_produtocorfoto` (CorPadrao.codigo_hex_secundario + ProdutoCorFoto)
  - `conteudo.0007_paginaestatica_imagem_slugs` (PaginaEstatica.imagem + slug choices: perguntas_frequentes, meios_pagamento)
  - `pedidos.0004_codigovendedor_cupom_pedido_codigo_vendedor_str_and_more` (Cupom, CodigoVendedor, FK em Pedido)
  - `pedidos.0006_alter_pedido_frete_servico_id` — `frete_servico_id` max_length 10→20 (fix crash PIX checkout quando ID do serviço excedia o limite)

```bash
source venv/bin/activate
python manage.py makemigrations
python manage.py migrate --settings=core.settings.production
```

---

## Serviços em Produção

```bash
# Recarregar Gunicorn sem sudo (envia HUP ao processo master)
kill -HUP $(ps aux | grep gunicorn | grep -v grep | head -1 | awk '{print $2}')

# Reiniciar Gunicorn (requer sudo)
sudo systemctl restart gunicorn_della_site

# Coletar estáticos + reiniciar (fluxo completo)
bash scripts/atualizar_site.sh

# Logs em tempo real
sudo journalctl -u gunicorn_della_site -f

# Testar e recarregar Nginx
sudo nginx -t && sudo systemctl reload nginx
```

**Socket:** `/run/gunicorn_della_site/gunicorn.sock`
**Serviço:** `gunicorn_della_site` (systemd, usuário `neto`, 2 workers)

**`client_max_body_size 50M`** — ✅ aplicado em `/etc/nginx/sites-available/della_site`.

---

## Migração para www.dellainstore.com

**Domínio principal:** `www.dellainstore.com`
**Redirects 301 para o principal:** `dellainstore.com`, `www.dellainstore.com.br`, `dellainstore.com.br`

### Passo a passo (fazer quando DNS propagar):
1. No painel UOL, apontar **ambos os domínios** para o IP `159.203.101.232` (registro A):
   - `dellainstore.com` → `159.203.101.232`
   - `www.dellainstore.com` → `159.203.101.232`
   - `dellainstore.com.br` → `159.203.101.232`
   - `www.dellainstore.com.br` → `159.203.101.232`
2. Editar `/etc/nginx/sites-available/della_site` — substituir bloco "testes" pelo bloco definitivo:
   ```nginx
   # Domínio principal
   server {
       listen 443 ssl;
       server_name www.dellainstore.com;
       # ... configuração principal do site ...
   }
   # Redirects 301 → principal
   server {
       listen 80;
       server_name dellainstore.com www.dellainstore.com dellainstore.com.br www.dellainstore.com.br;
       return 301 https://www.dellainstore.com$request_uri;
   }
   server {
       listen 443 ssl;
       server_name dellainstore.com dellainstore.com.br www.dellainstore.com.br;
       return 301 https://www.dellainstore.com$request_uri;
   }
   ```
3. `sudo certbot --nginx -d www.dellainstore.com -d dellainstore.com -d www.dellainstore.com.br -d dellainstore.com.br`
4. Atualizar no `.env`:
   - `ALLOWED_HOSTS=www.dellainstore.com,dellainstore.com,www.dellainstore.com.br,dellainstore.com.br,159.203.101.232`
   - `SITE_URL=https://www.dellainstore.com`
   - `BLING_REDIRECT_URI=https://www.dellainstore.com/bling/callback/`
5. `sudo systemctl reload nginx && sudo systemctl restart gunicorn_della_site`

---

## Models Criados

### `apps/usuarios/`
| Model | Campos principais |
|---|---|
| `Cliente` | email (login), nome, sobrenome, cpf, telefone, genero — auth customizado sem username |
| `Endereco` | cep, logradouro, numero, complemento, bairro, cidade, estado, principal |
| `Wishlist` | cliente, produto |

### `apps/produtos/`
| Model | Campos principais |
|---|---|
| `Categoria` | nome, slug, descricao, imagem, **parent** (FK para si mesmo — subcategorias), ordem, ativa |
| `Produto` | categoria, nome, slug, descricao, composicao, preco, preco_promocional, ativo, destaque, novo, bling_id, sku, seo_titulo, seo_descricao, seo_keywords |
| `ProdutoImagem` | produto, imagem (validada por magic bytes), alt, principal, ordem |
| `CorPadrao` | nome (único), codigo_hex, **codigo_hex_secundario** (opcional — bolinha bicolor diagonal), ordem |
| `ProdutoCorFoto` | produto (FK), cor (FK→CorPadrao), imagem (FK→ProdutoImagem) — vincula foto a uma cor; ao clicar na bolinha a galeria muda para essa foto. 1 entrada por (produto+cor) vale para todos os tamanhos. |
| `TamanhoPadrao` | nome (único), ordem — **lista-mestre de tamanhos** |
| `Variacao` | produto, **cor** (FK→CorPadrao), **tamanho** (FK→TamanhoPadrao), estoque, sku_variacao, bling_variacao_id, ativa |
| `Avaliacao` | produto, cliente, nota, titulo, comentario, aprovada (moderação manual) |

**Importante sobre Variacao:**
- Cor e Tamanho são FKs — cadastre as cores/tamanhos em Produtos → Cores padrão / Tamanhos padrão ANTES de criar variações
- `clean()` detecta variação duplicada (mesmo produto + mesma cor + mesmo tamanho) e lança ValidationError
- Migration 0005 fez data migration automática dos dados de texto antigos (ex: "PRETO" → CorPadrao)

**Bolinha bicolor:** `CorPadrao.codigo_hex_secundario` preenchido → template usa `conic-gradient(cor1 0deg 180deg, cor2 180deg 360deg)`. Diagonal automática, sem JS extra.

**Foto por cor:** no admin do produto há inline `ProdutoCorFoto` (após "Fotos do produto"). Vincule uma foto já cadastrada a uma cor. O JS do detalhe usa `fotosPorCorMap` (JSON) para trocar a galeria ao clicar na bolinha.

### `apps/conteudo/`
| Model | Campos principais |
|---|---|
| `BannerPrincipal` | ordem, tipo (video/foto), video, **video_mobile** (opcional 9:16), foto, **foto_mobile** (opcional 9:16), poster, pretitulo, titulo, titulo_italico, subtitulo, texto_botao, url_botao, ativo. Mobile: `<picture>` para fotos, JS swap (data-src-mobile) para vídeos |
| `MiniBanner` | posicao (esq/dir, único), foto, pretitulo, titulo, url, ativo |
| `LookDaSemana` | titulo, descricao, foto, **produto_ponto1/2/3** (FK→Produto, null/blank), ponto1_top/esq, ponto2_top/esq, ponto3_top/esq (DecimalField %), ativo, criado_em |
| `PaginaEstatica` | slug (choices: politica_privacidade, trocas_devolucoes, sobre, termos_uso, perguntas_frequentes, meios_pagamento), titulo, conteudo (HTML rich text — editor WYSIWYG no admin via `static/admin/js/pagina_editor.js`), **imagem** (opcional, usada em "Nossa história"), ativo |

**Importante sobre LookDaSemana:**
- M2M `produtos` foi **removido** — cada ponto "+" tem seu próprio FK direto: `produto_ponto1`, `produto_ponto2`, `produto_ponto3`
- Posições são editadas via **editor visual JS** no admin (clica na foto → preenche os campos automaticamente)
- Arquivo: `static/admin/js/look_editor.js` injetado pelo `class Media` do LookDaSemanaAdmin
- No template `home/index.html`: `{% if look_obj.produto_ponto1 %}<a style="top:{{ look_obj.ponto1_top }}%;left:{{ look_obj.ponto1_esq }}%;">`

**Importante sobre BannerPrincipal:**
- Todos os campos de texto (titulo, subtitulo, botao) são **opcionais** — deixe em branco se o vídeo/foto já tem texto na imagem
- Para **foto-type banner**: crie um NOVO registro com tipo=Foto e faça upload da foto. O campo titulo não é obrigatório
- Validação só ocorre na criação (não na edição de registros existentes)
- O overlay de texto no hero só aparece se houver algum texto preenchido

### `apps/pedidos/`
| Model | Campos principais |
|---|---|
| `Pedido` | numero (DI-XXXX), cliente, dados copiados, endereço copiado, subtotal, desconto, frete, total, status, gateway, codigo_rastreio, bling_pedido_id, **cupom** (FK→Cupom, null), **cupom_codigo** (cópia), **codigo_vendedor** (FK→CodigoVendedor, null), **codigo_vendedor_str** (cópia) |
| `ItemPedido` | pedido, produto, variacao, nome/preco copiados, quantidade |
| `HistoricoPedido` | log de mudanças de status |
| `Cupom` | codigo (único), tipo (percentual/fixo), valor, quantidade_total (null=ilimitado), vezes_usado, um_por_cliente (bool), valido_de, valido_ate, ativo. `esta_valido(cpf)` → (bool, motivo). `calcular_desconto(subtotal)` → Decimal |
| `CodigoVendedor` | codigo (auto-gerado 8 chars aleatórios, único), nome, ativo — vincula venda ao vendedor sem desconto |

**Cupom no checkout:**
- Campo `Cupom de desconto` + botão "Aplicar" — AJAX para `/carrinho/validar-cupom/`
- Campo `Código do vendedor` + botão "Aplicar" — AJAX para `/carrinho/validar-vendedor/`
- Ambos ficam dentro de um `<details>` recolhível "Tem um cupom ou código de vendedor?"
- Desconto aparece no resumo lateral em tempo real
- `_processar_checkout` aplica o desconto no `total` e incrementa `Cupom.vezes_usado` fora do bloco atômico (após commit)

### `apps/bling/`
| Model | Campos |
|---|---|
| `BlingToken` | access_token, refresh_token, expira_em |
| `BlingLog` | tipo, pedido, sucesso, payload_enviado, resposta, erro |

---

## Bling — Integração Bidirecional (apps/bling/services.py)

### Fluxo de situações

| Evento | situacao_id | Nome no Bling |
|---|---|---|
| Pedido criado no checkout | `754756` | Em andamento - Site (custom D'ELLA, verificado via API — pedido 9638) |
| Pagamento confirmado (cartão/pix) | `18723` | Atendido - Site (custom D'ELLA) |
| Pedido cancelado | `12` | Cancelado (padrão Bling) |

**IDs de situação observados via API (referência):**
- `754756` = Em andamento - Site (custom) ← usado no checkout
- `18723` = Atendido - Site (custom) ← usado no pagamento confirmado
- `15762` = situação custom antiga (pedidos anteriores)
- `15` = Em andamento (padrão Bling)
- `9` = Atendido (padrão Bling)
- `12` = Cancelado (padrão Bling)
- `6` = Em aberto (padrão Bling — estado inicial de criação, **não usar**)

**Importante:** o Bling ignora o campo `situacao` no POST de criação e cria tudo como "Em aberto" (ID 6). Por isso o código faz um PATCH separado logo após a criação para forçar "Em andamento - Site". Se o PATCH falhar, o pedido fica como "Em aberto" — verificar logs do gunicorn.

### IDs fixos
```python
LOJA_ID            = 204582763   # Show Room - D'ella
UNIDADE_NEGOCIO_ID = 1484433     # Matriz
VENDEDOR_PADRAO_ID = 7616577942  # CRISLAINY SILVERIO GIACOMELLI
```

### Mapeamento de vendedores (nome maiúsculas → bling_vendedor_id)
```python
VENDEDORES_BLING = {
    'TINA DIAS':                     7613793453,
    'CRISLAINY SILVERIO GIACOMELLI': 7616577942,
    'MICHELLE ALVES FERNANDES':      15205612892,
    'SARA OLIVEIRA':                 15596882226,
}
```
O sistema lê `pedido.codigo_vendedor.nome` e busca no dicionário; se não achar, usa Crislainy como padrão.

### Formas de pagamento
```python
FORMA_PAG_PIX = 1194065  # TED/DOC/TRANSF./PIX (À Vista)

FORMA_PAG_CARTAO = {
    1: 929656,    # PAG SEGURO À Vista
    2: 2103282,   # PAG SEGURO 2x
    3: 7128327,   # PAG SEGURO 3x
    4: 7128329,   # PAG SEGURO 4x
    5: 7128331,   # PAG SEGURO 5x
}
```

### Descrição dos itens no Bling

Formato: `NOME PRODUTO (COR) (TAMANHO)` — ex: `BODY BASIC ANACA (BRANCO POLAR) (P)`

Código: lê diretamente das FKs `variacao.cor.nome` e `variacao.tamanho.nome` (uppercase). Se a variação foi deletada, faz fallback parseando `variacao_desc` salvo no `ItemPedido`. SKU da variação vai no campo `codigo`.

### Transporte (bloco `transporte` no payload)

```python
{
    'fretePorConta': 1,          # 1=FOB (cliente paga) | 0=CIF (frete grátis ≥R$800)
    'frete':         29.78,
    'transportador': {'nome': 'CORREIOS'},
    'logistica':     {'nome': 'Melhor Envio - Correios'},
    'volumes': [{
        'servico':    'PAC',     # ou 'SEDEX'
        'modalidade': 1,         # 1=PAC, 2=SEDEX
        'peso':        0.5,      # DIMENSOES_PADRAO da caixa D'ELLA
        'altura':      8,
        'largura':     17,
        'comprimento': 28,
    }]
}
```
`fretePorConta` é calculado automaticamente: `1` quando `pedido.frete > 0`, `0` quando frete grátis.

### Parcelas — sempre 1 (antecipação)
Mesmo que o cliente parcele em 2–5x, lança **apenas 1 parcela** no Bling (valor total), pois a loja usa antecipação e recebe tudo à vista. A observação da parcela inclui o código de autorização PagSeguro (`pedido.gateway_id`):
```
Cartão de Crédito 3x — Autorização: CHARGE_ID_DO_PAGSEGURO
```

### Estoque no site (apps/produtos/models.Variacao.estoque)
- **Diminui** no checkout, dentro de `transaction.atomic()` via `Greatest(F('estoque') - qty, Value(0))` — nunca vai negativo
- **Restaura** ao cancelar (webhook PagSeguro + cron `cancelar_pedidos_expirados`) via `F('estoque') + item.quantidade`

### Pontos de integração no código
| Arquivo | Evento |
|---|---|
| `apps/pedidos/views.py` | Checkout → `enviar_pedido_bling()` + `atualizar_situacao_bling(ATENDIDO)` se pix confirmado |
| `apps/pagamentos/views.py` | Webhook PagSeguro → `atualizar_situacao_bling(ATENDIDO ou CANCELADO)` + `restaurar_estoque_pedido()` |
| `apps/pedidos/management/commands/cancelar_pedidos_expirados.py` | Cron → `restaurar_estoque_pedido()` + `atualizar_situacao_bling(CANCELADO)` |

---

## Navbar (base.html)

**Logo D'ELLA Instore:** duas linhas empilhadas — `.navbar-logo-della` (Playfair Display, **2.4rem**, letra-spacing 0.18em) e `.navbar-logo-instore` (Jost, **0.94rem**, letra-spacing 0.48em, `text-align: center`). `.navbar-logo` usa `align-items: stretch` para que o Instore ocupe exatamente a largura da D'ELLA. Mesma estrutura no footer: `.footer-logo-della` (1.6rem) e `.footer-logo-instore` (**0.72rem**, centralizado).

**Posicionamento absoluto da logo:** `.navbar-logo` é filho direto de `<nav>` (fora do `.navbar-topo`), com `position: absolute; left: 3.5rem; top: 0; height: var(--navbar-total); display: flex; flex-direction: column; justify-content: center; z-index: 2` — assim a logo fica verticalmente centralizada em relação a toda a altura da navbar (topo + categorias) e não empurra os outros elementos do grid.

Estrutura em 2 linhas:
```
[Linha 1 — .navbar-topo]     hamburger (mobile) | D'ELLA / Instore | busca + login + whatsapp + carrinho
[Linha 2 — .navbar-categorias-bar]   BODY · BEACHWEAR · CASUAL · ... (categorias-mãe com dropdown)
```
- Navbar é `position: fixed`, altura total: 60px (topo) + ~36px (categorias) = ~96px
- Em páginas com `.navbar.solida` (ex: home, detalhe), o conteúdo tem `margin-top: var(--navbar-total)`
- Mobile: linha de categorias some, hamburger abre menu lateral (`#menu-mobile`)
- Ícones à direita: Busca + Login/Conta + WhatsApp Suporte + Carrinho (wishlist removida)
- **JS (`della.js`):** `navbarComEfeitoScroll` verifica se navbar **começou** como `transparente` — só aplica efeito de scroll se sim. Páginas que começam com `solida` (home) não ficam transparentes nunca
- **Dropdown subcategorias:** `.navbar-menu { overflow: visible }` — era `overflow-x: auto`, cortava o dropdown
- **Clicar em categoria mãe:** view `loja` inclui produtos das subcategorias (`Q(categoria=cat) | Q(categoria_id__in=sub_ids)`)
- **Sidebar de categorias (`loja.html`):** árvore colapsável — categoria mãe clicável via `.sidebar-cat-mae` button + `.sidebar-subcats` lista. **NÃO existe** "Todas em X" — foi removido. Clicar na mãe já mostra todas.

---

## Footer (base.html — 4 colunas)

Estrutura atual (da esquerda para direita):
1. **Brand** — logo D'ELLA Instore, descrição, Instagram (@dellainstore) + TikTok (@dellainstore_)
2. **Ajuda** — Fale conosco, Meus pedidos, Trocas e devoluções, Guia de tamanhos, Perguntas frequentes
3. **D'ELLA Instore** — Nossa história, Política de privacidade, Termos de uso
4. **Endereços** — Show Room + Studio Anacã com WhatsApp

**Selos visuais** (`.footer-selo-visual`): SSL Seguro, Compra Segura, LGPD — com ícone dourado + borda fina.
**Bandeiras de pagamento** (`.footer-pagamentos`): Pix (`fab fa-pix`), Visa (`fab fa-cc-visa`), Mastercard (`fab fa-cc-mastercard`), Amex (`fab fa-cc-amex`), Elo (texto). Classes de cor: `.pix`, `.visa`, `.mc`, `.amex`, `.elo`. Ficam no centro do `footer-bottom` entre copyright e selos.
**CNPJ** do Show Room exibido no endereço: `29.049.870/0001-37` — linha entre CEP e e-mail.

**Nota:** A coluna "Loja" foi removida. "Trocas" foi movida para Ajuda. Não restaurar a coluna "Loja".

---

## Homepage (home/index.html)

Seções em ordem:
1. **Hero slider** — banners do admin (BannerPrincipal), fallback estático. Dots (7×7px) no canto inferior direito. Botão mute no canto inferior **esquerdo**. Hero aparece ABAIXO do menu. **Altura: `calc(98svh - var(--navbar-total))`** (quase tela cheia).
2. **Destaques da semana** — carrossel horizontal de produtos com `destaque=True`. Mostra 4 por vez (3 em ≤1024px, 2 em ≤640px). Setas prev/next **absolutas nas laterais** das fotos (`left/right: -1.5rem`, `top: 38%`), não abaixo. Swipe mobile. HTML: `.destaques-carousel` > setas absolutas + `.destaques-viewport` > `.destaques-track`. JS: `#destaques-carousel`, `#destaques-track`, `#destaques-prev`, `#destaques-next`.
3. **Mini banners** — MiniBanner do admin (2 colunas, gap 1.5rem, max-width 1200px). **`aspect-ratio: 3/4` + `max-height: 80vh` + `width: 100%`** — proporcionais à largura, nunca cortam o topo, nunca ultrapassam 80% da tela. `background-position: center top` ancora a imagem pelo topo. Padding `2rem`.
4. **Look da semana** — foto + pontos "+". Grid `0.75fr 1.25fr`, max-width `1100px`, padding reduzido `4rem`. No breakpoint 1024px: single-col, max-width da foto `420px`.
5. **Manifesto** — texto fixo da marca
6. **Depoimentos** — Avaliacao aprovadas
7. **Instagram** — banner CTA estático (@dellainstore)
8. **Newsletter** — AJAX na página + **popup automático** após 5s (aparece 1x por sessão via `sessionStorage`). HTML: `#popup-newsletter` em `base.html`. JS: `della.js`.

**Seções removidas:** "Nossas Categorias" (grid de categorias abaixo do hero)

---

## Página de Produto (produtos/detalhe.html)

- **Sem breadcrumb** — foi removido (o menu fixo no topo já é suficiente)
- Galeria com thumbnails clicáveis
- Seleção de cor: bolinhas coloridas (CorPadrao.codigo_hex). Todas as bolinhas têm `box-shadow: inset 0 0 0 1px rgba(0,0,0,0.15)` para que cores brancas fiquem visíveis. Selecionada = borda dupla + checkmark branco
- Seleção de tamanho: botões de texto **únicos por tamanho** (deduplicados via `.values().distinct()` no view). Selecionado = fundo preto
- **Lógica de variação via JSON map** (`variacoes_json`): o view monta um mapa `"{cor_id}_{tam_id}" → {id, disponivel}` que o JS usa para resolver a variação correta ao selecionar cor + tamanho
- Ao selecionar uma cor, os tamanhos indisponíveis para essa cor ficam desabilitados automaticamente
- Clicar novamente deseleciona cor ou tamanho
- `variacaoSelecionadaId` é resolvido pelo JS consultando `variacoesMap[corKey_tamKey]`
- **Bolinhas de cor deduplicadas em Python** (`views.py → detalhe_produto`): iterar `.values('cor__id', 'cor__nome', 'cor__codigo_hex')` com set de IDs vistos — garante 1 bolinha por `cor__id` mesmo que o produto tenha múltiplas variações da mesma cor (ex: Branco P, Branco M, Branco G → 1 bolinha Branco)

---

## Admin Painel (/painel/)

### Tema do Painel Admin (design premium D'ELLA)

O painel usa um tema completamente customizado, com identidade visual da marca D'ELLA (preto + dourado, fontes Playfair Display e Jost).

#### Arquivos principais

| Arquivo | Função |
|---|---|
| `static/admin/css/della_admin.css` | Todo o CSS customizado do painel — cores, tipografia, cards, sidebar, tabelas, botões |
| `templates/admin/base_site.html` | Template base customizado: remove dark mode, injeta fontes, CSS e script de scroll |
| `templates/admin/index.html` | Dashboard com cards organizados por seção |
| `templates/admin/conteudo/instagrampost/change_list.html` | Listagem customizada com botões de importação do Instagram |

#### Como funciona o tema (decisões arquiteturais importantes)

**Dark mode desabilitado:**
- Django Admin 5.x carrega `dark_mode.css` via `{% block dark-mode-vars %}` no `base.html`
- Esse arquivo aplica `@media (prefers-color-scheme: dark)` que sobrescreve as variáveis CSS e escurece tudo quando o navegador do usuário está no tema escuro
- **Solução:** `base_site.html` sobrescreve `{% block dark-mode-vars %}` como vazio, removendo completamente `dark_mode.css` e `theme.js` do Django. O painel fica sempre claro, independente do tema do navegador

**Variáveis CSS:**
- O `della_admin.css` redefine as variáveis nativas do Django (ex: `--body-bg`, `--primary`, `--darkened-bg`) no `:root` — elas são consumidas pelos próprios CSS do Django (base.css, nav_sidebar.css, changelists.css), então redefinindo aqui controlamos tudo

**Botão theme-toggle oculto:**
- Django ainda injeta o botão `<button class="theme-toggle">` no header via `color_theme_toggle.html`
- Como removemos `dark_mode.css`, esse botão fica sem estilos e aparece como uma caixa branca no header
- Corrigido com `.theme-toggle { display: none !important; }` no `della_admin.css`

**Sidebar sempre branca:**
- `#nav-sidebar { background-color: var(--da-white) !important; }`
- `#nav-sidebar * { background-color: transparent !important; }` — reseta todos os filhos
- Links "+ Adicionar" da sidebar **ocultos**: `#nav-sidebar .module td { display: none !important; }` — botão disponível dentro de cada página
- Tabelas internas com `table-layout: fixed; width: 100%` para as captions ficarem em linha única

**Ícone "+" nos botões de adicionar (object-tools):**
- Django aplica `background-image: url(tooltag-add.svg)` com `padding-right: 26px` em `.addlink`
- Nosso CSS sobrescreve o padding, fazendo o ícone sobrepor o texto
- Corrigido com `background-image: none !important; padding-right: 0.9rem !important` em `ul.object-tools li a.addlink`

**Scroll do menu lateral persistido em TODAS as páginas:**
- `base_site.html` tem um `<script>` inline que salva/restaura `#nav-sidebar.scrollTop` via `sessionStorage`
- Salva ao clicar em qualquer link da sidebar (`click`) e ao sair da página (`beforeunload`)
- Antes existia só em `admin_linhas.js` (que só carrega nas páginas com `class Media` no admin), causando reset ao navegar para páginas sem o script

**Barra de pesquisa centralizada:**
- `#toolbar { padding: 0.6rem 1rem !important; display: flex; align-items: center; }`
- `#changelist-search { display: flex; align-items: center; gap: 0.5rem; }`

#### Botões por linha (padrão unificado)

Todos os admins usam classes CSS em vez de estilos inline:
- `della-btn-edit` — botão dourado (editar)
- `della-btn-delete` — botão borda vermelha (excluir)

```python
from django.utils.html import format_html
from django.urls import reverse

def acoes_linha(self, obj):
    edit_url   = reverse('admin:APP_MODEL_change', args=[obj.pk])
    delete_url = reverse('admin:APP_MODEL_delete', args=[obj.pk])
    return format_html(
        '<a href="{}" class="della-btn-edit">✎ Editar</a>'
        '<a href="{}" class="della-btn-delete" onclick="return confirm(\'Excluir?\')">✕ Excluir</a>',
        edit_url, delete_url,
    )
acoes_linha.short_description = 'Ações'
```

#### Após qualquer mudança no CSS do admin

```bash
cd /var/www/della-sistemas/projetos-claude/site_della && source venv/bin/activate
python manage.py collectstatic --noinput --settings=core.settings.production
kill -HUP $(ps aux | grep gunicorn | grep della_site | grep -v grep | head -1 | awk '{print $2}')
```

O WhiteNoise usa hash no nome do arquivo (`della_admin.<hash>.css`) — cada mudança gera hash novo e força o browser a baixar a versão atualizada.

### Produtos → Cores padrão
Cadastre aqui todas as cores (nome + hex). Use ANTES de criar variações de produtos.

### Produtos → Tamanhos padrão
Cadastre aqui todos os tamanhos (nome + ordem). A ordem controla a exibição no site.

### Produtos → Produtos
- Importar via planilha CSV (botão no topo da listagem)
- Variações usam dropdown de CorPadrao e TamanhoPadrao
- Clone de variação disponível em cada linha do inline
- Aviso de variação duplicada no clean()

### Conteúdo do Site → Slides do banner principal
- Tipo Vídeo: upload do .mp4 (+ poster opcional). Título/texto opcionais
- Tipo Foto: upload da imagem. Título/texto opcionais. **Crie um registro separado por slide**
- Apenas slides com `ativo=True` aparecem no site

### Conteúdo do Site → Mini banners
- Posições: Esquerda e Direita (máximo 1 ativo por posição)
- Foto em **retrato 3:4** (ex: 900×1200px). O card usa `aspect-ratio: 3/4` + `max-height: 80vh` + `width: 100%` — proporcional, responsivo, nunca corta o topo
- `background-position: center top` — âncora pelo topo; o **assunto principal deve ficar na parte superior** da foto
- Texto (pretítulo/título) fica alinhado ao rodapé do card com gradiente escuro para contraste

### Conteúdo do Site → Look da semana
- Upload da foto + selecione até 3 produtos (um por ponto: Ponto "+" 1, 2, 3)
- Clique na foto no **editor visual** para posicionar cada ponto automaticamente
- Apenas o look ativo mais recente aparece

### Categorias
- Admin mostra mães e filhas agrupadas (mãe → filhas indentadas logo abaixo)
- `list_editable: ordem` — ajuste a ordem inline na listagem

### Bling → Tokens de acesso
- Token de acesso expira em **1 hora** (comportamento normal do Bling — não é bug)
- O sistema tenta renovar automaticamente via `refresh_token` (válido por 30 dias) a cada requisição
- Se o token aparecer como "Expirado" no admin: clique **"Atualizar Token"** (botão verde) para renovar manualmente
- Se o `refresh_token` também expirar (30 dias sem uso): clique **"Re-autorizar"** (botão dourado) para refazer o OAuth
- View de refresh manual: `/bling/refresh-token/` (staff only, redireciona com mensagem de sucesso/erro)

---

## Arquivos JS/CSS importantes

| Arquivo | O que faz |
|---|---|
| `static/js/della.js` | JS principal: navbar scroll, hero slider (com swipe mobile), drawer carrinho, wishlist, newsletter, menu mobile, galeria do produto (setas + swipe), tap nos pontos "+" do Look (mobile) |
| `static/css/della.css` | Todo CSS customizado da marca |
| `static/admin/js/look_editor.js` | Editor visual de pontos do Look da Semana no admin (clica na foto → preenche %) |
| `core/storage.py` | Storage custom `WhiteNoiseManifestStorageLeniente` — veja "Cache-busting" abaixo |

### Cache-busting de arquivos estáticos (MUITO IMPORTANTE)

Nginx serve `/static/*` com `Cache-Control: immutable, max-age=2592000` (30 dias). Sem hash no nome, o Safari iOS trava a versão antiga por um mês e usuários não veem atualizações de CSS/JS.

**Configuração atual** (Django 5.x usa `STORAGES` dict — `STATICFILES_STORAGE` é ignorado):

```python
# core/settings/base.py
STORAGES = {
    'default':     {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {'BACKEND': 'core.storage.WhiteNoiseManifestStorageLeniente'},
}
```

O storage custom em `core/storage.py` herda de `CompressedManifestStaticFilesStorage` e sobrescreve `manifest_strict = False` + `hashed_name()` com fallback. Sem isso, qualquer `{% static %}` apontando para um arquivo inexistente (ex: `images/brand/og-default.jpg`, que ainda não foi enviado) derruba a página com `ValueError`.

**Fluxo ao publicar mudanças em CSS/JS:**

```bash
cd /var/www/della-sistemas/projetos-claude/site_della
source venv/bin/activate
python manage.py collectstatic --noinput --settings=core.settings.production
kill -HUP $(ps aux | grep gunicorn | grep -v grep | head -1 | awk '{print $2}')
```

O `collectstatic` pós-processa e gera `della.<hash>.js` / `della.<hash>.css`. Cada mudança no código-fonte produz um hash novo — o HTML passa a referenciar o novo arquivo, forçando o browser (incluindo Safari iOS) a baixar a versão atual.

**Para verificar que o servidor está entregando a versão nova:**

```bash
curl -s https://novo.dellainstore.com.br/ | grep -oE 'della\.[a-z0-9]+\.(js|css)'
```

### Decisões de CSS relevantes
- **Logo navbar — posicionamento absoluto:** `.navbar-logo` é filho direto de `<nav>` (fora do `.navbar-topo`). `position: absolute; left: 3.5rem; top: 0; height: var(--navbar-total); display: flex; flex-direction: column; justify-content: center; z-index: 2`. Isso faz ela cobrir verticalmente as duas barras da navbar sem afetar o grid do `.navbar-topo` (que usa `1fr auto`).
- **Itens do menu** — `font-weight: 400` (antes era 500 — mais delicado)
- **Ícones de ação** (busca/login/whatsapp/carrinho) — `font-size: 1.15rem` (antes era 0.82rem)
- **Manifesto** — padding: `5rem 2rem` (antes 8rem), título: `clamp(1.6rem, 3vw, 2.6rem)` (antes 3.5rem)
- **`.conta-wrapper`** — `padding: calc(var(--navbar-total) + 2rem) 1.5rem 5rem` — o `+ 2rem` extra evita que o "Olá, Nome" apareça colado na navbar
- `.hero { margin-top: var(--navbar-total); }` — hero abaixo do menu (não atrás)
- `.hero-mute-btn { bottom: 2rem; left: 2rem; }` — botão mute no canto inferior esquerdo (longe dos dots)
- `.produto-acoes` usa `visibility: hidden/visible` (não `display:none`) para transição suave + pointer-events corretos
- `.variacao-cor { box-shadow: inset 0 0 0 1px rgba(0,0,0,0.15); }` — torna bolinhas brancas visíveis
- **WhatsApp FAB:** `.whatsapp-fab` tem `pointer-events: none` — o container não bloqueia cliques na área ao redor. Apenas `.whatsapp-btn-principal` tem `pointer-events: auto`. Ao abrir o menu, `.whatsapp-opcoes.aberto` também recebe `pointer-events: auto`.
- **Hero slider:** altura `calc(98svh - var(--navbar-total))` (quase tela cheia). Dots `7×7px` (mais delicados). Timer = 6s. Swipe horizontal na seção `#hero-slider`; threshold 40px; ignora gesto vertical. `touchstart` nos dots é **não-passivo** e chama `e.stopPropagation()` + `e.preventDefault()`. `.hero-slides` tem `pointer-events: none`. IDs dos `<video>` removidos (eram duplicados).
- **Destaques carrossel:** setas `position: absolute` nas laterais do `.destaques-carousel` (`left/right: -1.5rem`, `top: 38%`). `.destaques-viewport` tem `overflow: hidden` (clipa o track). `.destaques-carousel` tem overflow padrão para as setas ficarem visíveis. No mobile ≤768px setas ficam em `left/right: 0.25rem` para não sair da tela.
- **Hero vídeo autoplay:** além de `autoplay muted playsinline`, o `della.js` força `.play()` em `loadeddata`/`canplay` — alguns navegadores cancelam autoplay após `v.load()` (que acontece no swap do vídeo mobile).
- **Look da semana — pontos "+" (fix definitivo):** estrutura de dois divs: `.look-foto-outer` (`position:relative; aspect-ratio:3/4`) é o containing block dos pontos; dentro dele `.look-foto` (`position:absolute; inset:0; overflow:hidden`) só clipa a imagem. Os `.look-ponto` são filhos diretos do `.look-foto-outer` (irmãos do `.look-foto`), nunca dentro dele — assim não são clipeados pelo `overflow:hidden` da imagem.
- **Look da semana — valores decimais em CSS inline (BUG de localização):** `LANGUAGE_CODE=pt-br + USE_I18N=True` faz `DecimalField` renderizar `56.4` como `56,4` → vírgula quebra parsing CSS em `style="top:56,4%"` e empilha todos os pontos em 0,0. Solução: `{% load l10n %}` + filtro `|unlocalize` em todas as saídas de `ponto1_top/esq`, `ponto2_top/esq`, `ponto3_top/esq` (`templates/home/index.html`).
- **Look da semana — tap mobile (sticky hover):** Safari iOS mantém `:hover` grudado após touch, então o tooltip não fechava. `:hover` foi escopado em `@media (hover:hover) and (pointer:fine)` (só desktop); no mobile o `della.js` detecta `matchMedia('(hover: none)')` e faz toggle da classe `.aberto` no `.look-ponto` (tap abre → tap de novo no mesmo `+` fecha → tap fora fecha → tap no tooltip navega ao produto). `.aberto` também aplica `z-index:20` no ponto e `25` no tooltip para ficar acima da outra bolinha.
- **Galeria do produto — mobile:** `aspect-ratio: 3/4`, `object-fit: contain` (foto inteira sem corte), setas `.galeria-nav` escondidas com `display:none` — navegação por swipe horizontal na `.galeria-principal` (handlers em `della.js`, threshold 40px, ignora gesto vertical).
- **Menu mobile:** `#menu-mobile` tem `overflow-y-auto overscroll-contain` para rolar quando a lista de categorias é longa; `della.js` trava `document.body.overflow` enquanto aberto, fecha com o botão `#btn-menu-mobile-fechar`, com `Escape` ou clicando no próprio hamburger. O botão `X` NÃO tem mais `onclick` inline — tudo pelo listener em JS.
- **Modal `.modal-overlay` (guia de tamanhos):** estado padrão é `display:none` (não `opacity:0`) — no mobile o `opacity:0; pointer-events:none` ainda deixava o texto "vazar" no fluxo visualmente. `.aberto` aplica `display:flex`.
- **Font Awesome 6 Free:** usar `fas` para ícones sem variante regular grátis (house, bag-shopping, location-dot, arrow-right-from-bracket, truck, etc.). Usar `far` apenas para: heart, user, star, circle-check, circle-xmark. NÃO usar `fa-regular fa-X` — causa ícones de retângulo vazio quando o ícone não existe na variante regular free

---

## Import de Produtos

URL: `/painel/produtos/produto/importar/`

Dois formatos suportados (detecção automática):

### Formato Bling (recomendado)
Exportar direto do Bling: **Produtos → Exportar → CSV ou XLSX**.
Colunas: `ID, Código, Descrição, Preço, Situação`
A Descrição segue: `MODELO (COR) (TAMANHO)` — ex: `BODY GIU (AZUL MARINHO) (PP)`
- O sistema parseia o padrão e cria Produto + CorPadrao + TamanhoPadrao + Variacao automaticamente
- HEX das cores é preenchido automaticamente para ~30 cores conhecidas (dicionário em `ProdutoAdmin._COR_HEX`)
- Informe a **categoria** no formulário de importação — todos os produtos importados recebem essa categoria

### Formato legado (CSV manual)
Colunas: `nome, categoria, descricao, composicao, genero, preco, preco_promocional, ativo, destaque, novo, bling_id, sku, var_cor, var_tamanho, var_estoque, var_sku, var_bling_id`
- `var_cor` = nome da cor (case-insensitive); cria `CorPadrao` automaticamente se não existir
- Baixar modelo: botão na página de importação

**openpyxl** adicionado ao `requirements.txt` para suporte a .xlsx.

---

## Tamanhos ideais de imagens

| Tipo | Dimensão | Proporção | Obs |
|---|---|---|---|
| **Vídeo hero — Desktop** | 1920×1080px | 16:9 | MP4, H.264, até 50MB |
| **Vídeo hero — Mobile** | 1080×1920px | 9:16 | MP4, H.264, até 30MB — campo `video_mobile` |
| **Foto do banner — Desktop** | 1920×1080px | 16:9 | JPG, foco no centro |
| **Foto do banner — Mobile** | 1080×1920px | 9:16 | JPG — campo `foto_mobile` (opcional, usa `<picture>`) |
| **Poster do vídeo** | 1920×1080px | 16:9 | JPG, comprimido |
| **Mini banners** | 900×1200px | 3:4 (retrato) | JPG — card usa `aspect-ratio:3/4`, âncora pelo topo (`center top`). Foco principal no **topo** da imagem (não no rodapé). Texto do overlay fica na parte inferior. |
| **Look da semana** | 800×1100px | 3:4 | JPG, foto de corpo inteiro |
| **Produto (retrato)** | 800×1067px | 3:4 | JPG/PNG — preferido |
| **Produto (quadrado)** | 800×800px | 1:1 | JPG/PNG |
| **Open Graph** | 1200×630px | 1.91:1 | Para compartilhamento social |

---

## Segurança Implementada

| Camada | O que faz |
|---|---|
| `scripts/check_security.sh` | Verifica .env no git, SECRET_KEY hardcoded, DEBUG em prod |
| `apps/core_utils/sanitize.py` | sanitize_text, validate_image_upload (magic bytes), validate_cpf |
| `django-axes` | Bloqueia IP após 5 tentativas de login falhas por 1 hora |
| `django-csp` | Content-Security-Policy headers |
| Django CSRF | Ativo em todos os forms |
| Nginx | Bloqueia .env, .git, .sql; scripts em /media/; headers de segurança |
| `production.py` | HTTPS obrigatório, HSTS, cookies seguros. **`CSRF_COOKIE_HTTPONLY = False`** (necessário para AJAX ler o csrftoken) |
| ORM Django | Zero SQL raw |

---

## Auditoria de Segurança — 2026-04-20 (Pós-lançamento, primeiros clientes reais)

Auditoria completa rodada após o site começar a receber clientes reais colocando dados pessoais (nome, CPF, e-mail, endereço, telefone, senha).

### ✅ Resultado: Nenhum vazamento identificado. Postura de segurança sólida.

| Verificação | Resultado |
|---|---|
| `.env` rastreado no git | ❌ Não (apenas `.env.example` com placeholders) |
| `.gitignore` bloqueia `.env`, `.env.*` | ✅ OK (exceção para `.env.example`) |
| Permissões do `.env` | ✅ `600` (só owner lê/escreve) |
| Credenciais hardcoded em `.py`/`.js` commitados | ✅ Nenhuma encontrada |
| Histórico git com `.env` real | ✅ Nunca commitado |
| `python manage.py check --deploy` | ✅ 0 issues |
| HSTS 1 ano + preload | ✅ Ativo (`max-age=31536000; includeSubDomains; preload`) |
| `SESSION_COOKIE_SECURE` / `CSRF_COOKIE_SECURE` | ✅ True |
| `SESSION_COOKIE_HTTPONLY` | ✅ True |
| `X-Frame-Options: DENY` | ✅ Ativo (Django + Nginx) |
| `SECURE_CONTENT_TYPE_NOSNIFF` | ✅ True |
| `SECURE_REFERRER_POLICY` | ✅ `strict-origin-when-cross-origin` |
| CSP com domínios explícitos | ✅ Ativa (restringe `connect-src` a PagBank) |
| Django `debug=False` em produção | ✅ Confirmado |
| Nginx bloqueia `.env/.git/.sql/.bak/.log` | ✅ Todas retornam 403 |
| Nginx bloqueia execução de scripts em `/media/` | ✅ `deny all` para `.php/.py/.pl/.sh/.cgi` |
| `/media/` listagem direta | ✅ 403 Forbidden |
| SQL raw no código | ✅ Nenhum — 100% ORM |
| `eval/exec/pickle.loads/yaml.load` com input externo | ✅ Nenhum |
| `django-axes` brute force | ✅ 5 tentativas / 1h lockout por IP+user |
| Magic-bytes em uploads de imagem | ✅ `validate_image_upload` aplicado em conteudo e produtos |
| CPF/e-mail/endereço em logs | ✅ `_redact_payload_pii` em Bling (S5) |
| Webhook PagBank com verificação de origem | ✅ Reconsulta autenticada `GET /orders/{id}` (C3) |
| Webhook Bling com HMAC | ✅ Ativo — valida `X-Bling-Signature-256` com `BLING_CLIENT_SECRET` (Bling v3) |
| IDOR em detalhe de pedido | ✅ `_pode_acessar_pedido` unificado (S1) |
| Dados de cartão no backend | ✅ Tokenização frontend — PAN nunca toca servidor (S3) |
| Tokens Bling mascarados no admin | ✅ `access_token_mascarado` / `refresh_token_mascarado` (S4) |
| OAuth Bling valida `state` | ✅ `secrets.token_urlsafe` + `compare_digest` (C4) |
| Superusers da loja | ✅ Apenas 1 (`admin@dellainstore.com.br`) |
| Access attempts bloqueados (axes) | ✅ 0 bloqueios ativos no momento |
| URLs comuns de ataque (`/.env`, `/.git/config`, `/wp-admin`) | ✅ Todas retornam 403/404 |

### ✅ Itens de atenção — TODOS RESOLVIDOS em 2026-04-20

**1. `core/settings/django_default.py` — REMOVIDO** ✅
- Era arquivo órfão gerado pelo `django-admin startproject` com `SECRET_KEY = 'django-insecure-...'` e `DEBUG = True`.
- `git grep` confirmou que não era referenciado em nenhum lugar.
- Removido via `git rm core/settings/django_default.py`.
- Mantidos apenas `base.py`, `production.py`, `development.py`.

**2. Webhook Bling v3 — HMAC CONFIGURADO** ✅
- **Descoberta importante (2026-04-20):** Bling v3 **não usa segredo HMAC separado**. A API assina automaticamente cada POST com o `client_secret` do próprio app OAuth. `BLING_WEBHOOK_SECRET` foi removido (settings + .env) porque não existe no Bling v3.
- **Validação aplicada em `apps/bling/views.py → webhook`:**
  - Header: `X-Bling-Signature-256` (formato `sha256=<hex>`)
  - Algoritmo: `HMAC-SHA256`
  - Chave: `settings.BLING_CLIENT_SECRET` (o mesmo usado no OAuth)
  - Requests sem assinatura válida → `401 Unauthorized`
- **Ação pendente no painel Bling (developer.bling.com.br):** cadastrar servidor em **Webhooks → Adicionar** apontando para `https://novo.dellainstore.com.br/bling/webhook/`. Não há campo de "chave secreta" — o Bling assina automaticamente.
- **Referência oficial:** https://developer.bling.com.br/webhooks

**3. Sanitização de `|safe` em páginas estáticas — IMPLEMENTADA** ✅
- Novo filter `{% load safe_html %}{{ ... |clean_html }}` em `apps/core_utils/templatetags/safe_html.py`.
- Usa `bleach.clean()` + `CSSSanitizer` (do pacote `bleach[css]` via `tinycss2`).
- Tags permitidas: formatação básica (`p`, `strong`, `em`, `a`, `img`, `h1-h6`, listas, tabelas).
- CSS inline permitido APENAS com propriedades listadas (`color`, `font-*`, `margin`, `padding`, etc). `url(javascript:...)` é neutralizado para `url([bad url])`.
- Protocolos aceitos em `href/src`: `http`, `https`, `mailto`, `tel` (bloqueia `javascript:`, `data:`).
- Templates atualizados: `sobre.html`, `_pagina_base.html`, `guia_tamanhos.html`.
- `tinycss2==1.5.1` adicionado ao `requirements.txt`.
- **Testes realizados:** `<script>`, `onclick`, `<iframe>`, `href="javascript:"` e `style="background:url(javascript:...)"` são sanitizados; tags legítimas preservadas.

### Dependências — versões disponíveis
- `Django 5.1.15 → 5.1.x` (LTS) — atualizar para o último patch da série 5.1 quando disponível; 5.1 recebe security fixes até abril/2028. Não subir para 5.2/6.0 sem regressão testada.
- `boto3 1.42.88 → 1.42.91` — patch trivial, update seguro (não urgente, o projeto usa pouco).
- `django-anymail 14 → 15` — major: revisar changelog antes de subir.
- Nenhuma CVE ativa nas versões atuais (Django 5.1.15 é a patch mais recente da LTS).

**4. `|safe` em templates estáticos (`pagina.conteudo|safe`)**
- Usado em `home/sobre.html`, `home/_pagina_base.html`, `home/guia_tamanhos.html`.
- O conteúdo vem de `PaginaEstatica.conteudo` (HTML rich text do admin).
- **Risco:** XSS se um admin comprometido injetar `<script>`. Mitigado por acesso restrito a staff e LGPD/axes.
- **Ação opcional:** filtrar o HTML com `bleach` (já no requirements) antes de salvar, permitindo apenas tags seguras.

### Testes efetuados na auditoria

```bash
# URLs testadas (todas retornam 403/404)
curl -sI https://novo.dellainstore.com.br/.env           → 403
curl -sI https://novo.dellainstore.com.br/.git/config    → 403
curl -sI https://novo.dellainstore.com.br/admin/.env     → 403
curl -sI https://novo.dellainstore.com.br/wp-admin       → 404
curl -sI https://novo.dellainstore.com.br/media/         → 403

# Headers de segurança confirmados
curl -sI https://novo.dellainstore.com.br/ | grep -iE "strict-transport|x-frame|csp|referrer"
# → Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
# → X-Frame-Options: DENY
# → Content-Security-Policy: ... (restritivo)
# → Referrer-Policy: strict-origin-when-cross-origin
```

### Recomendações gerais (próximos 30 dias)

1. **Rotacionar credenciais** se houver suspeita de vazamento (não há evidência de vazamento, mas rotação periódica é boa prática).
2. **Fazer backup diário do PostgreSQL** — configurar cron com `pg_dump` cifrado e guardar fora do VPS.
3. **Implementar LGPD:**
   - Rotina de anonimização de pedidos > 5 anos (prazo fiscal).
   - Limpeza de `BlingLog` > 180 dias.
   - Canal do titular de dados (formulário de direitos LGPD: acesso, correção, exclusão).
4. **Monitoramento:** ativar alertas de `django_error.log` para stack traces 500.

---

## Revisão de Segurança — 2026-04-18 (Cache Layer)

Revisão focada nas mudanças da camada de cache (`apps/core_utils/cache_utils.py`, `verificar_cache.py`, invalidações nos admins, caching em `views.py` e `context_processors.py`).

**Resultado: nenhuma vulnerabilidade identificada.** Aprovado para produção.

### Pontos inspecionados sem findings

| Aspecto | Resultado |
|---|---|
| Chaves de cache | Constantes hardcoded — sem interpolação de input externo |
| Dados cacheados | Apenas conteúdo público (banners, produtos, categorias) — nenhum dado de usuário autenticado |
| Importação Instagram | Restrita a staff (`admin_view()`); URL da imagem vem de API autenticada do Facebook |
| FileBasedCache + Pickle | Exploit exige escrita prévia no filesystem — acesso já comprometido |
| CSRF nos endpoints GET do admin Instagram | Impacto seria apenas importar posts públicos; abaixo do limiar de risco |

---

## Auditoria de Segurança — 2026-04-14

Auditoria completa rodada nesta data. Resultado detalhado abaixo — usar como baseline antes de migrar o domínio definitivo.

---

## Revisão de Segurança/LGPD — 2026-04-16

Segunda rodada de correções. Todos os itens abaixo foram implementados, validados com `py_compile` e commitados.

### ✅ Correções aplicadas nesta sessão

**S1 — IDOR em `detalhe_pedido` (`apps/pedidos/views.py`)** (ALTO)
- Antes: `if pedido.cliente and request.user.is_authenticated:` — se `cliente=None` (guest checkout), o bloco era ignorado e qualquer pessoa com o número acessava nome, e-mail, CPF, endereço e itens.
- Depois: usa `_pode_acessar_pedido` (mesmo pattern de `confirmacao_pedido`) — apenas staff, dono logado ou número na sessão do guest.

**S2 — Webhook Bling sem validação de origem (`apps/bling/views.py:webhook`)** (ALTO)
- Antes: `@csrf_exempt` + sem verificação → POST anônimo podia alterar status/rastreio de qualquer pedido.
- Depois: se `BLING_WEBHOOK_SECRET` estiver no `.env`, valida `X-Bling-Signature` via HMAC-SHA256 do body. Se vazio, loga `WARNING` e processa (retrocompat). **Estrutura pronta — ativar configurando o segredo.**
- Setting adicionado em `core/settings/base.py`: `BLING_WEBHOOK_SECRET = config('BLING_WEBHOOK_SECRET', default='')`.

> **Ação necessária:** gerar um segredo forte, adicionar em `.env` como `BLING_WEBHOOK_SECRET=<valor>` e cadastrar o mesmo no painel Bling → Integrações → Webhooks → Chave de assinatura.

**S3 — Dados de cartão transitando pelo backend (`templates/checkout/index.html`)** (CRÍTICO/PCI)
- Antes: campos PAN/CVV com `name=` eram submetidos ao backend diretamente.
- Depois (2026-04-16): aba desabilitada temporariamente. Campos PAN/CVV removidos.
- Depois (2026-04-17): **cartão reativado** com tokenização correta. O `templates/checkout/index.html` carrega o SDK `direct-checkout.js` do PagBank, chama `PagSeguro.encryptCard()` no frontend e envia apenas o `encryptedCard` ao backend. PAN nunca chega ao servidor.

**S4 — Tokens Bling em texto claro no admin (`apps/bling/admin.py`)** (MÉDIO)
- Antes: `readonly_fields` exibia `access_token` e `refresh_token` completos na tela de detalhes.
- Depois: substituído por `access_token_mascarado` e `refresh_token_mascarado` — exibem apenas os 8 primeiros chars + `••••••••••••••••••••` + últimos 4. Fluxo OAuth/refresh inalterado.

**S5 — PII nos logs Bling (`apps/bling/services.py` + `apps/bling/admin.py`)** (MÉDIO/LGPD)
- Antes: `BlingLog.payload_enviado` armazenava CPF, e-mail, telefone, nome e endereço completo do cliente.
- Depois: `_redact_payload_pii(payload)` em `services.py` aplica `[REDACTED]` nos campos `cpfCnpj`, `email`, `telefone`, `enderecos`, `nome` do bloco `contato` antes de gravar. Diagnóstico preservado (número do pedido, itens, totais).
- Admin `BlingLogAdmin`: `payload_enviado` removido de `readonly_fields`; substituído por `payload_resumo` que exibe apenas campos não-sensíveis (`numero`, `itens`, `total`, `situacao`).

---

### ✅ Correções já aplicadas (sessão 2026-04-14)

**C1 — IDOR em `pix_gerar`, `pix_status` e `confirmacao_pedido`** (CRÍTICO)
- Depois: nova helper `_pode_acessar_pedido(request, pedido)` em `apps/pagamentos/views.py` — autoriza apenas staff, dono logado, ou número presente em `session['pedidos_guest']` / `session['ultimo_pedido']`. `confirmacao_pedido` usa a mesma regra unificada.
- `apps/pedidos/views.py → _processar_checkout` registra cada pedido em `session['pedidos_guest']` (limite: últimos 20).

**C4 — OAuth Bling validando `state`** (CRÍTICO)
- `apps/bling/views.py`: `oauth_autorizar` gera `secrets.token_urlsafe(32)`. `oauth_callback` compara com `secrets.compare_digest`.

**M1 — `.env` com permissão 600** ✅

**A1 — Upload sem validação (magic bytes)** ✅

**A2 — Vídeos de banner sem validação** ✅

**M2 — `CSRF_TRUSTED_ORIGINS` explícito** ✅

---

### ⏳ Pendências — ordenadas por prioridade

**C2 — Webhook Bling (HMAC)** — estrutura implementada (S2), falta **ativar**
- Gerar segredo: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- Adicionar ao `.env`: `BLING_WEBHOOK_SECRET=<valor_gerado>`
- Cadastrar o mesmo valor no painel Bling → Integrações → Webhooks → Chave de assinatura
- Reiniciar Gunicorn após alterar o `.env`

**C3 — Webhooks Stone sem assinatura** — quando ativar Stone
- Stone: validar header `X-Stone-Signature` (HMAC) antes de processar.

**M3 — CSP com `'unsafe-inline'`** — médio prazo
- Compilar Tailwind localmente para remover `'unsafe-inline'` de `script-src`.

**LGPD — Retenção de `BlingLog`** — ação operacional
- Logs nunca são deletados automaticamente. Implementar rotina de limpeza periódica (ex: cron que apaga registros com mais de 180 dias).

**LGPD — Retenção de dados de pedidos antigos** — revisão futura
- Pedidos guardam CPF, e-mail, endereço indefinidamente. Avaliar política de anonimização após prazo fiscal (5 anos).

---

### ✅ Pontos bons — não regredir

- `.env` fora do git; `SECRET_KEY` via `config()`; `ALLOWED_HOSTS` explícito
- HSTS 1 ano + preload, `SECURE_SSL_REDIRECT`, cookies `Secure + SameSite=Lax`
- `X-Frame-Options: DENY` (Django + Nginx)
- django-axes 5 tentativas → 1h lockout por IP+user
- auto-escape template ON, ORM-only (zero SQL raw)
- recuperação de senha não enumera e-mails
- `next_url` validado (`startswith('/')`) no login
- Nginx bloqueia `.env`, `.git`, `.sql`, scripts em `/media/`
- CSRF em todos os forms; `CSRF_TRUSTED_ORIGINS` configurado

### Helper reutilizável: `_pode_acessar_pedido`
Toda nova view que expõe dados de `Pedido` deve usar este pattern (em `apps/pagamentos/views.py`):
```python
def _pode_acessar_pedido(request, pedido) -> bool:
    if request.user.is_authenticated:
        if request.user.is_staff: return True
        if pedido.cliente_id and pedido.cliente_id == request.user.id: return True
    numero = pedido.numero
    if numero == request.session.get('ultimo_pedido'): return True
    if numero in request.session.get('pedidos_guest', []): return True
    return False
```

---

## Design System

| Token | Valor |
|---|---|
| Cor preto | `#0a0a0a` |
| Cor branco | `#fafafa` |
| Cor dourado | `#c9a96e` |
| Cor dourado claro | `#e8d5b0` |
| Cor cinza claro | `#f5f5f3` |
| Fonte títulos | `Playfair Display` (serif) |
| Fonte corpo | `Jost` (sans-serif) |
| Navbar total height | `--navbar-total: 96px` (60px topo + 36px categorias) |
| Transição padrão | `all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94)` |

---

## Variáveis de Ambiente (`.env`)

```
SECRET_KEY=...
DEBUG=False
ALLOWED_HOSTS=novo.dellainstore.com.br,www.dellainstore.com.br,dellainstore.com.br,www.dellainstore.com,dellainstore.com,159.203.101.232
DB_NAME=della_site
DB_USER=della_user
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
BREVO_API_KEY=...   ← e-mail via Brevo API (Digital Ocean bloqueia SMTP)
BLING_CLIENT_ID=23672393b3c0bdb7090fec018f92efe0d6f86027
BLING_CLIENT_SECRET=...
BLING_REDIRECT_URI=https://novo.dellainstore.com.br/bling/callback/
WHATSAPP_NUMBER_1=5511988879928
INSTAGRAM_ACCESS_TOKEN=   ← vazio por enquanto (banner estático ativo)
MELHOR_ENVIO_TOKEN=...
MELHOR_ENVIO_SANDBOX=False
PIX_CHAVE=29049870000137
SITE_URL=https://novo.dellainstore.com.br
```

---

## Melhor Envio — Cálculo de Frete (apps/pagamentos/services/melhorenvio.py)

- **Token:** `MELHOR_ENVIO_TOKEN` no `.env` | **Modo:** `MELHOR_ENVIO_SANDBOX=False` (produção)
- **CEP de origem:** `MELHOR_ENVIO_CEP_ORIGEM` no `.env` (fallback: `01310100`)
- **Serviços consultados:** `1=PAC Correios`, `2=SEDEX Correios`
- **Caixa padrão D'ELLA:** `DIMENSOES_PADRAO = {width:17, height:8, length:28, weight:0.5}` (cm/kg por peça)
- **Fallback:** quando sem token ou erro, retorna PAC R$18.90 / SEDEX R$34.90 estimados
- **Retry CEP 422:** se a API rejeitar o CEP com HTTP 422, tenta novamente com CEP raiz (`cep[:5] + '000'`). Alguns CEPs válidos são rejeitados pelo Melhor Envio; o CEP raiz geralmente é aceito com prazo/preço equivalente
- **IDs de serviço** (`frete_servico_id` no model `Pedido`): `'1'` = PAC, `'2'` = SEDEX. `max_length=20` no campo (aumentado de 10 para suportar os IDs)

---

## PagSeguro (PagBank) — Integração ativa

- **Token:** produção, configurado em `.env` como `PAGSEGURO_TOKEN`
- **Sandbox:** `PAGSEGURO_SANDBOX=False` (produção ativa)
- **Endpoint público-key correto:** `GET /public-keys/card` (não `/public-keys/CREDIT_CARD` — legado, retorna 404)
- **Fluxo cartão:** frontend carrega SDK → `PagSeguro.encryptCard()` → envia `encrypted_card` → backend chama `criar_ordem_cartao()` — PAN nunca toca o servidor
- **Webhook seguro (C3 implementado):** `pagseguro_notificacao` recebe o `order_id` do payload, reconsulta `GET /orders/{id}` na API PagBank de forma autenticada e só então atualiza o pedido — payloads forjados são descartados porque a reconsulta falha
- **Chave pública cacheada:** 1 hora (`pagseguro_public_key` no cache Django). Limpar com `cache.delete('pagseguro_public_key')` se precisar forçar renovação

### SDK do PagBank — URL atualizada (2026-04-20)

A URL antiga do SDK retorna **403 Forbidden** (descontinuada pelo PagBank sem aviso):
```
❌ https://assets.pagseguro.com.br/checkout-sdk/js/direct-checkout.js  ← 403, não usar
✅ https://assets.pagseguro.com.br/checkout-sdk-js/rc/dist/browser/pagseguro.min.js  ← ativa
```
O SDK é carregado **incondicionalmente** no `{% block js_extra %}` de `templates/checkout/index.html`, antes do handler de submit, para garantir que `PagSeguro` esteja definido quando o usuário submete o formulário.

### Pagamento com cartão — pendência PagBank (2026-04-20)

O frontend encripta o cartão corretamente (`PagSeguro.encryptCard()` retorna `encryptedCard`), mas o backend recebe `ACCESS_DENIED: whitelist access required` ao chamar `POST /orders`.

**Diagnóstico:** a conta PagBank não está habilitada para Checkout Transparente via API. O token tem acesso à API (GET /orders retorna 400, não 401/403), mas criar ordens com cartão exige liberação específica.

**Ações realizadas:**
- Domínio `https://novo.dellainstore.com.br` cadastrado em "URL do serviço de chave pública" no painel do PagBank
- Chamado aberto no suporte técnico PagBank (`https://dev.pagbank.uol.com.br` → Suporte) solicitando habilitação do Checkout Transparente

**Enquanto aguarda:** Pix funciona normalmente. Cartão fica bloqueado até PagBank liberar a conta.

---

## Atualizações 2026-04-20 (sessão tarde)

### Migração de clientes do site antigo

- **Campo `precisa_ativar`** adicionado ao model `Cliente` (migration `usuarios.0004`). Contas importadas sem senha recebem `precisa_ativar=True`.
- **Management command `importar_clientes`** (`apps/usuarios/management/commands/importar_clientes.py`): lê CSV com `;` ou `,`, detecta encoding automaticamente (latin-1/utf-8), aceita data no formato `MM/DD/AAAA HH:MM:SS`. Uso: `python manage.py importar_clientes arquivo.csv --dry-run --settings=core.settings.production`.
- **Fluxo de ativação:** na view `cadastro`, o CPF é verificado em `request.POST` **antes** do `form.is_valid()` — assim funciona mesmo que o e-mail já exista no banco. Se CPF existe + `precisa_ativar=True` → redireciona para `/conta/ativar/<uid>/<token>/`. Tela pede e-mail (confirma identidade) + nova senha → login automático + `precisa_ativar=False`.
- **View `ativar_conta`** em `apps/usuarios/views.py`. **Form `AtivacaoForm`** em `apps/usuarios/forms.py`. **Template** `templates/usuarios/ativar_conta.html`. **URL** `usuarios:ativar_conta`.

### Navbar — reestruturação

- **Nova ordem de ícones:** Busca → WhatsApp → Carrinho → Login/Nome.
- **Nome do usuário logado:** quando autenticada, exibe `{{ user.nome }}` ao lado do ícone de pessoa (`navbar-usuario-label` — uppercase, 0.72rem, truncado em 7rem). Quando não logada, exibe "Entrar".
- **`WHATSAPP_NUMBER_1` e `WHATSAPP_NUMBER_2` movidos para o context processor** `apps/produtos/context_processors.py → categorias_menu` — agora disponíveis em **todas** as páginas via contexto global. Antes só existiam no contexto da homepage.

### Página de produto — correções

- **Ícone "Adicionar ao carrinho":** trocado de `far fa-shopping-bag` (Pro, quebrava) para `fas fa-bag-shopping` (Free).
- **Texto wishlist:** "Adicionar à Lista de Desejos" / "Salvo na Lista de Desejos" (era "Salvar/Salvo na wishlist").
- **Seleção de cor/tamanho bidirecional:** ao carregar a página, todos os tamanhos ficam habilitados (antes ficavam todos desabilitados porque `corSelecionadaId=null` não existia no mapa). Selecionar cor → filtra tamanhos; selecionar tamanho → filtra cores. Ambos os sentidos funcionam independentemente.
- **Ícones da sidebar da conta:** `wishlist.html` usava `fa-regular` (Pro) nos ícones. Corrigido para `fas`/`far` (Free) — igual às outras páginas da área do cliente.

---

## Atualizações 2026-04-20

### Correções de UX — Cadastro / Login / Navbar

- **CPF `maxlength` correto:** o model tem `max_length=11` (sem formatação), mas Django renderizava `maxlength="11"` no input, bloqueando a digitação da máscara `000.000.000-00` (14 chars). Solução: declarar o campo `cpf` explicitamente em `CadastroForm` com `max_length=14` fora do Meta. **Padrão a seguir:** todo campo onde o valor formatado é maior que `max_length` do model deve ser declarado explicitamente no form (não via `Meta.widgets`).
- **CEP `maxlength` correto:** mesmo problema em `EnderecoForm` — CEP stored como 8 dígitos, mas formato `00000-000` tem 9 chars. Mesmo fix: `cep` declarado explicitamente com `max_length=9`.
- **Nome completo unificado:** `CadastroForm` passou de dois campos (`nome` + `sobrenome`) para um único campo `nome` com placeholder "Nome completo". O `save()` divide automaticamente: primeira palavra → `nome`, resto → `sobrenome`. Modelo e migrations não foram alterados.
- **Checkout exige login:** `@login_required(login_url='/conta/entrar/')` adicionado à view `checkout` em `apps/pedidos/views.py`. Quem tenta acessar sem login é redirecionado com `?next=/checkout/` e volta automaticamente após autenticar.
- **"Criar conta grátis" → "Criar conta":** texto do link na página de login simplificado.
- **Termos de uso no cadastro:** checkbox agora usa `:not([type="checkbox"])` no seletor `.conta-campo input` para não receber estilos de campo de texto. Tamanho fixo `18×18px` com `accent-color: var(--preto)`.
- **Logo mobile:** no breakpoint ≤768px, `--navbar-total` é redefinido para `var(--navbar-topo-h)` (60px), removendo o overflow da logo de 96px sobre o conteúdo. Logo posicionada em `left: 3rem` para não sobrepor o hamburger.
- **Separador da navbar:** linha entre topo e categorias agora usa `::before` pseudo-elemento centralizado (60% da largura, máx 780px) — não vai de ponta a ponta da tela.
- **Área da conta (padding):** `.conta-area` usa `padding: calc(var(--navbar-total) + 4rem) 1.5rem 4rem` para que o conteúdo não fique colado à navbar. Vale para todas as páginas da conta (Início, Meus Pedidos, Endereços, etc.).
- **Badge de quantidade no resumo do checkout:** `.resumo-item-foto` recebeu `overflow: visible` para o badge circular não ser cortado.

### Carrinho e Página de Produto

- **Botão "Adicionar" nas listagens (loja e home):** ao clicar no ícone de sacola em qualquer card de produto fora da página de detalhe, o cliente é redirecionado para a página do produto (não adiciona mais sem cor/tamanho). O botão recebe `data-produto-url` e o JS verifica: se não houver `data-variacao-id`, faz `window.location.href = produtoUrl`.
- **Filtro bidirecional cor↔tamanho:** na página de detalhe, clicar em um tamanho agora também filtra/desabilita as cores indisponíveis para aquele tamanho (função `atualizarDisponibilidadeCores()`). Antes só cor → tamanhos era tratado. Agora ambos os sentidos funcionam.
- **Descrição de variação no carrinho:** `carrinho.py` usa `_desc_variacao(variacao)` que retorna apenas `"Cor / Tam. X"` (ex: `"Preto / Tam. P"`), sem repetir o nome do produto. Exibido no drawer lateral e no resumo do checkout via `item.variacao`.
- **Foto por cor no carrinho:** `carrinho.py → adicionar()` verifica `ProdutoCorFoto` pela cor da variação selecionada antes de usar `imagem_principal`. Se encontrar foto da cor, usa ela; caso contrário cai no fallback `produto.imagem_principal`. Garante que ao adicionar "Body Preta" o drawer mostre a foto preta, não a foto padrão.
- **Botão remover no resumo do checkout:** cada item do resumo lateral (`templates/checkout/index.html`) tem botão de lixeira vermelho ao lado dos botões +/−. Envia `quantidade: 0` para `/carrinho/atualizar/` via AJAX e remove o elemento do DOM imediatamente. CSS: `.resumo-remover-btn` em `della.css`.
- **Bug subtotal ao remover item no checkout:** `window.SUBTOTAL` (usado por `atualizarResumoTotal()` ao selecionar frete) é atualizado via `window.SUBTOTAL = novoSubtotal` no handler AJAX do resumo. Sem isso, ao selecionar o frete após remover um item, o total voltava com o valor original da página.
- **E-mail de confirmação de pedido:** `bcc=['financeiro@dellainstore.com.br']` adicionado em `apps/pedidos/emails.py → enviar_confirmacao_pedido`. Todo pedido novo envia cópia interna automaticamente.
- **Tela de confirmação — cartão aprovado:** `templates/checkout/confirmacao.html` verifica `pedido.status == 'pagamento_confirmado'` e exibe badge verde "Pagamento Confirmado" em vez de "Em processamento".

### Correções 2026-04-21

- **PIX checkout — crash corrigido:** `frete_servico_id` tinha `max_length=10` mas IDs do fallback Melhor Envio eram maiores. Aumentado para 20, migration `pedidos.0006` aplicada. IDs de fallback alterados de `'pac_fallback'`/`'sedex_fallback'` para `'pac'`/`'sedex'`.
- **Validação de cor/tamanho — Adicionar ao carrinho:** botão bloqueado se cor ou tamanho não estiver selecionado. Aviso `#aviso-variacao` exibido inline em `templates/produtos/detalhe.html`. Handler do `btn-adicionar-carrinho` retorna antes de enviar ao carrinho.
- **Validação de cor/tamanho — Comprar agora:** mesmo bloqueio aplicado no handler do `btn-comprar-agora`. Além disso, `static/js/della.js` foi corrigido: adicionado `if (btn.id === 'btn-comprar-agora') return;` no handler global `[data-produto-id]` que estava disparando independentemente da validação do template, causando bypass.
- **Bling — webhook PIX confirmado:** `_MAPA_SITUACAO` em `apps/bling/views.py` incluiu `18723: 'pagamento_confirmado'` (Atendido - Site, custom D'ELLA) para que o admin moverem o pedido no Bling confirme automaticamente o PIX no Django.
- **Bling — situação correta ao criar pedido:** `SITUACAO_EM_ANDAMENTO_SITE` corrigido de `6` (Em aberto) para `754756` (Em andamento - Site, custom D'ELLA — verificado via API no pedido 9638).
- **Bling — descrição dos itens:** formato corrigido para `NOME PRODUTO (COR) (TAMANHO)` ex: `BODY BASIC ANACA (BRANCO POLAR) (P)`. Lê das FKs `variacao.cor.nome` e `variacao.tamanho.nome` via `select_related`. Fallback: parse do campo `variacao_desc` salvo no `ItemPedido`.
- **Bling — código do produto (`codigo`) corrigido:** `bling_variacao_id` (ex: '15910731466') é o **ID interno** do Bling e não é o código do catálogo. Corrigido em `apps/bling/services.py → _montar_payload_pedido`: agora usa `item.sku` como fonte primária (salvo no checkout como `sku_variacao`, ex: '4604'). Fallback: `variacao.sku_variacao` → `produto.sku`. O `bling_variacao_id` foi removido da lógica de `codigo`.
- **Bling — transporte completo:** payload inclui `logistica: {nome: 'Melhor Envio - Correios'}`, dimensões da caixa (peso 0.5kg, 17×8×28cm) e `fretePorConta` automático.
- **Checkout resumo — botão remover:** botão de lixeira vermelho por item no resumo lateral. Bug de total ao remover corrigido: `window.SUBTOTAL` atualizado no callback AJAX + `atualizarResumoTotal()` chamada após remoção.
- **Carrinho — foto por cor:** `carrinho.py → adicionar()` busca `ProdutoCorFoto` pela cor da variação selecionada antes de usar `imagem_principal`.
- **Melhor Envio — CEP inválido (422):** alguns CEPs válidos são rejeitados pela API do Melhor Envio com HTTP 422. Solução: ao receber 422, o sistema tenta novamente com o CEP raiz (`cep[:5] + '000'`). Ex: CEP `14401385` → retry com `14401000`.
- **PIX QR Code — expiração de 10 minutos:** tela de confirmação tem countdown `MM:SS`. Após expirar, esconde o QR e exibe bloco com botão "Gerar novo QR Code" (AJAX para `/pagamento/pix/gerar/<numero>/`). Polling de status a cada 30s enquanto aguarda confirmação.
- **Carrinho — diminuir qty de 1 remove o item:** `atualizar_carrinho` em `views.py` chama `cart.remover(chave)` quando `quantidade <= 0`. Antes ficava preso em 1.
- **Admin — select boxes em inlines:** CSS em `della_admin.css` com `height: auto`, `min-height: 2.2rem`, `line-height: 1.4` nos selects de inlines tabular. Remove o clipping vertical do texto. **Não usar `overflow: visible`** — causa o texto `.original` vazar sobre o select.
- **Admin — widget de senha:** criado `templates/auth/widgets/read_only_password_hash.html` customizado. Exibe apenas dicas de requisitos (maiúscula, número, especial) em vez do hash/algoritmo Django padrão.
- **Carrinho — foto por cor:** `carrinho.py → adicionar()` busca `ProdutoCorFoto` pela cor da variação. Mostrava sempre a foto padrão independente da cor selecionada.
- **Checkout resumo — botão remover:** botão de lixeira vermelho por item. Bug de subtotal ao remover corrigido (`window.SUBTOTAL` atualizado no callback AJAX).
- **Bling — formato descrição:** itens enviados como `NOME (COR) (TAMANHO)` (ex: `BODY BASIC ANACA (BRANCO POLAR) (P)`). Antes usava `NOME — Cor / Tam. X`.
- **Bling — transporte completo:** payload agora inclui `logistica: {nome: 'Melhor Envio - Correios'}`, dimensões da caixa (peso 0.5kg, 17×8×28cm) e `fretePorConta` automático (1=FOB/cliente paga, 0=CIF/frete grátis).
- **Bling — situação correta:** `SITUACAO_EM_ANDAMENTO_SITE` corrigido de `6` (Em aberto, padrão Bling — errado) para `754756` (Em andamento - Site, custom D'ELLA, verificado via API no pedido 9638).

### Correções Admin (2026-04-20)

- **CEP — busca automática corrigida:** `templates/usuarios/endereco_form.html` usava `/carrinho/cep/?cep=${cep}` (query param), mas a URL espera `/carrinho/cep/<cep>/` (path param). Corrigido para `/carrinho/cep/${cep}/`.
- **Admin — campos cortando informações (overflow):** `#content .module` tem `overflow: hidden` necessário para border-radius, mas cortava a tabela de resultados e os inlines de variações. Solução: adicionar `overflow-x: auto` em `#changelist-form .results` e `.tabular.inline-related` — o conteúdo das colunas pode rolar horizontalmente sem cortar. `.inline-group` também mudou de `overflow: hidden` para `overflow-x: auto`.
- **Admin — date hierarchy afastado da borda esquerda:** filtro de datas ("2026 / abril / 13 de abril") renderizado em `.xfull` sem padding. Adicionado `.xfull { padding-left: 0.9rem !important; }` em `della_admin.css`.
- **Admin — exportar CSV de produtos:** novo botão verde "Exportar CSV" na listagem de produtos (`/painel/produtos/produto/`). Exporta todos os produtos com variações ativas no mesmo formato do CSV de importação (`nome, categoria, descricao, composicao, genero, preco, preco_promocional, ativo, destaque, novo, bling_id, sku, var_cor, var_tamanho, var_estoque, var_sku, var_bling_id`). URL: `/painel/produtos/produto/exportar-csv/`. Método `_exportar_csv` em `apps/produtos/admin.py`. Botão adicionado em `templates/admin/produtos/produto_changelist.html`.

---

## Funcionalidades recentes (2026-04-17 — atualizado)

- **Meus Pedidos** (`/conta/pedidos/`): lista pedidos do cliente com status badges e link para detalhe.
- **Detalhe do Pedido** (`/conta/pedido/<numero>/`): exibe itens, resumo (subtotal, desconto, frete, total), endereço e — se `status=aguardando_pagamento` — seção de repagamento com QR Code Pix + botão copiar + aba "Cartão" (Em breve). Template: `templates/usuarios/detalhe_pedido.html`. View: `apps/usuarios/views.py → detalhe_pedido`.
- **Cupom + Código de Vendedor** no checkout: campos recolhíveis (`<details>`) com validação AJAX. Desconto aparece no resumo em tempo real. Admin: `Pedidos → Cupons` e `Pedidos → Códigos de vendedor`. Models: `Cupom` e `CodigoVendedor` em `apps/pedidos/models.py`. Migration: `0004`.
- **Auto-cancelamento de pedidos**: `python manage.py cancelar_pedidos_expirados --dias 2` — cancela `aguardando_pagamento` com mais de N dias. Agendar via cron.
- **E-mail via Brevo API** (`django-anymail[brevo]`): Digital Ocean bloqueia todas as portas SMTP (25/465/587). Solução: Brevo API HTTP (porta 443). Backend: `anymail.backends.brevo.EmailBackend`. Configurar `BREVO_API_KEY` no `.env`. Domínio `dellainstore.com.br` autenticado no Brevo (DKIM1, DKIM2, DMARC, Código Brevo — registros DNS na UOL). Plano Free: 300 e-mails/dia.
- **Admin — padrão unificado em TODOS os menus**:
  - `get_actions` retorna apenas `delete_selected` → checkboxes para exclusão em massa, sem dropdown desnecessário
  - `admin_linhas.js` injetado via `class Media` → clique na linha navega para edição
  - Botões por linha usam **classes CSS** (`della-btn-edit`, `della-btn-delete`) — não estilos inline
  - Arquivos atualizados: `bling/admin.py`, `conteudo/admin.py`, `pagamentos/admin.py`, `pedidos/admin.py`, `produtos/admin.py`, `usuarios/admin.py`
- **Admin — menu lateral não sobe mais**: `base_site.html` tem `<script>` inline que persiste scroll em **todas** as páginas (não depende do `admin_linhas.js` que só carrega em algumas).
- **Admin — Bling tokens**: botões "Atualizar Token" e "Re-autorizar" empilhados verticalmente (`flex-direction:column`) para não cortar em colunas estreitas.
- **Homepage**: "Destaques da Semana" com S maiúsculo. "Look da **Semana**" também com S maiúsculo.
- **Footer**: item "Perguntas frequentes" removido da coluna "Ajuda" (continua acessível via URL direta).
- **Páginas estáticas indisponíveis**: fallback mostra "Esta página está temporariamente indisponível." (guia de tamanhos, perguntas frequentes, modal de tamanhos no detalhe do produto).
- **Bling — integração bidirecional** (2026-04-17): pedido criado → `Em andamento - Site`; pagamento confirmado → `Atendido - Site`; cancelamento → `Cancelado` + restaura estoque. Ver seção "Bling — Integração Bidirecional" acima.
- **Estoque site**: diminui no checkout dentro de `transaction.atomic()` com `Greatest(F('estoque') - qty, Value(0))`; restaura no cancelamento.

### Feed do Instagram (2026-04-17)

- **Model `InstagramPost`** (`apps/conteudo/models.py`): armazena posts importados localmente — `instagram_id`, `media_type`, `imagem_local` (ImageField `upload_to='instagram/'`), `permalink`, `caption`, `timestamp`, `ativo`, `ordem`. Property `imagem_url` retorna URL da imagem local.
- **Importação manual** via admin (Conteúdo do Site → Posts Instagram):
  - **"↻ Atualizar (últimos 30)"** — busca 1 página (30 posts recentes), para se tudo já foi importado. Para uso semanal, rápido.
  - **"↓ Importar histórico completo"** — busca todos os posts **desde 01/01/2025** (`since=1735689600`) sem limite de páginas. Para uso inicial.
  - Imagens são **baixadas e salvas localmente** (`media/instagram/`) — sem dependência de URLs expiráveis do CDN do Instagram.
  - Vídeos usam `thumbnail_url` (não `media_url` que é .mp4). Posts já importados são ignorados.
  - Após importar, marcar "Exibir no site" (ativo=True) nos posts desejados.
- **Token**: System User token do Meta Business (nunca expira, `expires_at=0`). Endpoint: `graph.facebook.com/v19.0/{INSTAGRAM_ACCOUNT_ID}/media`.
- **Homepage**: grid `repeat(6, 1fr)`, **sem gap (`gap:0`)**, ocupa 100% da largura (edge-to-edge, igual ao banner hero). Header "@dellainstore" centralizado acima. Vídeos exibem thumbnail estático — ao clicar abre o post no Instagram. **Site exibe máx. 12 posts** (2 linhas × 6 colunas).
- **Admin**: contador "📸 X de Y exibindo no site" no topo da listagem. Aviso em vermelho se > 12 marcados. `list_per_page=200` (sem paginação). Posts ativos aparecem no topo (`ordering = '-ativo', 'ordem', '-timestamp'`).
- **Fallback**: se nenhum post estiver ativo, exibe banner estático CTA "@dellainstore".

### Padrão admin_linhas.js (como aplicar em novos admins)

```python
class Media:
    js = ('admin/js/admin_linhas.js',)

def get_actions(self, request):
    actions = super().get_actions(request)
    return {k: v for k, v in actions.items() if k == 'delete_selected'}

def acoes_linha(self, obj):
    from django.urls import reverse
    from django.utils.html import format_html
    edit_url   = reverse('admin:APP_MODEL_change', args=[obj.pk])
    delete_url = reverse('admin:APP_MODEL_delete', args=[obj.pk])
    return format_html(
        '<a href="{}" class="della-btn-edit">✎ Editar</a>'
        '<a href="{}" class="della-btn-delete" onclick="return confirm(\'Excluir?\')">✕ Excluir</a>',
        edit_url, delete_url,
    )
acoes_linha.short_description = 'Ações'
# Adicionar 'acoes_linha' em list_display e list_display_links = ('<campo_link>',)
# IMPORTANTE: usar classes CSS (della-btn-edit / della-btn-delete) — NUNCA estilos inline
```

## Estratégia de Cache (2026-04-18)

### Configuração base
- **Backend:** `FileBasedCache` em `BASE_DIR/cache/` — compatível com múltiplos workers Gunicorn
- **Timeout padrão:** 1 hora (configurado em `CACHES` em `core/settings/base.py`)
- **`apps.core_utils` adicionado ao `INSTALLED_APPS`** — necessário para os management commands

### Helper centralizado: `apps/core_utils/cache_utils.py`
Todas as chaves de cache e funções de invalidação ficam aqui. **Sempre usar este módulo** ao adicionar novo cache — nunca hardcodar chaves espalhadas pelo código.

```python
from apps.core_utils.cache_utils import (
    MENU_CATEGORIAS, HOME_BANNERS, HOME_MINI_BANNERS, HOME_LOOK,
    HOME_DEPOIMENTOS, HOME_DESTAQUES, LOJA_CONFIG, GUIA_TABELAS,
    _key_pagina, _key_relacionados, _key_tabela_medidas,
    invalidar_categorias, invalidar_banners, invalidar_look,
    invalidar_pagina, invalidar_config_loja, invalidar_categoria_produtos,
    invalidar_home_completa,
)
```

### O que está cacheado e por quanto tempo

| Chave | TTL | Onde é preenchido | Onde é invalidado |
|---|---|---|---|
| `menu_categorias_ativas` | 4h | `context_processors.py` + `views.loja` | `CategoriaAdmin.save_model/delete_model` |
| `home_banners` | 1h | `views.homepage` | `BannerPrincipalAdmin.save_model/delete_model` |
| `home_mini_banners` | 1h | `views.homepage` | `MiniBannerAdmin.save_model/delete_model` |
| `home_look_semana` | 1h | `views.homepage` | `LookDaSemanaAdmin.save_model/delete_model` |
| `home_depoimentos` | 6h | `views.homepage` | (expira sozinho — moderação manual é rara) |
| `home_produtos_destaque` | 2h | `views.homepage` | `ProdutoAdmin.save_model/delete_model` |
| `loja_config` | 24h | `views.detalhe_produto` | `ConfiguracaoLojaAdmin.save_model` |
| `guia_tabelas_medidas` | 24h | `views.guia_tamanhos` | (expira sozinho) |
| `pagina_estatica_{slug}` | 6h | `views._pagina_estatica` | `PaginaEstaticaAdmin.save_model/delete_model` |
| `produtos_relacionados_{cat_id}` | 3h | `views.detalhe_produto` | `ProdutoAdmin` + `CategoriaAdmin` |
| `tabela_medidas_{cat_id}` | 12h | `views.detalhe_produto` | `CategoriaAdmin.save_model/delete_model` |
| `pagseguro_public_key` | 1h | `pagamentos/services/pagseguro.py` | `cache.delete('pagseguro_public_key')` manual |

### Invalidação no admin — padrão implementado
Todo `ModelAdmin` que afeta conteúdo cacheado implementa `save_model` e `delete_model` chamando a função correspondente do `cache_utils`. Ao salvar/deletar no painel, o cache é limpo imediatamente — sem risco de exibir conteúdo desatualizado.

### Cron de verificação de cache — a cada 6 horas
```
0 */6 * * * cd /var/www/.../site_della && source venv/bin/activate && python manage.py verificar_cache --settings=core.settings.production >> logs/verificar_cache.log 2>&1
```
- **O que faz:** compara IDs dos objetos cacheados com o banco; remove entradas com objetos deletados
- **Log:** `logs/verificar_cache.log`
- **Modo leitura:** `python manage.py verificar_cache --so-relatorio` (não altera nada)
- **Arquivo:** `apps/core_utils/management/commands/verificar_cache.py`

### Ambiente de produção vs sandbox

| Serviço | Status |
|---|---|
| PagSeguro | **PRODUÇÃO** (`PAGSEGURO_SANDBOX=False`) |
| Melhor Envio | **PRODUÇÃO** (`MELHOR_ENVIO_SANDBOX=False`) |
| Stone | Sandbox (`STONE_SANDBOX=True`) — Stone ainda não ativo |
| Bling | Sem sandbox — conectado direto à conta real |

---

## Atualizações 2026-04-22

### Bling — produto vinculado ao catálogo via `produto.id`

- **Problema:** Bling exibia ⚠️ "Produto não encontrado no sistema" mesmo com `codigo` correto.
- **Causa:** o Bling usa o campo `codigo` (SKU textual) para display, mas a vinculação ao catálogo usa o **ID interno** do produto/variação.
- **Correção em `apps/bling/services.py → _montar_payload_pedido`:** payload de cada item agora inclui `produto: {'id': bling_variacao_id}` quando disponível. Prioridade: `variacao.bling_variacao_id` → fallback `produto.bling_id`. Conversão para `int()` com try/except para evitar crash se o campo estiver com valor textual.
- `codigo` continua sendo enviado (útil para exibição no Bling).

### Frete — cálculo consistente entre página de produto e checkout

- **Causa raiz:** `{{ produto.preco_atual }}` renderizava como `"326,00"` (locale pt-br), e `float("326,00")` no Python falhava silenciosamente retornando `0`. Com `insurance_value = 0` (mínimo) na página do produto e `insurance_value = cart.get_total()` no checkout, o Melhor Envio retornava preços diferentes para o mesmo CEP.
- **Correção 1 — template `templates/produtos/detalhe.html`:** adicionado `{% load l10n %}` no topo; `data-preco="{{ produto.preco_atual|unlocalize }}"` garante saída com ponto decimal (ex: `326.00`).
- **Correção 2 — `apps/pedidos/views.py → calcular_frete`:** lógica refatorada: se `preco` estiver nos GET params, usa esses valores diretamente (ignora carrinho) — garante que a página de produto sempre calcule com base no produto sendo visto, independente do estado do carrinho. Safety net: `.replace(',', '.')` antes do `float()`. Contexto sem `preco`: usa o carrinho normalmente (checkout).

### PIX — confirmação automática via PagBank API

- **Problema anterior:** QR code era gerado localmente (padrão EMV estático com chave CNPJ). O pagamento ia direto ao banco D'ELLA sem passar pelo PagBank — nenhum webhook era disparado, pedido ficava em `aguardando_pagamento` para sempre.
- **Solução implementada:** tanto `confirmacao_pedido` (`apps/pedidos/views.py`) quanto `pix_gerar` (`apps/pagamentos/views.py`) agora tentam criar uma ordem PIX via PagBank API antes de gerar QR estático.

**Fluxo `criar_ordem_pix` (`apps/pagamentos/services/pagseguro.py`):**
```python
POST /orders
{
  "reference_id": "DI-XXXX",
  "customer": {nome, email, tax_id (CPF)},
  "items": [{"name": "Pedido DI-XXXX", "quantity": 1, "unit_amount": <centavos>}],
  "qr_codes": [{"amount": {"value": <centavos>}, "expiration_date": "<+24h>"}],
  "notification_urls": ["https://.../pagamento/pagseguro/notificacao/"]
}
```

- Resposta: `qr_codes[0].text` = payload copia-e-cola; `id` = PagBank order ID (ex: `ORDE_xxx`).
- O `pedido.gateway_id` é atualizado com o PagBank order ID para rastreamento.
- **Fallback automático:** se PagBank retornar erro (ex: `ACCESS_DENIED`), usa o QR estático local. O campo `via` na resposta JSON indica `"pagseguro"` ou `"estatico"`.

**Webhook atualizado (`apps/pagamentos/views.py → pagseguro_notificacao`):**
- Antes: só tratava `charges` (cartão).
- Agora: verifica `charges` primeiro; se vazio, verifica `qr_codes[0].status` (PIX). Isso cobre o fluxo PagBank PIX em que o pagamento confirma via qr_code e não necessariamente cria um charge separado.

**Financeiro:** pagamentos via PagBank PIX vão para o **saldo da conta PagBank** (não direto ao banco). Transferência manual/automática via painel PagBank. Próximo passo planejado: integração direta com API PIX do banco (Opção C) para que o valor vá direto ao banco com confirmação automática.

### Preços — separador de milhar (1.000,00 / 10.000,00)

- **Todos os templates** de exibição de preço atualizados de `floatformat:2` para `floatformat:"2g"`.
- O flag `"g"` ativa o separador de milhar respeitando o locale ativo (`pt-br`): ponto como separador de milhar, vírgula como decimal. Ex: `1234.56` → `"1.234,56"`.
- **Exceções protegidas** (contextos JavaScript que fazem `parseFloat()`):
  - `templates/checkout/index.html:396` — `let SUBTOTAL = parseFloat(...)` mantido como `floatformat:2`
  - `templates/usuarios/detalhe_pedido.html:268` — `var total = parseFloat(...)` mantido como `floatformat:2`
- **Filtro auxiliar `brl_price`** criado em `apps/core_utils/templatetags/della_filters.py` (disponível mas não obrigatório — `floatformat:"2g"` cobre o uso principal).

### Página de produto — ajustes visuais

- **"Peças Relacionadas"** — capitalização corrigida (era "Peças relacionadas").
- **"Entrega e trocas"** — linha "Frete calculado no checkout" removida do acordeão. O frete já é consultado diretamente na página do produto, tornando a linha redundante e enganosa.

---

## Pendências

| Item | Prioridade |
|---|---|
| E-mail via Brevo API | ✅ implementado |
| Cache de performance | ✅ implementado (2026-04-18) |
| Bling produto vinculado ao catálogo | ✅ implementado (2026-04-22) |
| Frete consistente produto ↔ checkout | ✅ implementado (2026-04-22) |
| PIX via PagBank API (confirmação automática) | ✅ implementado (2026-04-22) |
| Preços com separador de milhar | ✅ implementado (2026-04-22) |
| **Migrar para `www.dellainstore.com`** — apontar DNS `.com` e `.com.br` na UOL para `159.203.101.232`, configurar Nginx + certbot, atualizar `.env`. Ver checklist em "Migração" acima | Quando aprovado |
| **C2 — HMAC webhook Bling** — precisará de `BLING_WEBHOOK_SECRET` no `.env` e no painel Bling | Alta (antes de ir ao ar) |
| **C3 — Webhook PagSeguro** ✅ implementado — reconsulta `/orders/{id}` autenticada antes de atualizar pedido | Concluído |
| **Cartão de crédito bloqueado** — PagBank retorna `ACCESS_DENIED: whitelist access required`. Chamado aberto. Aguardando PagBank habilitar Checkout Transparente na conta. Pix funciona normalmente via PagBank API. | Aguardando PagBank |
| **PIX Opção C — API PIX do banco** — integrar com API do banco da D'ELLA para confirmação automática com dinheiro indo direto ao banco (sem passar pelo PagBank). Requer integração específica da instituição (Sicredi, Itaú, Bradesco, etc.). | Planejado |
| **C3 — Webhook Stone** — validar `X-Stone-Signature` (HMAC) antes de processar | Quando ativar Stone |
| **M3 — Compilar Tailwind local** — remove `unsafe-inline` do CSP | Fase posterior |
| Instagram feed | ✅ implementado |
| **🔴 PENDENTE — Validação de estoque no carrinho/checkout:** hoje é possível adicionar ao carrinho quantidade maior que o estoque disponível. Corrigir em: (1) `apps/pedidos/carrinho.py → adicionar()` — limitar `quantidade` ao `variacao.estoque` disponível; (2) botão +/− no drawer/resumo — não incrementar além do estoque; (3) `apps/pedidos/views.py → _processar_checkout()` — validar antes de subtrair o estoque e retornar erro se insuficiente. | **Alta** |

---

## Dependências (`requirements.txt`)

```
Django==5.1.15
psycopg2-binary==2.9.11
gunicorn==25.3.0
Pillow==12.2.0
python-decouple==3.8
requests==2.33.1
whitenoise==6.12.0
bleach==6.3.0
django-axes==8.3.1
django-csp==4.0
django-extensions==4.1
django-storages==1.14.6
boto3==1.42.88
openpyxl==3.1.5
qrcode[pil]
django-anymail[brevo]==14.0
```

---

## Como Continuar numa Nova Conversa

Cole exatamente esta frase:

> **"Continuando o desenvolvimento do site Della Instore. Leia o arquivo `/var/www/della-sistemas/projetos-claude/site_della/CLAUDE.md` e me aguarde para o próximo ajuste."**
