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
  - `conteudo.0011_alter_configuracaoloja_options_and_more` — verbose_name "Frete Grátis"; MiniBanner ordering fix; BannerPrincipal remove text fields
  - `pedidos.0008_alter_codigovendedor_codigo_and_more` — CodigoVendedor.codigo agora editável manualmente (sem default aleatório); gerar_numero_pedido() sequencial YYYY-NNNN
  - `produtos.0011_remove_avaliacao_titulo_remove_categoria_descricao_and_more` — Avaliacao sem titulo, produto nullable; Categoria sem descricao/imagem; TabelaMedidas sem subtitulo/categoria

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

**`client_max_body_size 50M`** — ✅ aplicado em `/etc/nginx/sites-available/della_site` no `location /` global.

**Rota de import de fotos via ZIP** tem `location` próprio com `client_max_body_size 500M` + `proxy_read_timeout 600s` (ver "Nginx — limite específico para rota de import de fotos" abaixo).

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
| `LookDaSemana` | titulo, descricao, foto, **produto_ponto1/2/3** (FK→Produto, null/blank), **foto_ponto1/2/3** (FK→ProdutoImagem, null/blank — foto específica por ponto; se vazio usa imagem_principal do produto), ponto1_top/esq, ponto2_top/esq, ponto3_top/esq (DecimalField %), ativo, criado_em |
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
| `CarrinhoAbandonado` | cliente (FK→Cliente, unique), email, nome, itens_json (JSONField), total, email_enviado, email_enviado_em, recuperado, criado_em, atualizado_em |

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
| Pagamento confirmado (cartão/pix) | `754756` | **Permanece** Em andamento - Site (não avança automático) |
| Pedido cancelado | `12` | Cancelado (padrão Bling) |

**IDs de situação observados via API (referência):**
- `754756` = Em andamento - Site (custom) ← usado no checkout e mantido mesmo após pagamento
- `18723` = Atendido - Site (custom) ← hoje **não** é aplicado automaticamente pelo site
- `15762` = situação custom antiga (pedidos anteriores)
- `15` = Em andamento (padrão Bling)
- `9` = Atendido (padrão Bling)
- `12` = Cancelado (padrão Bling)
- `6` = Em aberto (padrão Bling — estado inicial de criação, **não usar**)

**Importante:** o Bling ignora o campo `situacao` no POST de criação e cria tudo como "Em aberto" (ID 6). Por isso o código faz um PATCH separado logo após a criação para forçar "Em andamento - Site". Se o PATCH falhar, o pedido fica como "Em aberto" — verificar logs do gunicorn.

**Fluxo operacional atual (decisão de negócio):**
- Todo pedido criado pelo site vai para o Bling como **Em andamento - Site**, pago ou não
- Mesmo quando o PagSeguro confirma pagamento, o site **não** muda automaticamente a situação no Bling para `Atendido - Site`
- A ideia é manter a reserva de estoque e permitir operação manual no Bling: visualizar pedidos, ajustar logística, pagar etiqueta e só depois emitir NF / avançar o fluxo

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
    'logistica':     {'id': 915540, 'nome': 'Melhor Envio - Correios'},
    'idServicoLogistico': 14896881661,  # PAC nessa conta (SEDEX tem ID próprio)
    'volumes': [{
        'servico':    'PAC',     # ou 'SEDEX'
        'idServicoLogistico': 14896881661,
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

### Observação interna fixa no Bling

Todo pedido enviado ao Bling recebe automaticamente em `observacoesInternas` a mensagem:

```text
EMPRESA OPTANTE PELO SIMPLES NACIONAL, NAO GERA DIREITO AO CREDITO DE ISS, ICMS E IPI.

Banco Santander
Ag 2200
Cc 1300 2879 8
Adriana Simoes Machado Confeccoes Me
CNPJ 29 049 870 0001 37 - PIX
```

Se `pedido.observacao_interna` estiver preenchido no Django, o texto digitado é anexado abaixo dessa mensagem padrão.

### Estoque no site (apps/produtos/models.Variacao.estoque)
- **Diminui** no checkout, dentro de `transaction.atomic()` via `Greatest(F('estoque') - qty, Value(0))` — nunca vai negativo
- **Restaura** ao cancelar (webhook PagSeguro + cron `cancelar_pedidos_expirados`) via `F('estoque') + item.quantidade`

### Pontos de integração no código
| Arquivo | Evento |
|---|---|
| `apps/pedidos/views.py` | Checkout → `enviar_pedido_bling()` apenas; não promove automaticamente para `Atendido` |
| `apps/pagamentos/views.py` | Webhook PagSeguro → atualiza status no Django, mas só envia `CANCELADO` ao Bling quando houver cancelamento |
| `apps/pedidos/management/commands/cancelar_pedidos_expirados.py` | Cron → `restaurar_estoque_pedido()` + `atualizar_situacao_bling(CANCELADO)` |

---

## Navbar (base.html)

**Logo D'ELLA Instore:** o `D'ELLA` do cabeçalho e do rodapé agora usa **imagem oficial da marca** (asset local em `static/images/brand/logo-della.webp`), mantendo o `Instore` em texto logo abaixo. Isso evita diferenças de tipografia entre a fonte do site e a arte real da marca.

**Posicionamento absoluto da logo:** `.navbar-logo` é filho direto de `<nav>` (fora do `.navbar-topo`), com `position: absolute; left: 3.5rem; top: 0; height: var(--navbar-total); display: flex; flex-direction: column; justify-content: center; z-index: 2` — assim a logo fica verticalmente centralizada em relação a toda a altura da navbar (topo + categorias) e não empurra os outros elementos do grid.

Estrutura em 2 linhas:
```
[Linha 1 — .navbar-topo]     hamburger (mobile) | D'ELLA / Instore | busca + login + whatsapp + carrinho
[Linha 2 — .navbar-categorias-bar]   BODY · BEACHWEAR · CASUAL · ... (categorias-mãe com dropdown)
```
- Navbar é `position: fixed`, altura total: 60px (topo) + ~36px (categorias) = ~96px
- Em páginas com `.navbar.solida` (ex: home, detalhe), o conteúdo tem `margin-top: var(--navbar-total)`
- Mobile: linha de categorias some, hamburger abre menu lateral (`#menu-mobile`)
- **Menu mobile:** a marca do menu lateral também usa a logo oficial da D'ELLA (não mais texto tipografado separado)
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
- **Peças Relacionadas:** os cards reaproveitam o mesmo comportamento de hover da loja/home. Se o produto não tiver segunda foto, o template usa a própria imagem principal como fallback em `foto-hover`, evitando sumiço da foto ao passar o mouse

### Guia de tamanhos / Tabela de medidas

- O cadastro deixou de depender apenas de texto/HTML livre. Agora existe **tabela estruturada** em `TabelaMedidas`, com:
  - `nome`, `subtitulo`, `categoria`
  - cabeçalhos de colunas (`cabecalho_1` … `cabecalho_6`)
  - linhas estruturadas em `TabelaMedidasLinha` com `medida`, `unidade` e valores por coluna
- O admin em **Produtos → Tabelas de medidas** agora permite cadastrar a tabela linha por linha, sem subir imagem
- O campo `conteudo` antigo foi mantido como **legado/fallback** para compatibilidade com tabelas antigas
- O link **Guia de Tamanhos** do rodapé usa a **mesma origem de dados** da tabela exibida no detalhe do produto
- O modal do produto e a página do rodapé compartilham o mesmo componente visual (`templates/components/tabela_medidas.html`)
- A faixa preta da tabela usa o `D'` oficial da marca como asset separado (`static/images/brand/d-logo-della-gold-soft.png`)

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
- **Importante:** o importador formato Bling hoje preenche produto, SKU e `bling_variacao_id`, mas **não sincroniza automaticamente o campo `Variacao.estoque`**. O estoque do site continua sendo o campo local `variacao.estoque` até existir uma rotina dedicada de sync

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
- **Painel Bling (developer.bling.com.br):** endpoint já cadastrado em **Webhooks → Adicionar** apontando para `https://novo.dellainstore.com.br/bling/webhook/`. Não há campo de "chave secreta" — o Bling assina automaticamente.
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
- Depois: valida `X-Bling-Signature-256` via HMAC-SHA256 do body usando `BLING_CLIENT_SECRET`, que é o comportamento correto do Bling v3. Não existe `BLING_WEBHOOK_SECRET` separado.
- Painel do Bling já configurado com o endpoint do webhook; a assinatura é gerada automaticamente pelo próprio Bling.

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

**Bling + Melhor Envio — payload operacional ajustado** ✅
- Payload do pedido no Bling foi enriquecido para o fluxo com Melhor Envio.
- Transporte agora envia também `quantidadeVolumes`, `pesoBruto`, `contato`, `etiqueta` e `prazoEntrega` (quando disponível), além de `servico`, `modalidade`, `frete`, `fretePorConta`, `logistica` e os IDs reais da logística/serviço logístico resolvidos via API do Bling.
- Checkout passou a persistir `frete_prazo_dias` no model `Pedido` para alimentar `prazoEntrega` e `dataPrevista` no Bling.
- Próximo passo: validar no painel do Bling se pedidos novos passam a exibir o indicador/ícone da integração do Melhor Envio.

**C3 — Webhooks Stone sem assinatura** — quando ativar Stone
- Stone: validar header `X-Stone-Signature` (HMAC) antes de processar.

**M3 — CSP com `'unsafe-inline'`** — médio prazo
- Compilar Tailwind localmente para remover `'unsafe-inline'` de `script-src`.

**LGPD — Retenção de `BlingLog`** ✅
- Management command implementado: `python manage.py limpar_bling_logs --dias 180 --settings=core.settings.production`
- Suporta `--dry-run` para validar antes de apagar.
- Sugestão de cron diário às 02:30 UTC:
  `30 2 * * * cd /var/www/della-sistemas/projetos-claude/site_della && /var/www/della-sistemas/projetos-claude/site_della/venv/bin/python manage.py limpar_bling_logs --dias 180 --settings=core.settings.production >> /var/www/della-sistemas/projetos-claude/site_della/logs/cron_limpar_bling_logs.log 2>&1`

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

### Bling + Melhor Envio — fluxo operacional desejado

- O fluxo operacional da D'ELLA é: **site cria pedido → pedido vai para o Bling com dados de transporte → emissão de NF no Bling → integração nativa do Bling envia para o carrinho do Melhor Envio → pagamento da etiqueta no Melhor Envio → impressão de etiqueta + DANFE simplificada no Bling**
- O papel ideal do site é **preparar corretamente o payload enviado ao Bling**, não necessariamente comprar a etiqueta diretamente
- **Ponto de verificação importante:** confirmar em produção se o pedido enviado pelo site ao Bling está com todos os dados de transporte/logística exigidos para o fluxo Bling + Melhor Envio entrar redondo (transportadora, serviço, volumes, frete e eventuais dados fiscais necessários)

---

## PagSeguro (PagBank) — Integração ativa

- **Token de produção:** `.env` → `PAGSEGURO_TOKEN`
- **Token de sandbox:** `.env` → `PAGSEGURO_TOKEN_SANDBOX`
- **Estado atual temporário (2026-04-23):** `PAGSEGURO_SANDBOX=True` para homologação com o suporte PagBank
- **Endpoint público-key correto:** `GET /public-keys/card` (não `/public-keys/CREDIT_CARD` — legado, retorna 404)
- **Fluxo cartão:** frontend carrega SDK → `PagSeguro.encryptCard()` → envia `encrypted_card` → backend chama `criar_ordem_cartao()` — PAN nunca toca o servidor
- **Webhook seguro (C3 implementado):** `pagseguro_notificacao` recebe o `order_id` do payload, reconsulta `GET /orders/{id}` na API PagBank de forma autenticada e só então atualiza o pedido — payloads forjados são descartados porque a reconsulta falha
- **Chave pública cacheada:** 1 hora (`pagseguro_public_key` no cache Django). Limpar com `cache.delete('pagseguro_public_key')` se precisar forçar renovação

### Homologação sandbox — 2026-04-23

- Integração colocada temporariamente em sandbox para responder ao chamado do PagBank com evidências reais de teste
- `apps/pagamentos/services/pagseguro.py` agora aceita `PAGSEGURO_TOKEN_SANDBOX` e escolhe o token automaticamente quando `PAGSEGURO_SANDBOX=True`
- Checkout de cartão foi reabilitado apenas para o fluxo sandbox, carregando a chave pública real do merchant de teste
- Foram criados comandos auxiliares para exportar logs de homologação:
  - `apps/pagamentos/management/commands/exportar_log_pagseguro_pix.py`
  - `apps/pagamentos/management/commands/exportar_log_pagseguro_cartao.py`
  - `apps/pagamentos/management/commands/mascarar_log_pagseguro.py`

### Logs de testes gerados para o suporte

Arquivos finais mascarados:

- `projetos-claude/logs/pagseguro_pix_DI-2026-E1C09B_masked.json`
- `projetos-claude/logs/pagseguro_pix_DI-2026-E1C09B_masked.txt`
- `projetos-claude/logs/pagseguro_cartao_DI-2026-8270EC_masked.json`
- `projetos-claude/logs/pagseguro_cartao_DI-2026-8270EC_masked.txt`

Pedidos usados na homologação:

- **PIX:** `DI-2026-E1C09B` → order `ORDE_1B0F9FFE-413F-47D4-93B2-73693748BABB`
- **Cartão:** `DI-2026-8270EC` → order `ORDE_DF4144C6-882D-48D6-BC7D-E3E7199F5805` → charge `CHAR_9F14B0C7-AEC8-4B90-AC00-5FCFD0794E28` (`PAID` em sandbox)

### Importante — voltar para produção após retorno do suporte

Assim que o PagBank concluir a análise/liberação:

1. Ajustar no `.env`: `PAGSEGURO_SANDBOX=False`
2. Manter `PAGSEGURO_TOKEN` como token de produção
3. Opcionalmente manter `PAGSEGURO_TOKEN_SANDBOX` salvo apenas para futuras homologações
4. Recarregar/reiniciar o Gunicorn do site
5. Validar no checkout que cartão e PIX continuam apontando para produção antes de reabrir o fluxo ao público

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

**Atualização 2026-04-23:** suporte pediu evidências reais em sandbox. Os testes de PIX e cartão via `POST /orders` foram executados com sucesso em sandbox e os logs completos foram gerados/mascarados para envio no chamado. Após a homologação, o ambiente deverá voltar para produção.

**Atualização 2026-04-24:** foi feito um diagnóstico seguro com o token de produção. `GET /public-keys/card` respondeu `200` e retornou chave pública, mas `POST /orders` com payload diagnóstico de cartão respondeu `403 ACCESS_DENIED: whitelist access required`. Conclusão: a tokenização já responde em produção, porém a allowlist do Checkout Transparente ainda não foi liberada pelo PagBank. O `.env` foi mantido em `PAGSEGURO_SANDBOX=True`.

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
- **Bling — webhook PIX confirmado:** `_MAPA_SITUACAO` em `apps/bling/views.py` continua aceitando `18723: 'pagamento_confirmado'` (Atendido - Site) quando a mudança partir do próprio Bling, mas o site não envia mais essa situação automaticamente após pagamento.
- **Bling — situação correta ao criar pedido:** `SITUACAO_EM_ANDAMENTO_SITE` corrigido de `6` (Em aberto) para `754756` (Em andamento - Site, custom D'ELLA — verificado via API no pedido 9638).
- **Bling — fluxo operacional manual:** mesmo com pagamento confirmado no site, o pedido permanece em `Em andamento - Site` no Bling. O avanço operacional (logística, etiqueta, NF e demais etapas) fica manual no painel do Bling.
- **Bling — observação interna padrão:** todo pedido enviado ao Bling recebe automaticamente a mensagem fiscal/bancária fixa em `observacoesInternas`.
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

### Atualizações 2026-04-22 (layout e conteúdo)

- **Logo da marca no site:** navbar, rodapé e menu mobile agora usam a **logo oficial em imagem** (`static/images/brand/logo-della.webp`) para o `D'ELLA`; o `Instore` permanece em texto abaixo
- **Guia de tamanhos estruturado:** `TabelaMedidas` ganhou cabeçalhos por coluna e linhas estruturadas (`TabelaMedidasLinha`), permitindo montar a tabela no admin sem subir imagem
- **Compatibilidade:** o campo antigo `conteudo` da tabela foi mantido como fallback para tabelas legadas
- **Admin de tabela de medidas:** Produtos → Tabelas de medidas agora aceita cadastro linha a linha (Manequim, Peso médio, Busto, Cintura, Quadril etc.)
- **Guia de tamanhos do rodapé:** usa a mesma base de dados da tabela mostrada no detalhe do produto
- **Componente compartilhado:** modal do produto e página do rodapé usam o mesmo componente visual (`templates/components/tabela_medidas.html`)
- **Marca na tabela de medidas:** o canto direito da faixa preta usa um asset separado do `D'` em dourado (`static/images/brand/d-logo-della-gold-soft.png`)
- **Peças Relacionadas:** corrigido o hover dos cards no detalhe do produto; quando o item não tem segunda foto, o template usa a própria foto principal como fallback e a imagem não some no hover

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
- **Bling — integração operacional** (atualizado em 2026-04-22): pedido criado → `Em andamento - Site`; pagamento confirmado **não** muda situação no Bling; cancelamento → `Cancelado` + restaura estoque. Ver seção "Bling — Integração Bidirecional" acima.
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

**Todo admin novo DEVE ter:** row click + botões Editar/Excluir por linha.

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

### SEO manual — ProdutoAdmin

- O fieldset `SEO — Google` permanece no admin de produto
- Campos preenchidos manualmente: `seo_titulo`, `seo_descricao` e `seo_keywords`
- Se ficar em branco, o site continua usando fallback com nome e descrição do produto

### Configurações de admin simplificadas (sessão 2026-04-24)

| Model | Campos removidos | Justificativa |
|---|---|---|
| `BannerPrincipal` | pretitulo, titulo, titulo_italico, subtitulo, texto_botao | Banners são visuais — o texto fica na arte da imagem |
| `MiniBanner` | pretitulo, titulo | Banners são visuais |
| `Categoria` | descricao, imagem | Nunca exibidas na loja |
| `Avaliacao` | titulo; produto nullable | Avaliação pode ser da loja (não de produto específico) |
| `TabelaMedidas` | subtitulo, categoria | Tabela única global, sem vínculo por categoria |
| `CodigoVendedor` | default aleatório no `codigo` | Usuário agora digita o nome/código manualmente |

**BannerPrincipal após remoção de campos de texto:**
- `url_botao` permanece: clicar no slide redireciona para essa URL
- Template `home/index.html`: slide com `data-href` → JS redireciona ao clicar
- Não há mais overlay de texto no hero

**MiniBanner — fix do swap esq/dir:**
- Admin e homepage agora usam a mesma regra visual: `esq` sempre renderiza primeiro e `dir` sempre renderiza em segundo.
- Template da homepage: banner é só imagem clicável (sem campos de texto sobrepostos).

**ConfiguracaoLoja — singleton UX:**
- `changelist_view` redireciona direto para o formulário de edição (ou add se não existir)
- `response_change` mantém o usuário na tela de edição após salvar
- verbose_name = `'Frete Grátis'` para o painel
- `__str__()` retorna vazio para não exibir `ConfiguracaoLoja object (1)` no admin

**Numeração de pedidos:**
- `gerar_numero_pedido()` gera `YYYY-NNNN` sequencial (ex: `2026-0001`)
- `gerar_codigo_vendedor()` mantida em `models.py` apenas para compatibilidade retroativa com migration `0004`

**CSS — inline de Variações (della_admin.css seção 21):**
- Header sticky: `position: sticky; top: 0; z-index: 2`
- `max-height: 420px; overflow-y: auto` no `.tabular.inline-related`
- Larguras fixas por coluna (nth-child 1–9)
- Campos numéricos/SKU/ID Bling ficaram mais compactos
- Remoção de linhas agora usa botão `×` vermelho (sem checkbox visível)

**Painel admin — organização e usabilidade (sessão 2026-04-24):**
- Sidebar e dashboard reorganizados nesta ordem: `Conteúdo do Site`, `Produtos`, `Pedidos`, `Usuários`, `Bling ERP`, `Segurança`
- `Pagamentos` aparece agrupado dentro de `Pedidos`; o app separado deixa de aparecer na navegação
- `Grupo de acesso` aparece agrupado dentro de `Usuários`; o app `auth` deixa de aparecer como menu separado
- A sidebar lateral das páginas internas do admin usa override próprio em `templates/admin/nav_sidebar.html` + tag `apps/core_utils/templatetags/admin_sidebar.py` para garantir essa ordem e esses agrupamentos em todas as telas
- `Segurança` usa nomes em português no menu: bloqueios de acesso, histórico de logins e tentativas com senha errada
- `CodigoVendedorAdmin` não mostra mais o texto de exemplo acima do formulário
- `CategoriaAdmin` ordena por grupo da categoria-mãe, mantendo cada subcategoria logo abaixo da sua respectiva mãe
- `ProdutoAdmin` mostra `Editar/Excluir` mais cedo na linha da listagem
- Inline `Fotos do produto` ganhou área de arrastar/soltar e seleção múltipla
- `ProdutoImagem.__str__()` agora usa o nome original do arquivo salvo, em vez de `Foto #...`
- `ProdutoCorFotoInline.verbose_name_plural = "Fotos por Cor"`
- `ClienteAdmin` voltou a expor o campo padrão de senha do `UserAdmin` junto do link "Alterar senha" para evitar falha na abertura do cadastro

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
| PagSeguro | **SANDBOX temporário** (`PAGSEGURO_SANDBOX=True`) — voltar para produção após retorno do suporte |
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

### Admin — Dashboard de Pedidos

- Novo botão **"Dashboard de Pedidos"** adicionado ao lado de **"Relatório Geral"** no topo do painel.
- Nova rota administrativa: `/painel/pedidos/dashboard/`.
- O dashboard mostra cards separados para:
  - **Pedidos à Enviar**: pedidos pagos e ainda não enviados (`pagamento_confirmado` + `em_separacao`).
  - **Pedidos Enviados** no período filtrado.
  - **Faturamento Total** no período filtrado.
  - **Qtd de Clientes** no período filtrado.
  - **Qtd de SKU Vendidos** no período filtrado.
- Filtro rápido por dias implementado com opções: `1`, `7`, `15`, `30`, `60` e `90`.
- A contagem de **Pedidos Enviados** usa o `HistoricoPedido`, para refletir os pedidos realmente marcados como `enviado` no período, mesmo que depois tenham sido entregues.
- A tela também mostra duas listas rápidas:
  - **Pedidos para Envio**
  - **Últimos Pedidos Enviados**

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
| Webhook Bling v3 com HMAC via `BLING_CLIENT_SECRET` | ✅ implementado e endpoint cadastrado no painel (2026-04-22) |
| **Migrar para `www.dellainstore.com`** — apontar DNS `.com` e `.com.br` na UOL para `159.203.101.232`, configurar Nginx + certbot, atualizar `.env`. Ver checklist em "Migração" acima | Aguardar finalização dos testes |
| **C3 — Webhook PagSeguro** ✅ implementado — reconsulta `/orders/{id}` autenticada antes de atualizar pedido | Concluído |
| **PagBank em allowlist pendente** — tanto cartão quanto Pix dinâmico via `POST /orders` retornam `ACCESS_DENIED: whitelist access required`. Chamado aberto. Enquanto isso, o site usa fallback de Pix estático local, sem confirmação automática. | Aguardando PagBank |
| **C3 — Webhook Stone** — validar `X-Stone-Signature` (HMAC) antes de processar | Quando ativar Stone |
| **M3 — Compilar Tailwind local** — remove `unsafe-inline` do CSP | Aguardar |
| Instagram feed | ✅ implementado |
| Retenção de `BlingLog` via management command | ✅ implementado (aguarda apenas agendamento no cron) |
| Validação de estoque no carrinho/checkout | ✅ implementado (limite respeita estoque disponível) |
| **🔴 PENDENTE — Estoque automático via Bling:** hoje o estoque oficial do site ainda é o campo local `Variacao.estoque`. O importador formato Bling não sincroniza esse campo automaticamente. Quando o estoque real no Bling estiver saneado, implementar rotina de sincronização `Bling -> site` para que o Bling passe a ser a fonte de verdade. | Aguardar saneamento do estoque no Bling |
| Payload do pedido para fluxo Bling + Melhor Envio | ✅ ajustado no código; pendente validar no painel do Bling se o ícone/sinal da integração aparece em pedidos novos |
| **Carrinho Abandonado** — captura, e-mail de lembrete, admin, management command | ✅ implementado (2026-04-26) — ver seção "Carrinho Abandonado" |
| **Cookie Consent (LGPD)** — banner rodapé + modal de personalização + cookie de consent | ✅ implementado (2026-04-28) — ver "Atualizações 2026-04-28" |
| **Meta Pixel** — PageView, ViewContent, AddToCart, InitiateCheckout, Purchase com consent gate | ✅ implementado (2026-04-28) — ver "Atualizações 2026-04-28" |
| **Meta — API de Conversões (server-side)** — eventos do servidor → Meta direto, melhora atribuição em iOS/ad blockers | Aguardar — implementar quando rodar campanhas pagas pra valer |
| **Meta — Catálogo de produtos (`/feed-meta.xml`)** — feed dinâmico para Anúncios Dinâmicos + Lojas no Instagram/Facebook | Aguardar |

---

## Atualizações 2026-04-26

### Melhor Envio — ajustes de cálculo de frete

- **`insurance_value` removido:** `apps/pagamentos/services/melhorenvio.py` agora envia `insurance_value: 0` — o seguro declarado não é mais somado ao frete. Antes, o valor da peça ou do carrinho era passado como `insurance_value`, encarecendo o cálculo.
- **Parâmetro `valor_declarado` removido** da função `calcular()` e dos chamadores (`apps/pedidos/views.py`).
- **Ajuste de prazo e preço:** toda opção retornada pela API recebe `+1 dia` no prazo e `+R$3,00` no preço (margem operacional). Aplicado em `calcular()` antes de retornar as opções.
- **Peso por produto:** campo `peso` (inteiro em gramas, default 500) adicionado ao model `Produto` — migration `produtos.0013`. Cadastrado no admin em "Produtos → Logística". O cálculo de frete soma `peso_g × quantidade` de cada item do carrinho/produto e converte para kg antes de enviar ao Melhor Envio, substituindo o peso fixo de 0.5kg/peça anterior.

### Produto — campo `genero` removido

- Campo `genero` (Feminino/Unissex) removido do model `Produto` — migration `produtos.0014`.
- Removido do admin (fieldset "Identificação", filtro lateral, exportar CSV, importar CSV).
- O campo `genero` do model `Cliente` (perfil/cadastro) permanece intocado.

### Admin — botão × de deletar fotos corrigido

- `static/admin/js/admin_linhas.js`: substituído **binding direto** por **event delegation** no `document`.
- Antes, o click handler era vinculado individualmente a cada botão × na inicialização — se o DOM era modificado depois (inserção do dropzone, linhas novas), o handler podia se perder.
- Agora um único listener no `document` captura qualquer clique em `.della-inline-remove`, independente de quando o botão foi criado. Corrige o bug de "clico e nada acontece" no inline de fotos do produto.

### Look da Semana — foto específica por ponto

- Adicionados campos `foto_ponto1`, `foto_ponto2`, `foto_ponto3` (FK → `ProdutoImagem`, null/blank) ao model `LookDaSemana` — migration `conteudo.0012`.
- **Fluxo no admin:** selecione o produto → salve → volte a editar → o campo "Foto do ponto X" agora mostra apenas as fotos daquele produto (ordenadas: principal primeiro). Se vazio, o site usa a foto principal do produto.
- **View (`apps/produtos/views.py → homepage`):** `select_related` inclui `foto_ponto1/2/3`; contexto passa `look_items` (lista de tuples `(produto, foto)`).
- **Template (`templates/home/index.html`):** seção "look-produtos-lista" usa `{% for produto, foto in look_items %}` — se `foto` está preenchida usa `foto.imagem.url`; caso contrário cai em `produto.imagem_principal`.

---

## Carrinho Abandonado (2026-04-26)

### Como funciona

Quando um cliente **autenticado** adiciona uma peça ao carrinho e não finaliza a compra, o sistema salva automaticamente um snapshot do carrinho no banco (`CarrinhoAbandonado`). Se o cliente adicionar mais itens, o registro é atualizado. Quando o checkout é concluído com sucesso, o registro é marcado como `recuperado=True`.

### Arquivos envolvidos

| Arquivo | Função |
|---|---|
| `apps/pedidos/models.py` | Model `CarrinhoAbandonado` |
| `apps/pedidos/views.py` | `_salvar_carrinho_abandonado()` e `_limpar_carrinho_abandonado()` |
| `apps/pedidos/emails.py` | `enviar_email_carrinho_abandonado(ca)` e helper `_brl()` |
| `apps/pedidos/admin.py` | `CarrinhoAbandonadoAdmin` |
| `apps/pedidos/management/commands/enviar_emails_carrinho_abandonado.py` | Command para disparo via cron |
| `templates/emails/carrinho_abandonado.html` | Template HTML do e-mail |
| `static/images/brand/logo-della-white.png` | Logo D'ELLA em branco (gerada via Pillow) para o e-mail |

### Model `CarrinhoAbandonado`

- `unique_together = [('cliente',)]` — apenas 1 registro por cliente (sempre sobrescrito)
- `itens_json` — JSONField com snapshot dos itens: `nome`, `variacao_desc`, `preco`, `quantidade`, `subtotal`, `imagem`
- `email_enviado` / `email_enviado_em` — controle de envio do lembrete
- `recuperado` — True após checkout concluído com sucesso
- Migration: `pedidos.0009_carrinhoabandonado`

### Foto dos itens no e-mail

A `imagem` salva em `itens_json` já vem resolvida do `carrinho.py → adicionar()`:
1. Busca `ProdutoCorFoto` pela cor da variação selecionada (foto específica da cor)
2. Fallback: `produto.imagem_principal`

Ou seja, o e-mail mostra a foto da cor correta — se "Branco M", aparece a foto branca; se não houver vínculo de cor, aparece a foto principal.

### Hooks no views.py

```python
# Após cart.adicionar() em adicionar_ao_carrinho:
_salvar_carrinho_abandonado(request, cart)

# Após cart.limpar() em _processar_checkout:
_limpar_carrinho_abandonado(request)
```

### Admin — Pedidos → Carrinhos Abandonados

- Badges de status: `Aguardando` (amarelo) / `E-mail enviado` (azul) / `Recuperado` (verde)
- Ação em massa: **"Enviar e-mail de lembrete agora"** — dispara para selecionados não recuperados

---

## Atualizações 2026-04-27

### Cores padrão — importação/exportação

- **Botão "Exportar CSV" em Produtos → Cores padrão:** exporta `nome, codigo_hex, codigo_hex_secundario, ordem` no mesmo formato da importação.
- **Importação de cores refatorada para validação prévia:** o fluxo agora é `Validar planilha` → preview (`Criar`/`Atualizar`, erros e avisos) → `Importar planilha validada`.
- **Leitura robusta de arquivo:** aceita `CSV`, `XLSX` e `XLS`; no CSV detecta automaticamente separador `;`, `,` ou tab.
- **Normalização de nomes na importação:** nomes de cor são comparados com chave normalizada:
  - maiúsculas
  - sem acentos
  - sem caracteres invisíveis do Excel/CSV (`BOM`, zero-width chars)
  - com espaços normalizados
- **Consequência prática:** `CHA` e `CHÁ` são tratados como o mesmo nome base na validação/importação.
- **Arquivo duplicado:** se a mesma cor aparecer duas vezes no mesmo arquivo importado, a validação acusa erro.
- **Banco duplicado por variação de acento/caixa:** se já existirem duas cores no banco que diferem apenas por acento/maiúscula, a validação acusa erro por ambiguidade.
- **Atualização por nome existente:** reimportar um CSV exportado pelo próprio admin agora entra como `Atualizar`, não `Criar`.

### Produtos — importação completa por planilha

- **Fluxo antigo removido:** importação antiga "Bling" / "Formato personalizado" substituída por um único fluxo completo com validação prévia.
- **Cabeçalho atual da planilha:** `nome, categoria_pai, subcategoria, descricao, composicao, preco_geral, preco_promocional_geral, peso, ativo, destaque, novo, ordem, seo_titulo, seo_descricao, palavra_chave, preco_variacao, preco_promocional_variacao, disponibilidade, prazo_confeccao_dias, estoque, sku, id_bling`
- **Nome da variação:** o campo `nome` deve seguir o padrão `MODELO (COR) (TAMANHO)`; o import faz parse automático do modelo, cor e tamanho.
- **Leitura robusta:** aceita CSV com `;`, `,` e tab, além de `XLSX/XLS`.
- **Normalização de comparação:** produtos, categorias, subcategorias, cores e tamanhos são comparados com chave normalizada (maiúsculas + sem acentos + sem caracteres invisíveis).
- **Campos opcionais que não bloqueiam a importação:** `descricao`, `composicao`, `preco_promocional`, `seo_titulo`, `seo_descricao`, `palavra_chave`.
- **Descrição vazia no produto novo:** se `descricao` vier vazia na planilha e o produto não existir ainda, o import usa o nome do modelo como fallback temporário para não travar o save.
- **Categoria pai + subcategoria:** a planilha passou a aceitar os dois campos porque existem subcategorias com nomes repetidos em pais diferentes.
- **Cor ausente no cadastro:** a validação não bloqueia; avisa e, no import confirmado, cria a cor automaticamente sem `codigo_hex`.
- **Importação posterior de HEX:** a planilha de `Cores padrão` pode ser usada depois para completar ou atualizar os HEX dessas cores criadas automaticamente.

### Produtos e variações — novas regras de negócio

- **Disponibilidade por variação:** `Variacao` ganhou:
  - `disponibilidade`: `imediata` ou `sob_demanda`
  - `prazo_confeccao_dias`
- **Prazo de frete:** quando a variação é `sob_demanda`, o prazo de confecção é somado ao prazo retornado pelo frete.
- **Preço por variação:** `Variacao` ganhou `preco` e `preco_promocional`.
- **Fallback de preço:** se a variação não tiver preço próprio, o site usa `preco` / `preco_promocional` do `Produto`.
- **Importação de produtos:** passou a aceitar `preco_geral`, `preco_promocional_geral`, `preco_variacao` e `preco_promocional_variacao`.
- **Carrinho/checkout/listagens:** passaram a consumir o preço efetivo da variação quando houver.

### Padronização de texto

- **Maiúsculas automáticas:** `Produto.nome`, `CorPadrao.nome` e `TamanhoPadrao.nome` são salvos em uppercase.
- **Descrição e composição com múltiplas linhas:** `sanitize_multiline_text()` passou a preservar quebras de linha em `Produto.descricao` e `Produto.composicao`.
- **Página do produto:** a composição agora respeita as quebras de linha ao renderizar.

### Admin — usabilidade

- **Cores padrão:** a listagem passou a restaurar o scroll ao voltar de uma edição, usando `sessionStorage`.
- **Variações no produto — preview imediato da cor:** ao trocar o dropdown de cor no inline, a bolinha de preview é atualizada na hora sem precisar salvar.
- **Clonar variação antes de salvar:** o botão `Clonar` do inline agora gera uma nova linha no front-end antes do save, copiando os campos principais e limpando os que mais causam conflito (`tamanho`, `estoque`, `sku`, `id bling`).
- **Scroll do formulário de produto:** ao salvar, a página tenta restaurar a posição do scroll vertical e dos containers tabulares.
- **Scrollbar global do admin:** a aparência ficou mais visível, dourada e próxima do visual do site.

### Admin — bloco "Variações" — sticky header definitivo (2026-04-27)

Solução final do bloco de Variações no edit do produto. Faixa preta "VARIAÇÕES" + cabeçalho de colunas + barra de scroll horizontal **fixos no viewport da página** enquanto o usuário rola — não importa onde ele esteja na tabela.

**Arquitetura:**

- `templates/admin/edit_inline/tabular.html` — override do template do tabular inline para mover o `<h2 class="inline-heading">` para FORA de `.tabular.inline-related`, virando filho direto de `#variacoes-group`. Sem ancestral com overflow → o `position: sticky; top: 0` da faixa preta resolve contra a viewport. Vale para todos os tabular inlines (Fotos, Fotos por Cor, Variações), só Variações ativa o sticky via CSS.
- `#variacoes-group .tabular.inline-related` — `overflow-x: auto` (mantém scroll horizontal interno), barra nativa **oculta** via `scrollbar-width: none` (Firefox) + `::-webkit-scrollbar { display: none }` (Webkit) + `-ms-overflow-style: none` (Edge). Sem `overflow-y` (que escoparia o sticky do thead).
- **`<thead>` original** recebe `display: none`. Larguras das colunas vêm das `td` via `#variacoes-group th/td:nth-child(N) { width }`.
- **`.della-thead-clone-wrap`** — wrapper sticky construído via JS, filho direto do `#variacoes-group` (fora do scroll context). `position: sticky; top: var(--variacoes-heading-h); overflow: hidden`. Dentro tem um `<table>` com clone do thead. Largura é `sourceTable.scrollWidth`. JS sincroniza `transform: translateX(-container.scrollLeft)` no clone toda vez que o container rola horizontalmente.
- **`.della-inline-scrollbar-proxy`** — barra dourada sticky `bottom: 0`, sincroniza `scrollLeft` com o container. JS já atualiza o clone do thead em sincronia.
- **Bug crítico do `<fieldset class="module">` interno**: a regra global `#content .module { overflow-x: auto }` (seção 6 — MODULE/CARD) batia também no `<fieldset class="module">` filho de `.tabular.inline-related`, criando uma SEGUNDA scrollbar visível. Solucionado com override:
  ```css
  #variacoes-group .tabular.inline-related > fieldset.module { overflow: visible }
  ```
- **JS:** `produto_admin.js → buildVariationStickyThead()`, `syncVariationHeadingHeight()`. A altura real da faixa preta é medida e gravada na CSS variable `--variacoes-heading-h` para o `top` do clone ficar pixel-perfect.

**Arquivos:**
- `static/admin/css/della_admin.css` (seção das larguras + sticky de Variações)
- `static/admin/js/produto_admin.js`
- `templates/admin/edit_inline/tabular.html`

### Admin — Foto por Cor — bolinha de preview ao escolher cor (2026-04-27)

Fix do `formfield_for_foreignkey` do `ProdutoCorFotoInline` em `apps/produtos/admin.py`: a classe definia o método **duas vezes** (um aplicava o widget `CorPreviewSelect`, outro filtrava o queryset de `imagem` por produto). Em Python, o segundo método sobrescrevia o primeiro, então o widget custom de cor **nunca era aplicado** — sem `data-cor-hex` nas `<option>`, o JS não conseguia desenhar a bolinha. Unificado em um método único.

### Admin — Foto por Cor — fotos novas disponíveis antes de salvar (2026-04-27)

Fluxo: o usuário sobe fotos novas no inline "Fotos do produto" → vai pro inline "Fotos por Cor" e já consegue selecionar essas fotos novas no dropdown (sem precisar salvar antes). A bolinha de cor e a thumb da foto aparecem em tempo real. No save final, o backend orquestra a ordem: salva imagens primeiro (gera IDs), resolve as refs pending, salva fotos por cor.

**Backend:**
- `apps/produtos/forms.py` (NOVO) — `_PendingImagemField` (`ModelChoiceField` que aceita strings `pending:imagens-N` sem falhar a validação) + `ProdutoCorFotoForm` que substitui o field `imagem` pelo custom.
- `apps/produtos/admin.py → ProdutoCorFotoInline.form = ProdutoCorFotoForm`.
- `apps/produtos/admin.py → ProdutoAdmin.save_related` — override que processa formsets em ordem específica:
  1. Salva o formset de `ProdutoImagem` primeiro (gera IDs).
  2. Monta mapa `'imagens-N' → instance recém-criada`.
  3. Itera os forms de `ProdutoCorFoto` com `_pending_imagem_ref` setado e atribui `form.instance.imagem = instance`. Forms cuja ref não pode ser resolvida (ex: linha de imagens removida) são marcados como `cleaned_data['DELETE'] = True` e ignorados.
  4. Salva o formset de `ProdutoCorFoto` com refs resolvidas.
  5. Salva os demais formsets (variações).
- O campo `ProdutoCorFoto.imagem` já é `null=True, blank=True` → validação `_post_clean` não bate com NOT NULL durante o `is_valid()` com pending.

**Frontend (`produto_admin.js`):**
- `getPendingImageRefs()` — varre `imagens-group` lendo cada `<input type="file">` que tem arquivo escolhido (e a linha não é `has_original`/`empty-form`). Retorna lista de `{ key: 'imagens-N', filename }`.
- `syncPendingOptionsInColorPhotoSelects()` — injeta/remove `<option value="pending:imagens-N" data-pending="1">Nova foto: arquivo.jpg</option>` em todos os selects de "Foto" do `fotos_por_cor-group`. Idempotente — preserva a seleção existente do usuário.
- `updatePhotoFotoPreview(row)` — desenha a thumb na coluna de preview:
  - Valor `pending:imagens-N` → `URL.createObjectURL(file)` lendo o input file correspondente.
  - Valor numérico (foto já salva) → reusa o `<img>` da `.field-thumb_preview` da linha correspondente em `imagens-group` (correlação via `<input name="imagens-N-id" value="ID">`).
- Bind no `change` dos selects + chamada inicial via `MutationObserver` (`refreshInlineEnhancements`) e em `init()`.

### Importação de fotos via ZIP (2026-04-27)

URL: `/painel/produtos/produto/importar-fotos/` — botão **"Importar fotos (ZIP)"** roxo no changelist de produtos, ao lado de "Importar via planilha".

**Como funciona:**
- Usuário sobe um `.zip` contendo pastas com nomes dos produtos pais cadastrados; cada pasta contém `.png/.jpg/.jpeg/.webp`.
- Suporta **wrapper folder automático**: se zipou a pasta-pai inteira (ex: `fotos_produtos/Body Adriana/foto.png`), o validador detecta que todos os arquivos compartilham o mesmo primeiro segmento e desconta automaticamente. Não precisa zipar só o conteúdo interno.
- Match de produto via `_texto_importacao_chave` (maiúsculas + sem acentos + sem caracteres invisíveis), igual ao import de planilhas.
- Produtos que **já têm fotos** cadastradas são ignorados (sem sobrescrever nem duplicar).
- Pastas cujo nome não bate com nenhum produto são ignoradas (com aviso).
- Validação prévia → preview com cards de resumo (pastas no ZIP, produtos a atualizar, fotos a importar, já com fotos, sem produto), tabela detalhada com badge de status por pasta. Só após confirmar, importa.

**Implementação:**
- `apps/produtos/admin.py → ProdutoAdmin._importar_fotos_view`, `_validar_zip_fotos`, `_importar_fotos_zip_confirmado`.
- ZIP é salvo em `/tmp/della_import_fotos_*.zip` durante a sessão; o caminho fica em `request.session[IMPORT_FOTOS_PREVIEW_SESSION_KEY]['zip_path']` e é deletado após import (ou ao iniciar nova validação).
- No save: ordem alfabética dos arquivos da pasta, primeiro vira `principal=True`. Tudo dentro de `transaction.atomic()` por produto. Re-checagem `ProdutoImagem.filter(produto_id=...).exists()` antes do save protege contra concorrência. Cache de categoria invalidado.
- Validação de magic bytes acontece automaticamente via `ProdutoImagem.clean() → validate_image_upload`.

**Template:** `templates/admin/produtos/importar_fotos.html` (mesmo layout do `importar.html`).

### Importação de produtos — fix de duplicate de cor (2026-04-27)

`ProdutoAdmin._importar_preview_confirmado` (`apps/produtos/admin.py`) agora usa cache local + `filter(nome__iexact)` antes do `CorPadrao.objects.create()`. Antes, se a planilha tinha **a mesma cor nova em várias linhas** (cor que ainda não existia no banco), o validador marcava todas como "será criada"; no import, a 1ª criava com sucesso e a 2ª disparava `{'nome': ['Cor padrão com este Nome da cor já existe.']}` por unique constraint. Agora a 1ª cria, as demais reusam via dict `cores_criadas_no_import` (chave normalizada via `_texto_importacao_chave`).

### Página de produto — calcular frete não respondia ao clique (2026-04-27)

Bug: a IIFE de "Calcule o Frete" (`templates/produtos/detalhe.html`, ~linha 874) vive **fora** do callback `DOMContentLoaded` (que termina por volta da linha 802). Ela tentava ler `variacaoSelecionada` — variável `let` declarada **dentro** do `DOMContentLoaded`, portanto inacessível de fora. Resultado: `ReferenceError` antes de qualquer fetch → "clico e nada acontece".

Fix: `resolverVariacao()` agora também atualiza `window.variacaoSelecionada`. A IIFE de frete lê `window.variacaoSelecionada`, com fallback `va ? (va.prazo_confeccao_dias || 0) : 0` quando o usuário ainda não escolheu cor/tamanho. O `variacoes_json` em `apps/produtos/views.py` já incluía `prazo_confeccao_dias` (via `prazo_total_adicional_dias`), então o cálculo agora soma o prazo de confecção corretamente também na página de produto (já era correto no checkout via `Max('prazo_confeccao_dias')` em `apps/pedidos/views.py → calcular_frete`).

### Nginx — limite específico para rota de import de fotos (2026-04-27)

`/etc/nginx/sites-available/della_site` ganhou um bloco `location` específico **antes do `location /` genérico** para a rota `/painel/produtos/produto/importar-fotos/`:

```nginx
location = /painel/produtos/produto/importar-fotos/ {
    proxy_pass         http://della_site_app;
    proxy_http_version 1.1;
    proxy_set_header Host              $http_host;
    proxy_set_header X-Real-IP         $remote_addr;
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_redirect       off;
    proxy_read_timeout   600s;
    proxy_send_timeout   600s;
    proxy_connect_timeout 10s;
    client_max_body_size 500M;
    client_body_timeout  600s;
}
```

Por que: o `client_max_body_size 50M` global era bom para uploads normais (foto avulsa, banner) mas não comportava ZIP de fotos com vários produtos (~100MB+). O bloco `location =` é **exato** (apenas essa URL) — outras rotas continuam protegidas pelo limite menor.

Validação: `sudo nginx -t && sudo systemctl reload nginx`. Aplicado e funcional em 2026-04-27 (testado com ZIP de 105MB com 341 fotos).

### E-mail de carrinho abandonado

- **Faixa dourada do topo:** título reduzido para `Olá, NOME! Sua seleção ainda está disponível`.
- **Texto principal atualizado:** substituído por:
  `Você selecionou peças exclusivas da D'ELLA que foram produzidas em quantidade limitada e elas ainda estão reservadas para você. Finalize agora e aproveite!`
- **Rodapé simplificado:** removida a frase `D'ELLA INSTORE — PORQUE SER ÚNICA NUNCA SAI DE MODA`.
- **Ajustes visuais:** altura da faixa dourada e da faixa preta do rodapé reduzidas; conteúdo centralizado.

- Filtros: `email_enviado`, `recuperado`; busca por e-mail, nome, CPF

### Formatação de preços no e-mail

Função `_brl(valor)` em `emails.py` converte qualquer valor numérico/string para padrão brasileiro:
`326.0` → `326,00` | `1234.5` → `1.234,50`

O contexto do template recebe `itens` (subtotais formatados) e `total_fmt` — nunca usar `ca.itens` ou `ca.total` diretamente no template de e-mail.

### Remetente

`DEFAULT_FROM_EMAIL = "D'ELLA Instore <contato@dellainstore.com.br>"` em `core/settings/base.py`.
O "via gy.d.sender-sib.com" que aparece no Outlook é do Brevo (Return-Path domain). Para remover exige configurar Custom Return-Path no painel do Brevo.

### Disparo automático via cron (recomendado)

```bash
# Toda hora: envia para carrinhos abandonados entre 1h e 48h sem compra
0 * * * * cd /var/www/della-sistemas/projetos-claude/site_della && \
  /var/www/della-sistemas/projetos-claude/site_della/venv/bin/python \
  manage.py enviar_emails_carrinho_abandonado \
  --settings=core.settings.production \
  >> logs/carrinho_abandonado.log 2>&1
```

Parâmetros do command:
- `--horas N` — mínimo de inatividade para enviar (padrão: 1h)
- `--max-horas N` — não envia para carrinhos mais velhos que N horas (padrão: 48h)
- `--dry-run` — simula sem enviar e-mails

---

## Atualizações 2026-04-27 — Admin Fotos do Produto (Card Strip)

### Interface visual de fotos (card strip)

O admin de produto substituiu a tabela numérica de fotos por um painel visual com cards arrastáveis:

- **Strip de cards** (`della-fotos-panel` / `.della-fotos-track`): mostra as fotos como cards de ~148×188px com pré-visualização, botão × para remover e seta de download.
- **Reordenar**: arrastar cards horizontalmente reordena as fotos e atualiza os campos `ordem` automaticamente.
- **1ª foto sempre principal**: a foto na posição 0 (primeiro card do strip) é automaticamente marcada como `principal=True` ao salvar. Não há mais botão manual de "principal" — a ordem define qual é a principal.
- **Upload via "Escolher imagens"**: botão no cabeçalho do painel abre seletor múltiplo de arquivos.
- **Upload via arrastar do desktop**: arrastar arquivos do computador diretamente sobre o strip adiciona novas fotos.
- **Deletar nova foto**: botão × em cards de fotos ainda não salvas esvazia o input de arquivo (`fileInput.files = new DataTransfer().files`) para o Django ignorar a linha. Motivo: novas linhas em Django formsets com `can_delete_extra=False` (padrão) não têm checkbox DELETE — só limpar o input funciona.
- **Deletar foto salva**: botão × em cards de fotos já salvas marca o checkbox `DELETE` para o Django deletar no banco.
- **Preview de foto nova**: usa cache de `data:` URLs gerado pelo FileReader (`dataUrlCache[prefix]`). O strip é reconstruído no callback `reader.onload` (após o FileReader terminar assincronamente), garantindo que a imagem esteja disponível. CSP `img-src` inclui `blob:` para suporte a blob URLs em casos não-cacheados.
- **Sem botão de três pontos**: os cards são arrastáveis diretamente (sem botão handle — foi removido por confundir o usuário).
- **CSS**: `della_admin.css` seção 22 (strip) + seção 24 (variação + dragover).
- **JS**: `produto_admin.js` → `buildPhotoCard`, `buildPhotoCardStrip`, `setupCardDragAndDrop`, `refreshOrdemFromStrip`, `refreshPrincipalFromStrip`, `initAutoPrincipal`, `dataUrlCache`.

### Foto por cor — botão câmera na linha de variação

- **Botão câmera** (`.della-var-foto-btn`) inserido em `td.field-cor` (célula do dropdown de cor), **antes** do select.
- Layout visual por linha: `[miniatura vinculada] + [select dropdown de cor]` | `[bolinha de cor]`
- Ao clicar no botão → abre picker visual das fotos do produto → escolhida → vínculo salvo no formset oculto `#fotos_por_cor-group` (via `setCorFotoInGroup`).
- O formset `#fotos_por_cor-group` está oculto (`display: none !important`) — o vínculo é gerenciado via JS, o Django ainda processa os dados ao salvar.
- Se a cor mudar no dropdown, o thumb do botão é atualizado automaticamente com `getCorFotoMapFromGroup()`.
- **CSS**: `#variacoes-group td.field-cor { display: flex; flex-direction: column; align-items: flex-start; gap: 4px }` para empilhar miniatura + select.

### CSP — img-src blob:

`core/settings/base.py → CONTENT_SECURITY_POLICY['DIRECTIVES']['img-src']` agora inclui `"blob:"`. Necessário para que blob URLs criados por `URL.createObjectURL` (fallback do preview antes do FileReader terminar) possam ser usados em `<img>` no admin sem serem bloqueados pelo CSP.

---

## Atualizações 2026-04-28

### Cookie Consent (LGPD) — banner + modal de personalização

Banner fixo no rodapé com 2 botões: **"Customizar"** e **"Aceitar tudo"**. Modal de customização com 3 categorias:
- **Necessários** (sempre ativo) — login, carrinho, CSRF
- **Análise** (toggle) — futuro Google Analytics
- **Marketing** (toggle) — Meta Pixel

**UX:**
- Modal abre com toggles **já ligados por padrão** — "Salvar escolhas" sem mexer = aceita tudo (decisão UX explícita do cliente)
- Botão vermelho "Apenas necessários" desliga tudo exceto necessários
- Link **"Preferências de Cookies"** no rodapé (coluna D'ELLA Instore) reabre o modal a qualquer momento

**Persistência:**
- Cookie `della_consent` (JSON `{v, necessary, analytics, marketing, ts}`) — `SameSite=Lax; Secure` (Secure só se HTTPS)
- Validade: **6 meses** (recomendação ANPD)
- Versão do schema (`v: 1`) — bump para forçar reaceitação após mudanças

**Evento global:**
- `document.dispatchEvent(new CustomEvent('della:consent', { detail: data }))` é disparado toda vez que o consent muda
- Hook usado pelo Meta Pixel para carregar dinamicamente quando o usuário consente

**Mobile — bug crítico do `flex-grow`:**
- O `<p class="della-cookie-banner-text">` tinha `flex: 1 1 360px` (para layout desktop horizontal)
- No mobile com `flex-direction: column` + `align-items: stretch`, isso fazia o `<p>` **esticar verticalmente** para preencher o container, criando uma "tarja preta" enorme entre texto e botões
- Fix: `flex: 0 0 auto !important` no `.della-cookie-banner-text` e `.della-cookie-banner-acoes` no media query mobile (~768px)
- Também removidos `backdrop-filter: blur(8px)` e `box-shadow` no mobile (causavam vazamento visual no iOS Safari)

**Newsletter popup:**
- Suprimido enquanto o banner de cookies estiver visível (evita 2 popups sobrepostos no mobile)
- `if (cookieBanner && cookieBanner.style.display !== 'none') return;` no `setTimeout` do popup

**Arquivos:**
- `templates/base.html` — banner + modal injetados antes do popup-newsletter; link "Preferências de Cookies" no rodapé
- `static/js/della.js` — IIFE de cookie consent (~100 linhas) no fim do `DOMContentLoaded` + função `carregarMetaPixel()` global
- `static/css/della.css` — estilos do banner/modal/toggles + responsive (~280 linhas)

### Meta Pixel — integração completa com consent gate

**Pixel ID:** `1626695288613433` em `.env` como `META_PIXEL_ID`. Settings expostos via `apps/produtos/context_processors.py` → `META_PIXEL_ID` no contexto global. CSP libera `connect.facebook.net` (script-src) e `www.facebook.com` (img-src) em `core/settings/base.py`.

**Carregamento condicional:**
- Pixel **NÃO carrega** sem `consent.marketing === true`
- Função `carregarMetaPixel()` em `della.js` injeta o snippet oficial dinamicamente (não está no HTML)
- Listener no evento `della:consent` ativa o pixel quando o usuário consentir pela 1ª vez
- Snippet montado via JS lê `document.body.dataset.metaPixelId` (atributo `data-meta-pixel-id` no `<body>` do `base.html`, renderizado só se `META_PIXEL_ID` existir)

**Eventos disparados:**

| Evento | Local | Dados |
|---|---|---|
| `PageView` | Toda página (após carregar pixel) | — |
| `ViewContent` | `templates/produtos/detalhe.html` | `content_ids`, `content_name`, `value`, `currency` |
| `AddToCart` | Handler genérico `[data-produto-id]` em `della.js` | `content_ids`, `value`, `currency` |
| `InitiateCheckout` | `templates/checkout/index.html` | `value`, `num_items`, `currency` |
| `Purchase` | `templates/checkout/confirmacao.html` | `value`, `content_ids`, `num_items`, `order_id` |

**Mecanismo dos eventos custom (ViewContent/InitiateCheckout/Purchase):**
- Cada template renderiza `<script type="application/json" data-meta-event="EventName">{...dados...}</script>`
- Função `dispararMetaEventosCustom()` em `della.js` lê todos os scripts com `data-meta-event` no DOM e dispara via `fbq('track', evento, dados)` logo após o pixel carregar
- Valores monetários renderizados com `{% load l10n %}` + filtro `|unlocalize` para garantir ponto decimal (não vírgula)
- Strings escapadas com `|escapejs` (especialmente `produto.nome` e `pedido.numero`)

**LGPD compliance:**
- Sem consent → `<script>` da Meta nunca é injetado (zero requisições para `connect.facebook.net` ou `www.facebook.com`)
- Com consent → pixel carrega e dispara todos os eventos da página + futuras navegações
- Decisão pode ser revogada a qualquer momento pelo link "Preferências de Cookies" no rodapé

**Configurações na Meta (painel Gerenciador de Eventos):**
- **Categorias Especiais de Anúncios:** nenhuma marcada (loja de moda → segmentação normal sem restrições)
- **Correspondência avançada automática:** ativada — Meta hasheia SHA-256 client-side dados do formulário (email/telefone) antes de enviar. Cobre LGPD por já termos consent flow

**Próximo passo:** API de Conversões (server-side) — implementar quando rodar campanhas pagas pra valer (ganho de 17.8% custo/resultado segundo a Meta, mas exige código no backend para enviar eventos via API + hash de PII).

### Foto por Cor — botão "Remover vínculo" no modal

No modal de seleção de foto da variação (`showColorPhotoPicker` em `produto_admin.js`), adicionado botão vermelho **"Remover vínculo"** no rodapé do modal — visível APENAS quando já existe vínculo cor↔foto. Ao clicar:
- Marca `DELETE` no formset oculto `fotos_por_cor-group` para a cor correspondente
- Limpa o select de imagem da linha
- Atualiza o botão da variação para o placeholder de câmera

Função `removeCorFotoFromGroup(corId, afterCb)` em `produto_admin.js` (~30 linhas). `showColorPhotoPicker` ganhou parâmetro opcional `onRemoveCb` — se informado e já existe vínculo, exibe o botão. Estilo `.della-foto-picker-remove` em `della_admin.css` (borda/texto vermelhos, hover preenchido).

### Admin Produto — campo "Categoria pai" antes da Subcategoria

Fieldset "Identificação" agora tem 4 campos nessa ordem: `nome`, `slug`, `categoria_pai`, `categoria` (relabel para "Subcategoria"). O dropdown de "Subcategoria" filtra dinamicamente para mostrar apenas as filhas do pai escolhido.

**Implementação:**
- `apps/produtos/forms.py`:
  - Widget `CategoriaSubSelect` (extends `forms.Select`) sobrescreve `create_option` para adicionar `data-parent="<id>"` em cada `<option>` — JS usa esse atributo para filtrar
  - Form `ProdutoAdminForm` adiciona campo virtual `categoria_pai` (ModelChoiceField com queryset de categorias raiz ativas), pré-seleciona o pai a partir de `categoria.parent_id` ao editar, valida que sub escolhida é filha do pai
- `apps/produtos/admin.py`:
  - `form = ProdutoAdminForm`
  - `formfield_for_foreignkey` para `categoria` aplica o widget custom + queryset filtrado por subcategorias (`parent__isnull=False`) — **forma idiomática para admin** (preserva `RelatedFieldWidgetWrapper`)
- `static/admin/js/produto_admin.js`:
  - `initCategoriaPaiFiltro()` captura todas as opções com `data-parent` na inicialização, filtra ao trocar o pai

**Bug encontrado durante debug — `ModelChoiceIteratorValue`:**
- O admin do Django passa `ModelChoiceIteratorValue` (não int) como `value` no `create_option` do widget
- `int(value)` levantava `TypeError` silenciosamente, fazendo o widget renderizar opções **sem** o `data-parent`
- Fix: `int(str(value))` — `str(ModelChoiceIteratorValue)` retorna o ID como string em ambos os casos (admin e ChoiceField simples)

### Categoria — cascata `ativa` pai → subs

No método `save()` do model `Categoria` (`apps/produtos/models.py`):
- Ao salvar uma categoria PAI (sem `parent_id`), detecta se a flag `ativa` mudou comparando com `Categoria.objects.only('ativa').get(pk=self.pk)`
- Se mudou, propaga via `Categoria.objects.filter(parent_id=self.pk).update(ativa=self.ativa)` para todas as subcategorias
- Usa `.update()` (não `.save()`) — não dispara signals/clean das subs, é rápido, vai direto no banco

Comportamento:
- Inativar pai → todas subs viram inativas
- Reativar pai → todas subs voltam ativas (mesmo as que estavam inativas individualmente antes)
- Mexer só em sub → não afeta pai/irmãs (comportamento normal)
- Editar nome/slug do pai sem mexer em ativa → no-op (subs não tocadas)

Funciona via admin, scripts, shell — qualquer caminho que chame `.save()`. Não funciona com `.update()` em massa no QuerySet (limitação conhecida do Django).

**Atenção:** subcategorias que já estavam desalinhadas no banco (pai inativo + sub ativa, situação criada antes desta lógica) não são corrigidas automaticamente. Para alinhar: reativar e re-inativar o pai no admin para disparar a nova lógica.

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
