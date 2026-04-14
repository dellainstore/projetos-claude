# Della Instore — Site E-commerce Premium
**CLAUDE.md — Contexto completo para continuação do desenvolvimento**

---

## Visão Geral do Projeto

Loja virtual de moda feminina premium chamada **Della Instore**.
- **Stack:** Django 5.1 + PostgreSQL + Gunicorn + Nginx
- **Frontend:** HTML/CSS/JS com Tailwind CSS (CDN) + CSS customizado
- **VPS:** Ubuntu, 1 vCore, 1.9GB RAM, IP `159.203.101.232`
- **Domínio definitivo:** `www.dellainstore.com.br` (ainda aponta para site antigo)
- **Domínio de testes:** `novo.dellainstore.com.br` (DNS já criado na UOL Host)
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
│   │   ├── base.py          ← settings compartilhado (com segurança)
│   │   ├── production.py    ← HTTPS, HSTS, cookies seguros
│   │   └── development.py   ← debug, e-mail no console
│   ├── urls.py              ← roteador raiz
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── produtos/            ← catálogo, categorias, variações, avaliações
│   ├── pedidos/             ← carrinho (sessão), checkout, pedidos
│   ├── pagamentos/          ← PagSeguro, Stone, Pix
│   ├── bling/               ← integração ERP Bling
│   ├── usuarios/            ← Cliente (auth customizado), Endereço
│   └── core_utils/
│       └── sanitize.py      ← sanitizadores de input (XSS, CPF, CEP, imagem)
├── templates/
│   ├── base.html            ← template raiz (navbar, footer, drawer, whatsapp)
│   ├── home/
│   │   └── index.html       ← homepage completa (8 seções)
│   ├── produtos/            ← stubs criados (loja, detalhe, busca, wishlist)
│   ├── pedidos/             ← stubs criados
│   ├── checkout/            ← stubs criados
│   └── usuarios/            ← stubs criados
├── static/
│   ├── css/della.css        ← todo CSS customizado da marca
│   └── js/della.js          ← JS principal (navbar, carrinho, AJAX, animações)
├── media/                   ← uploads de produtos
├── logs/                    ← logs do gunicorn e django
├── scripts/
│   ├── setup_postgres.sh        ← instala e cria banco della_site
│   ├── setup_django.sh          ← migrate + collectstatic + createsuperuser
│   ├── instalar_servico.sh      ← instala Gunicorn systemd + Nginx + Certbot
│   ├── check_security.sh        ← verifica .env, DEBUG, SECRET_KEY antes do deploy
│   ├── gunicorn_della_site.service  ← arquivo do serviço systemd
│   └── nginx_della_site.conf    ← config Nginx (testes + bloco produção comentado)
├── .env                     ← variáveis reais (NÃO subir no git)
├── .env.example             ← template sem valores reais
├── .gitignore
├── manage.py
└── requirements.txt
```

---

## Ambiente Virtual

```bash
cd /var/www/della-sistemas/projetos-claude/site_della
source venv/bin/activate
```

---

## Banco de Dados

- **Banco:** `della_site`
- **Usuário:** `della_user`
- **Senha:** no `.env` → `DB_PASSWORD`
- **Status:** PostgreSQL instalado, banco criado, migrations aplicadas ✓

### Rodar migrations após alterações em models:
```bash
source venv/bin/activate
python manage.py makemigrations
python manage.py migrate
```

---

## Servidor de Desenvolvimento

```bash
source venv/bin/activate
python manage.py runserver 0.0.0.0:8000 --settings=core.settings.base
```

Acesso: `http://159.203.101.232:8000`

> **IP deve estar no ALLOWED_HOSTS do .env** — já configurado: `159.203.101.232` incluído.

> **Atenção:** porta 8000 precisa estar aberta no UFW para acesso externo:
> ```bash
> sudo ufw allow 8000/tcp   # abre para teste
> sudo ufw delete allow 8000/tcp  # fecha depois
> ```

---

## Deploy em Produção (quando pronto)

```bash
# 1. Instala Gunicorn como serviço + Nginx + SSL (subdomínio novo.dellainstore.com.br)
sudo bash scripts/instalar_servico.sh

# 2. Verificação de segurança antes de qualquer push/deploy
bash scripts/check_security.sh
```

### Quando trocar para www.dellainstore.com.br:
1. Editar `/etc/nginx/sites-available/della_site` — comentar bloco "testes", descomentar bloco "produção"
2. `sudo certbot --nginx -d www.dellainstore.com.br -d dellainstore.com.br`
3. Atualizar `ALLOWED_HOSTS` no `.env`
4. `sudo systemctl reload nginx`

---

## Comandos Úteis

```bash
# Verificar status do serviço Gunicorn
sudo systemctl status gunicorn_della_site

# Reiniciar Gunicorn após alterações no código
sudo systemctl restart gunicorn_della_site

# Logs do Gunicorn em tempo real
sudo journalctl -u gunicorn_della_site -f

# Testar config Nginx e recarregar
sudo nginx -t && sudo systemctl reload nginx

# Coletar arquivos estáticos
python manage.py collectstatic --noinput
```

---

## Models Criados

### `apps/usuarios/`
| Model | Campos principais |
|---|---|
| `Cliente` | email (login), nome, sobrenome, cpf, telefone, genero — auth customizado sem username |
| `Endereco` | cep, logradouro, numero, complemento, bairro, cidade, estado, principal |

### `apps/produtos/`
| Model | Campos principais |
|---|---|
| `Categoria` | nome, slug, imagem, ordem, ativa |
| `Produto` | categoria, nome, slug, descricao, composicao, preco, preco_promocional, ativo, destaque, bling_id, sku |
| `ProdutoImagem` | produto, imagem (validada por magic bytes), alt, principal, ordem |
| `Variacao` | produto, tipo (tamanho/cor), nome, codigo_hex, estoque, ativa |
| `Avaliacao` | produto, cliente, nota, titulo, comentario, **aprovada** (moderação manual) |

### `apps/pedidos/`
| Model | Campos principais |
|---|---|
| `Pedido` | numero (DI-2024-XXXX), cliente, dados do comprador copiados, endereço copiado, subtotal, frete, total, status, gateway, codigo_rastreio, bling_pedido_id |
| `ItemPedido` | pedido, produto, variacao, nome/preco copiados (imutável), quantidade |
| `HistoricoPedido` | log de mudanças de status |
| `Carrinho` | classe de sessão em `apps/pedidos/carrinho.py` |

### `apps/pagamentos/`
| Model | Campos |
|---|---|
| `Pagamento` | pedido, gateway, gateway_id, status, valor, dados_retorno (JSON) |

### `apps/bling/`
| Model | Campos |
|---|---|
| `BlingToken` | access_token, refresh_token, expira_em |
| `BlingLog` | tipo, pedido, sucesso, payload_enviado, resposta, erro |

---

## Segurança Implementada

| Camada | O que faz |
|---|---|
| `scripts/check_security.sh` | Verifica .env no git, SECRET_KEY hardcoded, DEBUG em prod |
| `apps/core_utils/sanitize.py` | `sanitize_text`, `sanitize_name`, `sanitize_address`, `sanitize_phone`, `sanitize_cep`, `validate_cpf`, `validate_cnpj`, `validate_image_upload` (magic bytes) |
| `django-axes` | Bloqueia IP após 5 tentativas de login falhas por 1 hora |
| `django-csp` | Content-Security-Policy headers |
| Django CSRF | Ativo em todos os forms |
| Nginx | Bloqueia .env, .git, .sql; bloqueia scripts em /media/; headers de segurança |
| `production.py` | HTTPS obrigatório, HSTS, cookies seguros, X-Frame-Options DENY |
| ORM Django | Zero SQL raw — proteção contra SQL injection |
| `Avaliacao.aprovada` | Avaliações de clientes passam por moderação antes de aparecer |

---

## Homepage — Seções Implementadas

Template: `templates/home/index.html`
CSS: `static/css/della.css`
JS: `static/js/della.js`

| Seção | Status |
|---|---|
| Hero vídeo fullscreen com mute/unmute | ✓ |
| Categorias (grid 4 colunas, hover zoom) | ✓ |
| Produtos destaque (hover troca foto, add carrinho AJAX) | ✓ |
| Shop the Look (foto com pontos interativos) | ✓ |
| Manifesto da marca | ✓ |
| Depoimentos (3 colunas com estrelas) | ✓ |
| Feed Instagram (placeholders + estrutura para API) | ✓ |
| Newsletter (AJAX + sanitização) | ✓ |
| WhatsApp flutuante (2 contatos, abre/fecha) | ✓ |
| Drawer carrinho (slide lateral) | ✓ |
| Footer completo (4 colunas + social + selos) | ✓ |
| Navbar transparente→sólida ao rolar | ✓ |
| Animações fade-in ao scroll | ✓ |
| Mobile responsive | ✓ |

### Imagens necessárias (colocar em `static/images/brand/`):
- `hero.mp4` — vídeo do hero (ou `.webm`)
- `hero-poster.jpg` — frame inicial do vídeo (fallback)
- `categoria-placeholder.jpg` — foto genérica de categoria
- `produto-placeholder.jpg` — foto genérica de produto
- `instagram-placeholder.jpg` — foto genérica do grid Instagram
- `look-semana.jpg` — foto do Shop the Look
- `og-default.jpg` — imagem Open Graph (1200×630)
- `favicon.ico` — favicon da marca

---

## URLs Registradas

```
/                          → homepage
/loja/                     → listagem de produtos
/loja/<categoria>/         → produtos por categoria
/produto/<slug>/           → detalhe do produto
/busca/                    → busca
/wishlist/                 → lista de desejos

/conta/entrar/                        → login
/conta/sair/                          → logout
/conta/cadastro/                      → cadastro de cliente
/conta/minha-conta/                   → dashboard da conta
/conta/minha-conta/editar/            → editar perfil
/conta/minha-conta/enderecos/         → lista de endereços
/conta/minha-conta/enderecos/novo/    → novo endereço
/conta/minha-conta/pedidos/           → histórico de pedidos
/conta/minha-conta/pedidos/<n>/       → detalhe do pedido
/conta/recuperar-senha/               → recuperação de senha
/conta/recuperar-senha/confirmar/.../  → nova senha com token

/carrinho/                 → carrinho
/carrinho/adicionar/<id>/  → add produto (POST/AJAX)
/carrinho/checkout/        → fluxo de checkout
/carrinho/confirmacao/<n>/ → pedido confirmado

/pagamento/pagseguro/...   → retorno/notificação PagSeguro
/pagamento/stone/webhook/  → webhook Stone
/pagamento/pix/...         → geração QR Code Pix

/bling/webhook/            → notificações ERP
/painel/                   → Django Admin
```

---

## Etapas Concluídas ✓

- [x] **Etapa 1** — Estrutura de pastas do projeto
- [x] **Etapa 2** — Ambiente virtual Python + dependências (`requirements.txt`)
- [x] **Etapa 3** — Settings com segurança multicamada (base/production/development) + `sanitize.py`
- [x] **Etapa 4** — Apps Django criados + URLs completas de todos os apps
- [x] **Etapa 5** — PostgreSQL instalado, banco `della_site` criado, migrations aplicadas
- [x] **Etapa 6** — Models principais (Cliente, Produto, Pedido, Pagamento, Bling)
- [x] **Etapa 7** — Nginx config + Gunicorn systemd (prontos para instalar)
- [x] **Etapa 8** — Homepage completa (hero, categorias, produtos, look, manifesto, depoimentos, instagram, newsletter, whatsapp, footer)
- [x] **Etapa 9** — Loja (grid + filtros sidebar + paginação), página de produto (galeria, variações, acordeões, avaliações, relacionados), carrinho funcional (sessão, add/remover/atualizar via AJAX, drawer dinâmico)
- [x] **Etapa 10** — Checkout completo (stepper 3 etapas, ViaCEP, Melhor Envio com fallback, Pix QR Code EMV, Cartão de Crédito), criação real de Pedido+ItemPedido, página de confirmação com polling de status Pix
- [x] **Etapa 11** — Área do cliente: login, cadastro, minha conta, editar perfil, endereços CRUD, histórico de pedidos, detalhe de pedido, wishlist, recuperação de senha com token por e-mail
- [x] **Etapa 12** — Django Admin customizado: produtos com fotos inline, pedidos com status e ações, relatório geral
- [x] **Etapa 13** — Integração Bling: OAuth2 completo, cliente API v3, envio automático de pedido ao confirmar pagamento, emissão de NF-e, webhook para rastreio e status

### Detalhes da Etapa 11
| Arquivo | O que foi feito |
|---|---|
| `apps/usuarios/forms.py` | 6 formulários: LoginForm (axes-aware), CadastroForm (ModelForm com senhas), EditarPerfilForm, EnderecoForm (CEP cleaned), RecuperarSenhaForm, NovaSenhaForm (com validators Django) |
| `apps/usuarios/views.py` | Todas as views reais: login (next param seguro), cadastro (auto-login), minha_conta, editar_perfil, endereços CRUD, definir_principal (AJAX), meus_pedidos, detalhe_pedido, recuperar_senha (token+e-mail), confirmar_senha |
| `apps/usuarios/urls.py` | 14 rotas: /conta/entrar/, /conta/cadastro/, /conta/minha-conta/, /conta/minha-conta/editar/, /conta/minha-conta/enderecos/*, /conta/minha-conta/pedidos/*, /conta/recuperar-senha/* |
| `templates/usuarios/*.html` | 9 templates: login, cadastro, minha_conta (dashboard), editar_perfil, enderecos, endereco_form (com CEP autocomplete), meus_pedidos, detalhe_pedido, recuperar_senha, confirmar_senha |
| `templates/produtos/wishlist.html` | Wishlist com sidebar de conta, grid de produtos, link para toggle |
| `static/css/della.css` | +400 linhas: layout sidebar+conteúdo, sidebar nav, cards de conta, badges de status de pedido, grid de endereços, botões de ação, estados vazios, responsivo |

### Detalhes da Etapa 10
| Arquivo | O que foi feito |
|---|---|
| `apps/pedidos/forms.py` | `CheckoutForm` completo: dados pessoais, endereço, frete, pagamento; máscaras e validação de CPF/CEP |
| `apps/pedidos/views.py` | `checkout()`: GET pré-preenche dados do usuário logado, POST cria Pedido+ItemPedido+limpa carrinho; `calcular_frete()`; `consultar_cep()` via ViaCEP; `confirmacao_pedido()` com geração de QR Code Pix |
| `apps/pagamentos/pix.py` | Gerador de payload Pix EMV padrão BACEN (CRC-16/CCITT-FALSE) + QR Code PNG base64 via `qrcode` |
| `apps/pagamentos/services/melhorenvio.py` | Integração real Melhor Envio API v2 com fallback PAC/SEDEX quando token não configurado |
| `apps/pagamentos/views.py` | `pix_gerar()` e `pix_status()` reais; hooks PagSeguro/Stone estruturados |
| `templates/checkout/index.html` | Stepper visual 3 etapas (dados+endereço → frete → pagamento); ViaCEP autocomplete; cálculo de frete AJAX; tabs Pix/Cartão; máscaras JS |
| `templates/checkout/confirmacao.html` | QR Code Pix exibido, botão copiar código, polling automático de status (30s), detalhes do pedido |
| `della.css` | +500 linhas: stepper, campos, frete, tabs pagamento, Pix, confirmação, responsivo |
| `settings/base.py` + `.env.example` | `PIX_CHAVE` adicionado |

### Detalhes da Etapa 9
| Arquivo | O que foi feito |
|---|---|
| `apps/produtos/views.py` | `loja`: filtros por categoria/preço/novidade/promoção, ordenação, paginação. `detalhe_produto`: galeria, variações, avaliações, relacionados |
| `apps/pedidos/views.py` | `carrinho`, `adicionar_ao_carrinho`, `remover_do_carrinho`, `atualizar_carrinho` — todos retornam JSON com itens atualizados para drawer |
| `templates/produtos/loja.html` | Grid 4 colunas, sidebar com filtros, paginação, cards com hover + wishlist |
| `templates/produtos/detalhe.html` | Galeria com thumbs, seleção de cor/tamanho, qty selector, acordeões, avaliações, produtos relacionados |
| `templates/pedidos/carrinho.html` | Página completa do carrinho: itens, atualizar qty, remover, resumo lateral |
| `static/css/della.css` | Estilos para loja, card produto, detalhe, drawer items, carrinho, botões primário/secundário |
| `static/js/della.js` | `atualizarDrawerConteudo()`, `drawerRemover()`, `drawerAlterarQty()` — drawer AJAX global |

---

## Etapas Pendentes
- [ ] **Etapa 14** — E-mails transacionais: confirmação de pedido, envio com rastreio, recuperação de senha
- [ ] **Etapa 15** — Integração Instagram Feed (API Graph)
- [ ] **Etapa 16** — Deploy final: instalar Gunicorn+Nginx, SSL, variáveis de produção, trocar domínio

---

## Dependências Instaladas (`requirements.txt`)

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
```

---

## Variáveis de Ambiente (`.env`)

Arquivo em `/var/www/della-sistemas/projetos-claude/site_della/.env`
Template em `.env.example`

Variáveis principais:
- `SECRET_KEY`, `DEBUG`, `ALLOWED_HOSTS`
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`
- `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`
- `PAGSEGURO_EMAIL`, `PAGSEGURO_TOKEN`, `PAGSEGURO_SANDBOX`
- `STONE_CLIENT_ID`, `STONE_CLIENT_SECRET`, `STONE_SANDBOX`
- `BLING_CLIENT_ID`, `BLING_CLIENT_SECRET`
- `WHATSAPP_NUMBER_1`, `WHATSAPP_NUMBER_2`
- `INSTAGRAM_ACCESS_TOKEN`
- `MELHOR_ENVIO_TOKEN`, `MELHOR_ENVIO_SANDBOX`

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
| Transição padrão | `all 0.4s cubic-bezier(0.25, 0.46, 0.45, 0.94)` |

---

## Como Continuar numa Nova Conversa

1. Abra uma nova conversa no Claude Code
2. Cole exatamente a frase abaixo:

> **"Continuando o desenvolvimento do site Della Instore. Leia o arquivo `/var/www/della-sistemas/projetos-claude/site_della/CLAUDE.md` e continue pela Etapa 14 — E-mails transacionais."**

3. O Claude vai ler este arquivo e continuar de onde parou

---

### Detalhes da Etapa 12
| Arquivo | O que foi feito |
|---|---|
| `apps/produtos/admin.py` | `CategoriaAdmin` (thumb, total produtos), `ProdutoAdmin` (thumb inline, badge promoção, estoque colorido, média avaliações, ações ativar/desativar/destaque), `ProdutoImagemInline` (preview 60px), `VariacaoInline` (tabular), `AvaliacaoInline` (stackado, só leitura), `AvaliacaoAdmin` (aprovar/reprovar em massa) |
| `apps/pedidos/admin.py` | `PedidoAdmin` (badge status colorido, inlines ItemPedido+HistoricoPedido readonly, ações de mudança de status com log automático em `HistoricoPedido`) |
| `apps/usuarios/admin.py` | `ClienteAdmin` (herda `UserAdmin`, login por email, `EnderecoInline`), `EnderecoAdmin`, `WishlistAdmin` |
| `apps/pagamentos/admin.py` | `PagamentoAdmin` (badge status, valor formatado em R$, `dados_retorno` colapsável) |
| `apps/bling/admin.py` | `BlingTokenAdmin` (badge válido/expirado, readonly), `BlingLogAdmin` (badge OK/Erro, resumo do erro) |
| `apps/core_utils/admin_views.py` | View `relatorio()` com: faturamento 30 dias, pedidos por status, top 10 produtos, variações com estoque crítico |
| `templates/admin/relatorio.html` | Template do relatório com cards de KPIs, tabelas de status e top produtos, estoque crítico |
| `templates/admin/index.html` | Override do index admin para adicionar botão "Relatório Geral" no topo |
| `core/urls.py` | Rota `/painel/relatorio/` registrada via `staff_member_required` |

### Detalhes da Etapa 13
| Arquivo | O que foi feito |
|---|---|
| `apps/bling/oauth.py` | `get_authorize_url()`, `exchange_code()`, `refresh_token()`, `get_valid_access_token()` — fluxo OAuth2 completo com auto-refresh |
| `apps/bling/api.py` | `BlingAPI` + `BlingAPIError` — cliente HTTP para API v3: `criar_pedido_venda`, `consultar_pedido_venda`, `atualizar_situacao_pedido`, `emitir_nfe_do_pedido`, `consultar_nfe`, `enviar_nfe_sefaz` |
| `apps/bling/services.py` | `enviar_pedido_bling(pedido)` e `emitir_nfe_bling(pedido)` — funções de alto nível com log completo em `BlingLog`; `_montar_payload_pedido()` monta JSON completo para a API v3 |
| `apps/bling/views.py` | `oauth_autorizar` (staff only → redireciona para Bling), `oauth_callback` (troca code por token, salva), `webhook` (recebe notificações: atualiza rastreio, status, NF-e) |
| `apps/bling/urls.py` | Adicionada rota `/bling/autorizar/` |
| `apps/bling/admin.py` | `BlingTokenAdmin` com botão "Autorizar Bling" no changelist via template customizado |
| `apps/pedidos/admin.py` | Ação "→ Pagamento confirmado" agora dispara `enviar_pedido_bling` automaticamente; novas ações "Bling: enviar pedidos" e "Bling: emitir NF-e"; badge Bling/NF-e na listagem |
| `templates/admin/bling_status.html` | Página de resultado do OAuth (sucesso/erro) |
| `templates/admin/bling_token_changelist.html` | Override do changelist com botão "Autorizar Bling" |
| `core/settings/base.py` | Adicionado `BLING_REDIRECT_URI` |
| `.env.example` | Atualizado com `BLING_REDIRECT_URI` e instruções de configuração |

### Como configurar o Bling na prática
1. Criar um aplicativo em [developer.bling.com.br](https://developer.bling.com.br/aplicativos)
2. Copiar `Client ID` e `Client Secret` para o `.env`
3. Registrar no app Bling a URL de callback: `https://www.dellainstore.com.br/bling/callback/`
4. Configurar `BLING_REDIRECT_URI` no `.env`
5. Acessar `/bling/autorizar/` no admin para fazer o primeiro login
6. Configurar o webhook no painel Bling → Integrações → Webhooks → URL: `https://www.dellainstore.com.br/bling/webhook/`
7. Para NF-e: configurar CFOP, NCM e tributação dos produtos no painel do Bling antes de usar a ação de emissão

*Última atualização: Etapa 13 concluída — Integração Bling completa (OAuth2, API v3, envio de pedidos, NF-e, webhook).*
