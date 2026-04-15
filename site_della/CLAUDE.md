# D'ELLA Instore — Site E-commerce Premium
**CLAUDE.md — Contexto completo para continuação do desenvolvimento**

---

## Visão Geral do Projeto

Loja virtual de moda feminina premium chamada **D'ELLA Instore**.
- **Stack:** Django 5.1 + PostgreSQL + Gunicorn + Nginx
- **Frontend:** HTML/CSS/JS com Tailwind CSS (CDN) + CSS customizado
- **VPS:** Ubuntu, 1 vCore, 1.9GB RAM, IP `159.203.101.232`
- **Domínio de testes (ativo):** `novo.dellainstore.com.br` — site no ar com HTTPS ✓
- **Domínio definitivo:** `www.dellainstore.com.br` (ainda aponta para site antigo — migrar quando aprovado)
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

### Pendência Nginx
O `scripts/nginx_della_site.conf` foi atualizado para `client_max_body_size 50M`, mas o arquivo ao vivo em `/etc/nginx/sites-available/della_site` ainda tem 10M. Aplicar manualmente:
```bash
sudo sed -i 's/client_max_body_size 10M;/client_max_body_size 50M;/g' /etc/nginx/sites-available/della_site
sudo nginx -t && sudo systemctl reload nginx
```

---

## Quando Trocar para www.dellainstore.com.br

1. Editar `/etc/nginx/sites-available/della_site` — comentar bloco "testes", descomentar bloco "produção"
2. `sudo certbot --nginx -d www.dellainstore.com.br -d dellainstore.com.br`
3. Atualizar `ALLOWED_HOSTS` no `.env`
4. Atualizar `SITE_URL` no `.env`
5. Atualizar `BLING_REDIRECT_URI` no `.env`
6. `sudo systemctl reload nginx && sudo systemctl restart gunicorn_della_site`

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
| `Pedido` | numero (DI-XXXX), cliente, dados copiados, endereço copiado, subtotal, frete, total, status, gateway, codigo_rastreio, bling_pedido_id |
| `ItemPedido` | pedido, produto, variacao, nome/preco copiados, quantidade |
| `HistoricoPedido` | log de mudanças de status |

### `apps/bling/`
| Model | Campos |
|---|---|
| `BlingToken` | access_token, refresh_token, expira_em |
| `BlingLog` | tipo, pedido, sucesso, payload_enviado, resposta, erro |

---

## Navbar (base.html)

**Logo D'ELLA Instore:** duas linhas empilhadas — `.navbar-logo-della` (Playfair Display, 1.45rem, letra-spacing 0.18em) e `.navbar-logo-instore` (Jost, 0.5rem, letra-spacing 0.5em). Mesma estrutura no footer (`.footer-logo-della` / `.footer-logo-instore`).

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

**Selos visuais** (`.footer-selo-visual`): SSL Seguro, Compra Segura, LGPD — com ícone dourado + borda fina. Substituem os antigos `.footer-selo` (só texto).

**Nota:** A coluna "Loja" foi removida. "Trocas" foi movida para Ajuda. Não restaurar a coluna "Loja".

---

## Homepage (home/index.html)

Seções em ordem:
1. **Hero slider** — banners do admin (BannerPrincipal), fallback estático. Dots no canto inferior direito. Botão mute no canto inferior **esquerdo**. Hero aparece ABAIXO do menu (`margin-top: var(--navbar-total)`)
2. **Destaques da semana** — produtos com `destaque=True`
3. **Mini banners** — MiniBanner do admin (2 colunas lado a lado, **retrato 3:4**, foto de fundo). Layout mantém 2 colunas no mobile também (cards mais estreitos, texto/botão reduzidos). Ver CSS em `static/css/della.css` — `.mini-banner { aspect-ratio: 3 / 4 }`.
4. **Look da semana** — foto + pontos "+" posicionados em % configuráveis pelo admin (editor visual). Cada ponto é um FK direto para o produto (`produto_ponto1/2/3`)
5. **Manifesto** — texto fixo da marca
6. **Depoimentos** — Avaliacao aprovadas
7. **Instagram** — banner CTA estático (@dellainstore)
8. **Newsletter** — AJAX

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
- Foto em **retrato 3:4** (ex: 900×1200px). O card ocupa metade da largura em 2 colunas e tem altura proporcional via `aspect-ratio: 3/4` — nunca deforma a imagem
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
- `.hero { margin-top: var(--navbar-total); }` — hero abaixo do menu (não atrás)
- `.hero-mute-btn { bottom: 2rem; left: 2rem; }` — botão mute no canto inferior esquerdo (longe dos dots)
- `.produto-acoes` usa `visibility: hidden/visible` (não `display:none`) para transição suave + pointer-events corretos
- `.variacao-cor { box-shadow: inset 0 0 0 1px rgba(0,0,0,0.15); }` — torna bolinhas brancas visíveis
- **Hero slider:** timer = 6 segundos (`SLIDE_DURACAO = 6000` em `della.js`). Swipe horizontal (touchstart/touchend) na seção `#hero-slider` troca slides no mobile; threshold 40px e ignora gesto vertical. Dots com `z-index: 10` e `touch-action: manipulation` — `touchstart` nos dots chama `e.stopPropagation()` para não acionar o swipe listener ao mesmo tempo. IDs dos `<video>` foram removidos (eram duplicados, causavam comportamento inconsistente).
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
| **Mini banners** | 900×1200px | 3:4 (retrato) | JPG — o card é retrato, texto no rodapé |
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

## Auditoria de Segurança — 2026-04-14

Auditoria completa rodada nesta data. Resultado detalhado abaixo — usar como baseline antes de migrar o domínio definitivo.

### ✅ Correções já aplicadas

**C1 — IDOR em `pix_gerar`, `pix_status` e `confirmacao_pedido`** (CRÍTICO)
- Antes: qualquer um que adivinhasse `DI-XXXX` acessava QR Pix (com valor) + status; `confirmacao_pedido` também passava quando `pedido.cliente=None`.
- Depois: nova helper `_pode_acessar_pedido(request, pedido)` em `apps/pagamentos/views.py` — autoriza apenas staff, dono logado, ou número presente em `session['pedidos_guest']` / `session['ultimo_pedido']`. `confirmacao_pedido` usa a mesma regra unificada.
- `apps/pedidos/views.py → _processar_checkout` agora registra cada pedido criado em `session['pedidos_guest']` (limite: últimos 20), garantindo que guest checkout consiga abrir a confirmação no mesmo dispositivo.

**C4 — OAuth Bling validando `state`** (CRÍTICO)
- `apps/bling/views.py`: `oauth_autorizar` gera `secrets.token_urlsafe(32)` e guarda em `session['bling_oauth_state']`. `oauth_callback` (agora também `@staff_member_required`) compara com `secrets.compare_digest`. Sem match → recusa antes de trocar o code. Fecha OAuth CSRF / code injection.

**M1 — `.env` com permissão 600** — antes 664 (world-readable). `chmod 600 /var/www/della-sistemas/projetos-claude/site_della/.env`.

### ⏳ Pendências críticas antes de ir ao domínio definitivo

**C2 — Webhook Bling sem assinatura** (`apps/bling/views.py:webhook`)
- `@csrf_exempt` aceita POST anônimo → atacante que conheça `bling_pedido_id` altera status (entregue/cancelado) ou injeta rastreio falso.
- Fix: validar HMAC do header `X-Bling-Signature` com segredo do `.env` (`BLING_WEBHOOK_SECRET`). Rejeitar com 401 se não bater.

**C3 — Webhooks PagSeguro e Stone sem assinatura** (`apps/pagamentos/views.py`)
- PagSeguro (`pagseguro_notificacao`) e Stone (`stone_webhook`) hoje só logam e retornam OK. Quando o `TODO:` for implementado, **nunca confiar no corpo**:
  - PagSeguro: reconsultar `notificationCode` via API autenticada com credenciais.
  - Stone: validar header `X-Stone-Signature` (HMAC) antes de processar.

**A1 — Upload sem validação em conteúdo** (`apps/conteudo/models.py` + `apps/produtos/models.py:Categoria.imagem`)
- `validate_image_upload` (magic bytes, em `apps/core_utils/sanitize.py`) só está em `ProdutoImagem`. Adicionar `validators=[validate_image_upload]` em `BannerPrincipal.foto/foto_mobile`, `MiniBanner.foto`, `LookDaSemana.foto` e `Categoria.imagem`.

**A2 — Vídeos de banner (`FileField`) sem validação**
- `BannerPrincipal.video` e `video_mobile` aceitam qualquer binário até 50MB. Limitar extensões (.mp4/.webm) e tamanho via `FileExtensionValidator` + validador custom.

**M2 — `CSRF_TRUSTED_ORIGINS` explícito em `production.py`**
```python
CSRF_TRUSTED_ORIGINS = [
    'https://novo.dellainstore.com.br',
    'https://www.dellainstore.com.br',
    'https://dellainstore.com.br',
]
```

**M3 — CSP com `'unsafe-inline'` em script/style** (médio prazo)
- Necessário hoje pela CDN do Tailwind. Compilar Tailwind localmente (`npm run build`) para remover `'unsafe-inline'` de `script-src` e fortalecer proteção XSS.

### ✅ Pontos já bons (não regredir)

- `.env` fora do git (`.gitignore` + `.env.example`); só `.gitkeep` em `logs/cache/media`
- `SECRET_KEY` via `config()`; `ALLOWED_HOSTS` explícito (sem `*`)
- HSTS 1 ano + preload, `SECURE_SSL_REDIRECT`, cookies `Secure` + `SameSite=Lax`
- `X-Frame-Options: DENY` (Django + Nginx)
- django-axes 5 tentativas → 1h lockout por IP+user
- auto-escape template ON, ORM-only (zero SQL raw)
- recuperação de senha não enumera e-mails (`enviado=True` sempre + `except: pass` no SMTP)
- `next_url` validado (`startswith('/')`) no login
- Nginx bloqueia `.env`, `.git`, `.sql`, scripts em `/media/`

### Ordem sugerida para a próxima sessão de segurança
1. C2 (HMAC webhook Bling) — precisa do segredo no painel Bling → Webhooks.
2. C3 quando ligar pagamento real (reconsulta PagSeguro + HMAC Stone).
3. A1/A2 (validators de upload em Banner/Mini/Look/Categoria e vídeos).
4. M2 (`CSRF_TRUSTED_ORIGINS`) antes de migrar para `www.dellainstore.com.br`.
5. M3 (compilar Tailwind local) em fase posterior.

### Helper reutilizável: `_pode_acessar_pedido`
Se surgir nova view que expõe dados de `Pedido`, usar o mesmo pattern (definido em `apps/pagamentos/views.py`):
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
ALLOWED_HOSTS=novo.dellainstore.com.br,www.dellainstore.com.br,dellainstore.com.br,159.203.101.232
DB_NAME=della_site
DB_USER=della_user
DB_PASSWORD=...
DB_HOST=localhost
DB_PORT=5432
EMAIL_HOST=smtps.uhserver.com
EMAIL_PORT=465
EMAIL_USE_SSL=True
EMAIL_USE_TLS=False
EMAIL_HOST_USER=contato@dellainstore.com.br
EMAIL_HOST_PASSWORD=...
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

## Pendências

| Item | Prioridade |
|---|---|
| Aumentar `client_max_body_size` para 50M no nginx ao vivo (requer sudo) | Alta |
| E-mail SMTP (porta 465) — aguardando liberação Digital Ocean | Média |
| Migrar para `www.dellainstore.com.br` | Quando aprovado |
| C2 — HMAC webhook Bling (precisa segredo no painel Bling → Webhooks) | Alta (antes de ir ao ar) |
| A1/A2 — validators de upload em Banner/MiniBanner/LookDaSemana/Categoria e vídeos | Alta (antes de ir ao ar) |
| M2 — `CSRF_TRUSTED_ORIGINS` em `production.py` antes de migrar domínio | Média |
| Instagram API (feed real de fotos) | Opcional |

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
```

---

## Como Continuar numa Nova Conversa

Cole exatamente esta frase:

> **"Continuando o desenvolvimento do site Della Instore. Leia o arquivo `/var/www/della-sistemas/projetos-claude/site_della/CLAUDE.md` e me aguarde para o próximo ajuste."**
