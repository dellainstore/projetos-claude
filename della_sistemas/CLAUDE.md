# CLAUDE.md — della_sistemas (Painel Web Unificado D'ELLA)

## O que é este projeto

Painel web Django que unifica os apps Streamlit internos da D'ELLA em uma única interface com identidade visual da marca, menu lateral, sistema de usuários com permissões granulares por módulo, HTTPS e suporte a PWA (instalável no celular sem App Store).

**URL produção:** `https://sistemas.dellainstore.com` ✅ (em produção)
**Porta interna (Gunicorn):** Unix socket `/run/della-sistemas/gunicorn.sock`
**Stack:** Django 5.1 + HTMX + WhiteNoise + SQLite
**DNS:** Cloudflare (não UOL) — registro A `sistemas` → `159.203.101.232`, nuvem cinza (DNS only)

---

## Estrutura de pastas

```
della_sistemas/
├── manage.py
├── requirements.txt
├── .env                    # Nunca commitar — credenciais reais
├── .env.example
├── gunicorn.conf.py        # Unix socket, 4 workers, logs em ~/logs/della-sistemas/
├── config/                 # Settings, urls, wsgi
├── apps/
│   ├── core/               # Auth, User model, home, gerenciamento de usuários
│   │   ├── models.py       # User com permissoes JSONField + tem_perm()
│   │   ├── permissions.py  # PERMISSION_TREE + DEFAULT_PERMS_BY_PAPEL
│   │   ├── decorators.py   # perm_required() + papel_required() (legado)
│   │   ├── backends.py     # CaseInsensitiveBackend (login case-insensitive)
│   │   └── templatetags/
│   │       └── core_extras.py  # filtro get_perm (acessa dict dinâmico em templates)
│   ├── produtos/           # Módulo produtos (portado do Streamlit)
│   │   ├── views/          # incluir, aprovacoes, historico, manutencao, precos
│   │   └── services/       # Serviços Python
│   │       ├── bling/      # API client Bling (api.py tem GET/POST/PATCH/PUT/PUT_raw)
│   │       │               # ⚠️ _respect_rate_limit() usa threading.Lock (thread-safe)
│   │       ├── business/   # Regras de negócio (approvals, catalog, lookup, pricing...)
│   │       │   └── lookup.py   # get_sizes() ordena PP>P>M>G>GG ou numérico
│   │       ├── precos.py   # listar_cores_por_modelo() usa ThreadPoolExecutor(max_workers=4)
│   │       ├── db.py       # get_conn() → lê do inclusoes.db via PRODUTOS_DB_PATH
│   │       └── config.py   # Lê config do Django settings ou env
│   ├── metas/              # Módulo Metas
│   │   ├── models.py       # Funcionario, MetaFuncionario, MetaCanal
│   │   ├── urls.py         # app_name="metas", 7 rotas
│   │   ├── views/
│   │   │   ├── dashboard.py    # dashboard com filtros de período
│   │   │   └── cadastro.py     # CRUD funcionárias + metas individual/canal
│   │   ├── services/
│   │   │   └── relatorio.py    # toda lógica de negócio (carregar CSV, calcular, etc.)
│   │   ├── migrations/
│   │   │   └── 0001_initial.py
│   │   └── templatetags/
│   │       └── metas_extras.py # filtros: brl (R$ 1.234,56) e pct_css (% sem vírgula)
│   └── pedidos/            # Módulo Pedidos (sincronização Bling + pagamentos)
│       ├── models.py       # PedidoBling, ParcelaPedido, HistoricoDataPedido, BaixaPedido
│       ├── urls.py         # app_name="pedidos", rotas pendentes/pagamentos/htmx
│       ├── views/
│       │   ├── pedidos.py      # pendentes, dashboard, historico, sync_htmx
│       │   └── pagamentos.py   # pendentes, confirmados, resumo, dar_baixa, dar_baixa_parcela
│       ├── services/
│       │   └── sync.py         # sincronizar_pedidos() + _sync_parcelas()
│       └── migrations/
│           ├── 0001_initial.py
│           └── 0004_parcela_pedido.py
├── templates/
│   ├── base.html           # Sidebar expansível: Produtos ▸ e Metas & Pedidos ▸
│   ├── login.html
│   ├── home.html
│   ├── usuarios.html
│   ├── usuario_form.html   # Árvore de permissões estilo Bling (grupos expansíveis)
│   ├── produtos/
│   │   └── ...             # incluir, aprovacoes, historico, manutencao, precos
│   └── metas/
│       ├── dashboard.html           # dashboard principal
│       └── cadastro/
│           ├── funcionarios.html
│           ├── funcionario_form.html
│           ├── metas_individual.html
│           └── metas_canal.html
└── static/
    ├── css/della_sistemas.css
    ├── js/htmx.min.js
    ├── icons/                    # Ícones PWA 192/512px + logo-della.webp
    └── manifest.json
```

---

## Banco de dados

**Banco principal do Django:** `db.sqlite3` — usuários, sessões, permissões e **metas**.

**Banco do módulo produtos:** `della_sistemas/data/produtos/inclusoes.db`
— lido e escrito diretamente via `PRODUTOS_DB_PATH` no `.env`. Movido para dentro do
projeto em 2026-06-28 (antes ficava em `app/produtos/data/`, junto do Streamlit já
desativado). O caminho é resolvido por `BASE_DIR / "data" / "produtos"` no settings;
ao trocar, atualizar `.env`, `config/settings.py`, `apps/produtos/services/config.py`
e o cron de `sync_catalog`.

**Tabela `price_history`** (em `inclusoes.db`, criada pelo `services/precos.py`):
— registra todas as alterações de preço: quem mudou, quando, de quanto para quanto.
— também armazena preços de atacado importados via Excel (`tipo='atacado_local'`).

> **IMPORTANTE:** nunca rodar `migrate` para dados de produtos. Só para apps Django (core, auth, sessions, metas).

---

## Variáveis de ambiente (.env)

```env
SECRET_KEY=...
DEBUG=False                  # True apenas em dev local
LANGUAGE_CODE=pt-br          # ⚠️ faz floatformat usar vírgula — usar pct_css para CSS widths
ALLOWED_HOSTS=localhost,127.0.0.1,sistemas.dellainstore.com,159.203.101.232
PRODUTOS_DB_PATH=/var/www/della-sistemas/projetos-claude/della_sistemas/data/produtos/inclusoes.db
BLING_AUTH_DIR=/var/www/della-sistemas/shared/bling_auth
DEPOSITO_ID=7521173180
APPLY_STOCK_ON_PROCESS=1
BLING_CLIENT_ID=...
BLING_CLIENT_SECRET=...
AUTHENTICATION_BACKENDS=apps.core.backends.CaseInsensitiveBackend
```

---

## Sistema de usuários e permissões

### Modelo `apps.core.models.User`

O modelo usa **`permissoes` (JSONField)** como fonte de verdade — não mais o campo `papel`.

```python
user.tem_perm("modulo.chave")  # método principal de verificação
```

Se `permissoes` estiver vazio (usuário criado antes da migration), cai no fallback por `papel` automaticamente.

### Árvore de permissões (`apps/core/permissions.py`)

| Módulo | Chave | Descrição |
|--------|-------|-----------|
| `estoque` | `incluir` | Incluir estoque |
| `estoque` | `historico` | Ver histórico de inclusões |
| `estoque` | `excluir` | Excluir lançamentos |
| `aprovacoes` | `ver` | Ver solicitações pendentes |
| `aprovacoes` | `aprovar` | Aprovar / Rejeitar |
| `precos` | `ver` | Ver preços |
| `precos` | `alterar` | Alterar preços |
| `manutencao` | `sync` | Sincronizar catálogo |
| `manutencao` | `rebuild` | Rebuild variações |
| `manutencao` | `limpeza` | Limpeza de dados |
| `metas` | `ver` | Ver metas e dashboard |
| `metas` | `cadastrar` | Cadastrar funcionárias e metas |
| `metas` | `ver_situacao` | Ver faturamento por situação (Bling) — superadmin/gestor only |
| `em_breve` | `ver` | Ver seção "Em breve" no menu (Estoque / Financeiro) |
| `admin` | `usuarios` | Gerenciar usuários e permissões |

### Properties no User model

| Property | Equivalente |
|----------|-------------|
| `user.pode_incluir` | `tem_perm("estoque.incluir")` |
| `user.pode_aprovar` | `tem_perm("aprovacoes.aprovar")` |
| `user.is_superadmin` | `tem_perm("admin.usuarios")` |
| `user.is_gestor_or_above` | `tem_perm("aprovacoes.aprovar")` |
| `user.pode_ver_metas` | `tem_perm("metas.ver")` |
| `user.pode_cadastrar_metas` | `tem_perm("metas.cadastrar")` |
| `user.pode_ver_situacao_metas` | `tem_perm("metas.ver_situacao")` |
| `user.pode_ver_em_breve` | `tem_perm("em_breve.ver")` |

### Decorators (`apps/core/decorators.py`)

```python
@perm_required("metas.ver")      # usa tem_perm()
@papel_required("superadmin")     # legado — ainda funciona via fallback
@login_obrigatorio                # apenas autenticação
```

### Tela de usuários

`usuario_form.html` exibe a árvore de permissões em grupos expansíveis (estilo Bling):
- Checkbox mestre por grupo (marca/desmarca todos do grupo)
- Chevron para expandir/recolher cada grupo
- Botões "Marcar tudo" / "Desmarcar tudo"
- Checkboxes usam `name="perm_MODULO__CHAVE"` (dois underscores)

---

## Login

- **Case-insensitive:** `neto`, `Neto` e `NETO` funcionam igual
- Backend: `AUTHENTICATION_BACKENDS = ["apps.core.backends.CaseInsensitiveBackend"]`
- Eye toggle (mostrar/ocultar senha) na tela de login

---

## Sidebar (base.html)

Menu lateral com grupos expansíveis via JS `toggleNav(id)`. Grupos com subitens ativos abrem automaticamente via `DOMContentLoaded`.

**Colapsar/expandir (desktop):** botão `.ds-sidebar-tab` (tab fixada na borda direita da sidebar). Clique chama `toggleSidebar()` que alterna `body.sidebar-colapsada` e persiste estado em `localStorage` chave `ds-sidebar-colapsada`. Ícone: ◀ colapsado → ▶ expandido.

```
Dashboard
─────────
▸ Produtos                   (pode_incluir OR pode_aprovar OR is_superadmin)
    + Incluir Estoque        (estoque.incluir)
    ✓ Aprovações             (aprovacoes.aprovar)
    $ Preços                 (precos.ver via pode_aprovar)
    ≡ Histórico ▸            (grupo expansível nested)
        + Inclusões
        $ Preços             (pode_aprovar)
    ⚙ Manutenção            (is_superadmin)
    ▤ Resumo
▸ Metas                      (pode_ver_metas OR pode_cadastrar_metas)
    + Cadastro de Metas      (metas.cadastrar)
    ≡ Metas                  (metas.ver)
▸ Pedidos                    (pode_ver_pedidos)
    ○ Pedidos Em Andamento
    ≡ Pedidos Pendentes
    $ Pagamentos ▸           (grupo expansível nested)
        ▤ Resumo
        ○ Pendentes
        ✓ Confirmados
    ↺ Pedidos Alterados
─────────
Em breve
  Estoque / Financeiro
─────────
Administração
  Usuários                   (is_superadmin)
```

---

## Módulo Metas & Pedidos (`apps/metas/`)

### Modelos (`apps/metas/models.py`)

```python
class Funcionario:
    nome          # "Tina"
    nome_bling    # "TINA DIAS" — deve bater exatamente com campo vendedor do CSV
    ativo         # bool

class MetaFuncionario:
    funcionario   # FK → Funcionario
    ano, mes      # int
    valor         # Decimal
    unique_together: (funcionario, ano, mes)

class MetaCanal:
    canal         # show_room_sp | anaca | atacado | site_instagram
    ano, mes      # int
    valor         # Decimal
    unique_together: (canal, ano, mes)
    # londrina NÃO tem MetaCanal — apenas faturamento no dashboard
```

### Funcionárias cadastradas (com meta individual)

| Nome | nome_bling |
|------|-----------|
| Tina | `TINA DIAS` |
| Michelle | `MICHELLE ALVES FERNANDES` |
| Sara | `SARA OLIVEIRA` |

### Regras de negócio (em `services/relatorio.py`)

**Canais e situações Bling:**

| Canal | Situações no Bling | Meta |
|-------|--------------------|------|
| `show_room_sp` | `Atendido` | Canal (Jan-Jun) / individual (Jul+) |
| `anaca` | `Atendido-Anaca` | Canal (Jan-Jun) / individual (Jul+) |
| `atacado` | `Atendido-Atacado` | Sempre por canal |
| `site_instagram` | `Atendido-Site`, `Atendido-Instagram` | Sempre por canal |
| `londrina` | `Atendido-Londrina` | **Sem meta** — só faturamento |

**Meta individual conta apenas para:** `{"Atendido", "Atendido-Anaca"}`

**Transição histórica:**
- Jan–Jun/2026: metas individuais existem retroativamente (Tina = Show Room, Michelle = Anacã, Sara = só Jun)
- `ANO_MES_INICIO_INDIVIDUAL = (2026, 1)` — `usa_metas_individuais()` retorna True a partir daí

**Histórico importado:**
- 24 MetaCanal criados: Jan–Jun/2026 × 4 canais (exceto Londrina)
- Show Room SP Jun/2026 canal = R$ 60.000 (Tina 50k + Sara 10k)
- Metas individuais Jan–Jun criadas conforme canais históricos

### Views e URLs

```
GET /metas/                                    → dashboard (view_dashboard)
GET /metas/cadastro/funcionarios/              → lista funcionárias
GET /metas/cadastro/funcionarios/novo/         → criar
GET /metas/cadastro/funcionarios/<pk>/editar/  → editar
POST /metas/cadastro/funcionarios/<pk>/toggle/ → ativar/desativar
GET/POST /metas/cadastro/metas-individual/     → metas individuais por mês
GET/POST /metas/cadastro/metas-canal/          → metas de canal por mês
```

### Dashboard (`templates/metas/dashboard.html`)

**Filtros de período:**
- **Mês Atual** → `?filtro=atual`
- **Mês Anterior** → `?filtro=passado`
- **Personalizado** → `?filtro=custom&ano_ini=&mes_ini=&ano_fim=&mes_fim=` (máx. 12 meses)

Multi-mês: metas somadas, vendas agregadas, labels "Jan/2026 a Mar/2026".

**Seções:**
1. Totais gerais (faturamento, peças, pedidos)
2. Meta Geral do Período (barra de progresso sobre soma de canais ex-Londrina + /semana)
3. Metas Individuais — cards com barra, % atingido, ≈ R$/semana restante
4. Metas por Canal — cards incluindo Londrina (sem meta, só faturamento)
5. Vendedoras (Geral) — cards com tag "com meta individual"
6. Faturamento por Loja — tabela
7. Por Situação (Bling) — **apenas `metas.ver_situacao`**

**Cálculo "/semana":** `faltam ÷ dias_seg_sab_restantes(ano_fim, mes_fim) × 6`
- Conta dias Seg–Sáb de hoje até o último dia do período
- Retorna 0 se período já encerrou

### Filtros de template (`apps/metas/templatetags/metas_extras.py`)

```python
{{ valor|brl }}      # Decimal/float → "R$ 1.234,56" (formato BR)
{{ pct|pct_css }}    # float → "55.5" (SEMPRE ponto — para style="width:X%")
```

⚠️ **IMPORTANTE:** `LANGUAGE_CODE = "pt-br"` faz `{{ valor|floatformat:1 }}` retornar `"55,5"` (vírgula). Isso QUEBRA `style="width:55,5%"` no CSS — o browser ignora e a barra vira 100%. **Sempre usar `pct_css` para qualquer valor percentual em atributo `style`.**

---

## Módulo Pedidos (`apps/pedidos/`)

Gerencia pedidos Bling, pagamentos (parcelas) e histórico de alterações.

### Modelos (`apps/pedidos/models.py`)

```python
class PedidoBling:
    bling_id, numero, data_pedido, cliente_nome, valor_total
    situacao_id, situacao_nome, forma_pagamento, data_pagamento
    data_corrigida, forma_corrigida  # correções manuais

class ParcelaPedido:
    pedido             # FK → PedidoBling (related_name="parcelas")
    numero             # int — 1, 2, 3...
    valor              # Decimal
    data_vencimento    # DateField nullable
    forma_pagamento    # str — vem do Bling
    baixada            # bool — True quando parcela foi confirmada
    baixada_por        # FK → User nullable
    baixada_em         # DateTimeField nullable
    forma_efetiva      # str — forma conferida manualmente
    data_efetiva       # DateField — data conferida manualmente
    # Meta: ordering=["pedido","numero"], unique_together=[("pedido","numero")]

class HistoricoDataPedido:
    pedido, data_anterior, data_nova, registrado_em

class BaixaPedido:
    pedido     # OneToOneField → PedidoBling
    baixado_por, baixado_em, obs, valor_baixado, forma_efetiva, data_efetiva
```

### Sincronização (`apps/pedidos/services/sync.py`)

- `sincronizar_pedidos(ano)` — busca pedidos do Bling, cria/atualiza `PedidoBling` e chama `_sync_parcelas`
- `_sync_parcelas(pedido, parcelas_raw)` — upsert por `(pedido, numero)`; **preserva** `baixada`, `baixada_por`, `baixada_em`, `forma_efetiva`, `data_efetiva` (não sobrescreve baixas já lançadas)
- ⚠️ Pedidos criados antes da migration `0004_parcela_pedido` não têm parcelas — precisam de uma nova sync para popular

### URLs (`apps/pedidos/urls.py`)

```
GET  pedidos/pendentes/                    → view_pendentes
GET  pedidos/dashboard/                    → view_dashboard
GET  pedidos/pagamentos/pendentes/         → view_pagamentos_pendentes
GET  pedidos/pagamentos/confirmados/       → view_pagamentos_confirmados
GET  pedidos/pagamentos/resumo/            → view_pagamentos_resumo
POST pedidos/htmx/dar-baixa/<pk>/         → view_dar_baixa (baixa todas as parcelas)
POST pedidos/htmx/baixar-parcela/<pk>/    → view_dar_baixa_parcela (baixa parcela individual)
POST pedidos/htmx/salvar-correcao/<pk>/   → view_salvar_correcao
POST pedidos/htmx/sync/                   → view_sync_htmx
GET  pedidos/historico/                   → view_historico
```

### Pagamentos — fluxo de parcelas

**Pendentes (`pagamentos_pendentes.html`):**
- Cada pedido em `<tbody id="grupo-pedido-X" data-forma="...">` — alvo do HTMX e do filtro de forma
- Multi-parcela: linha principal mostra badge `(Nx)` + seta `▶` para expandir/recolher via `toggleParcelas(pk, qtd)`
- Linhas-filho `.linha-parcela-X` ficam `display:none` até expansão
- Cada parcela tem `<form id="form-parcela-X">` com select `forma_conferida` (placeholder "selecionar", sem pré-seleção) e date `data_conferida` pré-preenchido com `data_vencimento`
- **Baixar Tudo** (linha principal): `hx-post="dar_baixa"` → substitui `<tbody>` inteiro com confirmação
- **Baixar Esta** (linha parcela): `hx-post="dar_baixa_parcela"` → substitui `<tr>` individual; se última pendente, a view também remove o `<tbody>` pai via **HTMX OOB swap** `hx-swap-oob="true"`

```html
<!-- Resposta de dar_baixa_parcela quando é a última parcela -->
<tr id="row-parcela-X">✓ Baixada em ...</tr>
<tbody id="grupo-pedido-Y" hx-swap-oob="true"></tbody>
```

**Confirmados (`pagamentos_confirmados.html`):**
- Mesmo padrão de `<tbody id="grupo-conf-X">`, toggle via `toggleConf(pk, qtd)`
- `forma_efetiva` destacada em laranja se diferente de `forma_pagamento` do Bling

**Resumo (`pagamentos_resumo.html`):**
- 3 cards: **PAGO** (azul `#2563eb`) | **EM ATRASO** (vermelho `#dc2626`) | **A RECEBER** (verde `#059669`)
- Tabela de pedidos em atraso ordenada por `min_data` (vencimento mais antigo primeiro)
- View passa `pedidos_atraso` como lista de 3-tuples `(pedido, valor_atraso, min_data)` — **não** atributos com underscore em instâncias de model (Django templates proíbem `_X`)

### Filtros de texto

- **Pedidos Em Andamento** (`pendentes.html`): `<input id="filtro-andamento">` → `filtrarAndamento()`, filtra por `data-busca` nos `<tr>` (numero, cliente, situação)
- **Pedidos Pendentes** (`dashboard.html`): `<input id="filtro-dashboard">` → `filtrarDashboard()`, filtra todas as 3 seções simultaneamente via `.dash-row[data-busca]`

---

## Módulo Preços

Tela em **Produtos → Preços** (acesso: `precos.ver`).

**Ajustar Preços:**
- Autocomplete do modelo: input com `name="q"` + `hx-include="this"` → endpoint `htmx_modelos_precos`
- Ao selecionar modelo: carrega tabela de cores via `htmx_precos_cores` (URL: `htmx/precos/cores/`)
- Carregamento paralelo: `ThreadPoolExecutor(max_workers=4)` + `_respect_rate_limit()` com `threading.Lock`
- Tabela de cores: **SKU | COR | VAREJO | ATACADO | CUSTO** (nesta ordem)
- Atacado: armazenado localmente no `price_history`, exportado como CSV para importar no Bling

**⚠️ Atenção com nomes de URL (não duplicar):**
- `htmx_cores` → endpoint de busca de cores do **incluir** (`htmx/cores/`)
- `htmx_precos_cores` → endpoint de cores com preços do **preços** (`htmx/precos/cores/`)
  Já houve confusão com nome duplicado no passado que quebrou o incluir.

**Histórico de Preços:**
- Registra: data/hora, modelo, cor, SKU, tipo, preço antes → depois, usuário

---

## Módulo Incluir Estoque

**Autocomplete:**
- Inputs de busca usam `hx-include="#ID-do-hidden-input"` onde o hidden tem `name="q"`
  - `#q-base-hidden` (busca de modelo) e `#q-tpl-hidden` (busca de template)
  - O endpoint espera `?q=...`
- Após selecionar modelo: `onBaseSelecionada(base)` chama `htmx.ajax` para `htmx_cores`
- Após selecionar cor: `onCorSelecionada(cor)` chama `htmx_tamanhos`

**Tamanhos:**
- Ordem: PP → P → M → G → GG → XGG (letra) ou crescente numérico
- `_sort_size_key()` em `services/business/lookup.py`
- O template `_tamanhos_form.html` exibe **Varejo + Atacado + Custo** (atacado vem do `price_history`)

**Pipeline pós-aprovação:**
- Ao aprovar via `view_aprovar`: chama `processar_aprovacao()` + `processar_stock_moves()` automaticamente
- Não há botão manual de pipeline (foi removido da tela Manutenção)

---

## Cron de vendas (`/var/www/della-sistemas/jobs/vendas_atendidas.py`)

Gera `/var/www/della-sistemas/data/Relatorio de Vendas Atendidas/vendas_atendidas_{ano}.csv`.

**Coluna `vendedor` (adicionada):**
- A API Bling retorna `vendedor: {"id": 7613793453}` (só ID, nunca nome)
- O script busca `/vendedores` uma vez no início e monta lookup `{id → nome}`
- Linhas históricas sem detalhe ficam com vendedor vazio

**Mapeamento de vendedores (Bling):**

| ID | Nome |
|----|------|
| 7613793453 | TINA DIAS |
| 7616577942 | CRISLAINY SILVERIO GIACOMELLI |
| 15205612892 | MICHELLE ALVES FERNANDES |
| 15596882226 | SARA OLIVEIRA |

**Para re-processar um ano inteiro (backfill vendedor):**
```bash
cd /var/www/della-sistemas
export BLING_CLIENT_ID=$(grep BLING_CLIENT_ID projetos-claude/della_sistemas/.env | cut -d= -f2)
export BLING_CLIENT_SECRET=$(grep BLING_CLIENT_SECRET projetos-claude/della_sistemas/.env | cut -d= -f2)
export BLING_AUTH_DIR=$(grep BLING_AUTH_DIR projetos-claude/della_sistemas/.env | cut -d= -f2)
projetos-claude/della_sistemas/.venv/bin/python jobs/vendas_atendidas.py 2026
# Nota: argumento posicional "2026", não "--ano 2026"
```

---

## API Bling v3 — endpoints confirmados e limitações

### Varejo
- **Leitura:** `GET /produtos/{id}` → campo `preco`
- **Atualização:** `PATCH /produtos/{id}` com `{"preco": valor}` ✅

### Custo (`fornecedor.precoCusto`)
- **Leitura:** `GET /produtos/fornecedores?idProduto={id}` → campo `precoCusto`
- **Atualização (produto existente com fornecedor vinculado):**
  1. `GET /produtos/fornecedores?idProduto={id}` → obtém `idProdutoFornecedor`
  2. `PUT /produtos/fornecedores/{idProdutoFornecedor}` com payload completo
  ⚠️ `PATCH /produtos/{id}` com `precoCusto` retorna 200 mas **ignora silenciosamente** — não usar.
- Função pronta: `services/precos.py::atualizar_custo_bling(bling_id, novo_custo)`
- **Criação (produto novo sem fornecedor vinculado):**
  - `POST /produtos/fornecedores` requer `fornecedor.id` com `idContato` válido (≠ 0)
  - Função: `services/business/process_approved_requests.py::_vincular_custo_bling(bling_id, custo, supplier_name, sku)`
  - Cache local de fornecedores: tabela `bling_supplier_contacts` no `inclusoes.db`
  - Função: `services/business/suppliers.py::get_or_create_bling_supplier(supplier_name)` — busca no cache, cria no Bling se não existir

### Fornecedores Bling cadastrados (`bling_supplier_contacts`)

| Nome | Bling Contact ID |
|------|-----------------|
| IVONEIDE | 18220786141 |
| DIVINA SANTA | 18220786345 |

> Para adicionar novo: `seed_supplier_contacts({"NOME": id})` ou o sistema cria automaticamente ao aprovar.

### Atacado (Lista de Preços)
- **Confirmado pelo suporte Bling:** listas de preços **não têm API**
- Estratégia: armazenar em `price_history` localmente, exportar CSV para importar no Bling

### Vendedores
- **Endpoint:** `GET /vendedores` → lista com `{id, contato: {nome}}`
- O nome do vendedor fica em `vendedor.contato.nome`, **não** em `vendedor.nome`
- Pedido detalhe retorna só `vendedor: {"id": X}` — precisa do lookup

### Rate Limiting
- `MIN_SECONDS_BETWEEN_REQUESTS = 0.45s`
- `_respect_rate_limit()` usa `threading.Lock` — thread-safe para chamadas paralelas
- Retry automático em 429/5xx com `Retry-After` header

### Criação de novo produto (aprovação de nova cor)
- `POST /produtos` → `PATCH /produtos/{id}` com varejo → `_vincular_custo_bling()` (busca/cria fornecedor Bling automaticamente)
- Implementado em `services/business/process_approved_requests.py`

---

## Deploy na VPS

### Serviços
- **Systemd:** `della-sistemas.service` — `sudo systemctl restart della-sistemas`
- **Logs:** `~/logs/della-sistemas/access.log` e `error.log`
- **Nginx:** `/etc/nginx/sites-available/della-sistemas` (SSL via certbot)
- **SSL:** Let's Encrypt — renovação automática pelo certbot

### ⚠️ Gunicorn `preload_app = True`

`gunicorn.conf.py` tem `preload_app = True`. O processo master pré-carrega o app Django na inicialização; workers são forkados do estado em memória do master.

- **`sudo systemctl restart della-sistemas`** é OBRIGATÓRIO após qualquer mudança Python (`.py`, settings, migrations)
- `kill -HUP <pid>` (graceful reload) **não funciona** — novos workers herdam o código antigo do master na memória
- O serviço tem `Restart=on-failure`, então um `kill` manual não reinicia automaticamente — use sempre `systemctl restart`

### Comandos úteis
```bash
# Reiniciar após mudanças Python/settings (OBRIGATÓRIO após qualquer .py alterado)
sudo systemctl restart della-sistemas

# Ver logs em tempo real
tail -f ~/logs/della-sistemas/error.log

# Static files (após mudar CSS/JS/ícones)
cd /var/www/della-sistemas/projetos-claude/della_sistemas
.venv/bin/python manage.py collectstatic --noinput

# Migrations (apenas para apps Django, nunca para dados de produtos)
.venv/bin/python manage.py migrate

# Checar configuração Django
.venv/bin/python manage.py check

# Dev local
source .venv/bin/activate
python manage.py runserver 8002
```

### DNS
- Gerenciado pelo **Cloudflare** (não UOL)
- Registro A: `sistemas` → `159.203.101.232`, **DNS only** (nuvem cinza)
- `www.dellainstore.com` usa proxy Cloudflare (nuvem laranja) — outros subdomínios usam DNS only

---

## PWA (instalável no celular)

- `static/manifest.json` — tema dourado, nome D'ELLA Sistemas
- Para instalar: `https://sistemas.dellainstore.com` no Chrome/Safari → "Adicionar à tela inicial"

---

## Módulos futuros (placeholders no menu)

- **Estoque** — análise, reposição, queima (virá de `app/estoque/`)
- **Financeiro** — DRE, fluxo de caixa (virá de `app/financeiro/`)

Para adicionar: criar `apps/estoque/`, adicionar em `INSTALLED_APPS`, incluir URL em `config/urls.py`.

---

## App Streamlit produtos (DESATIVADO — migrado para o Django)

Desativado em 2026-06-28. A UI foi migrada para este projeto Django e o sync de
catálogo agora roda via `manage.py sync_catalog` (cron diário). O banco `inclusoes.db`
foi movido para `della_sistemas/data/produtos/`. A pasta `app/produtos/` será removida
após o período de validação (mantida temporariamente como fallback).

---

## Git e push

```bash
cd /var/www/della-sistemas/projetos-claude
git add della_sistemas/
git commit -m "feat: ..."
TOKEN=$(gh auth token)
git remote set-url origin "https://dellainstore:${TOKEN}@github.com/dellainstore/projetos-claude.git"
git push origin main
```
