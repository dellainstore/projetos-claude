# CRM-Conversations — Plano do Projeto

## Status: BLOQUEADO — Aguardando configuração DNS + HTTPS

**Único bloqueio atual**: configurar o subdomínio `crm.dellainstore.com` via painel da UOL
apontando para o IP do VPS, depois rodar Certbot para SSL. Sem HTTPS ativo, a Meta não aceita
o webhook e não é possível testar as mensagens do WhatsApp.

### O que JÁ está feito
- [x] Domínio `dellainstore.com` existe (gerenciado na UOL)
- [x] Meta Business Manager verificado (conta Instagram verificada)
- [x] App criado no `developers.facebook.com` (WhatsApp + Instagram já adicionados como produtos)
- [x] Conta Instagram Business configurada na Meta

### O que falta (em ordem)
- [ ] **Painel UOL**: criar registro DNS tipo A → `crm` → IP do VPS
- [ ] **VPS**: `sudo certbot --nginx -d crm.dellainstore.com` (após DNS propagar ~5-30min)
- [ ] **VPS**: configurar nginx e subir o app CRM na porta 8520
- [ ] **Meta Developer**: registrar webhook WhatsApp com URL `https://crm.dellainstore.com/webhooks/whatsapp`
- [ ] **Meta Developer**: configurar número WhatsApp Business (número real ou sandbox de teste)
- [ ] **Meta Developer**: registrar webhook Instagram com URL `https://crm.dellainstore.com/webhooks/instagram`

---

## O que é
CRM interno para unificação de conversas do **WhatsApp Business** e **Instagram Direct**.
Ferramenta para ~3-5 funcionários responderem clientes sem duplicar atendimentos.

**Problema que resolve**: Múltiplos funcionários respondem o mesmo cliente sem saber
quem está atendendo e em que estágio está a conversa.

**Funcionalidades do MVP**:
- Inbox unificado (WhatsApp + Instagram em uma só tela)
- Atribuição de atendente por conversa
- Status da conversa (Aberta / Pendente / Resolvida)
- Histórico completo do cliente

---

## Stack Definida

| Camada | Tecnologia | Motivo |
|---|---|---|
| Backend | FastAPI (Python 3.12) | Async nativo para webhooks + API |
| Banco | SQLite + SQLAlchemy | Zero configuração, suficiente para o volume |
| Frontend | Jinja2 + Tailwind CSS (CDN) + HTMX | Tudo em Python, sem build JS |
| Real-time | Server-Sent Events (SSE) | Mais simples que WebSocket, suportado pelo HTMX |
| WhatsApp | httpx direto para Meta Cloud API | Simples de debugar |
| Instagram | httpx direto para Meta Graph API | Idem |
| Auth | Cookies assinados (itsdangerous) | Simples, sem JWT, sem refresh |
| Servidor | uvicorn porta 8520 + nginx proxy + SSL | Mesmo padrão dos outros projetos |

> **Por que não Streamlit?** Streamlit não é adequado para apps de mensagem em tempo real —
> cada usuário cria uma sessão isolada, não há WebSocket nativo, e auth multi-usuário é
> complicado. FastAPI + HTMX é a escolha certa aqui.

---

## Estrutura de Pastas (a criar)

```
CRM-Conversations/
├── CLAUDE.md                         # Este arquivo
├── requirements.txt
├── .env.example
├── main.py                           # Entry point — cria app FastAPI, startup do banco
├── crm/
│   ├── config.py                     # pydantic-settings lendo .env
│   ├── database.py                   # Engine SQLAlchemy + WAL mode + get_db()
│   ├── models.py                     # Agent, Contact, Conversation, Message
│   ├── auth.py                       # Assina/verifica cookie de sessão
│   ├── dependencies.py               # get_db, get_current_agent (FastAPI deps)
│   ├── routers/
│   │   ├── auth_router.py            # GET/POST /login, GET /logout
│   │   ├── inbox_router.py           # GET /inbox, /inbox/{id} (HTML)
│   │   ├── conversations_router.py   # API: assign, status, reply
│   │   ├── webhooks_router.py        # GET+POST /webhooks/whatsapp e /instagram
│   │   └── sse_router.py             # GET /sse/events (stream SSE)
│   ├── services/
│   │   ├── whatsapp.py               # parse webhook + send_message()
│   │   ├── instagram.py              # parse webhook + send_message()
│   │   ├── conversation_service.py   # upsert_contact, get_or_create_conversation, save_message
│   │   └── notification_service.py   # broker SSE in-memory (asyncio.Queue por agente)
│   └── templates/
│       ├── base.html                 # Layout: sidebar + Tailwind + HTMX + SSE
│       ├── login.html
│       ├── inbox.html                # Lista de conversas com filtros
│       ├── conversation.html         # Histórico + caixa de resposta
│       └── partials/
│           ├── conversation_item.html    # Linha da inbox (HTMX swap)
│           ├── message_bubble.html       # Bolha de mensagem (SSE OOB swap)
│           └── assign_modal.html         # Modal de atribuição de agente
├── data/
│   └── crm.db                        # gitignored — banco com mensagens reais
├── crm-conversations.service         # systemd unit (mesmo padrão do Bot-Telegram)
└── nginx-crm.conf.example            # Config nginx para copiar para sites-available
```

---

## Modelos de Banco (`crm/models.py`)

### `agents` — funcionários que usam o CRM
```
id, name, username, password_hash (bcrypt), is_active, created_at
```

### `contacts` — clientes que entraram em contato
```
id, whatsapp_phone (E.164 ex: 5511999990000, unique),
instagram_user_id (IGSID da Meta, unique), instagram_username,
name, notes, created_at
```

### `conversations` — thread ativa por cliente por canal
```
id, contact_id FK, channel ENUM(whatsapp|instagram),
status ENUM(open|pending|resolved),
assigned_agent_id FK nullable, last_message_at, created_at, updated_at
```
**Regra**: unique constraint em `(contact_id, channel)` — uma conversa ativa por canal.
Quando resolvida, uma nova é criada na próxima mensagem.

### `messages` — cada mensagem individual
```
id, conversation_id FK, external_id (wamid ou mid — único, para deduplicação),
direction ENUM(inbound|outbound),
message_type ENUM(text|image|audio|video|document),
content, media_url nullable,
sent_by_agent_id FK nullable (null = mensagem do cliente),
status ENUM(sent|delivered|read|failed),
timestamp, created_at
```

**Detalhe crítico**: habilitar `PRAGMA journal_mode=WAL` no SQLite para suportar
leituras e escritas simultâneas (webhook escrevendo enquanto agentes acessam a UI).

---

## Fluxos Críticos

### Mensagem inbound (cliente → Meta → banco → tela)
```
1. Cliente manda mensagem no WhatsApp/Instagram
2. Meta POST → /webhooks/whatsapp (ou /instagram)
3. Validar assinatura X-Hub-Signature-256 com HMAC-SHA256 usando APP_SECRET
4. whatsapp.py parse payload → extrai phone/user_id, texto, id_externo, timestamp
5. conversation_service.upsert_contact() → cria ou retorna contato existente
6. conversation_service.get_or_create_conversation(contact, canal) → reutiliza aberta
7. conversation_service.save_message() → insere na tabela messages
8. notification_service.broadcast() → SSE para todos os agentes conectados
9. Return HTTP 200 — OBRIGATÓRIO (Meta reenvia se não receber 200 em 20s)
```

### Resposta outbound (agente digita → Meta API → cliente)
```
1. Agente digita no browser → HTMX POST /api/conversations/{id}/reply
2. Router identifica canal (WA ou IG) da conversa
3. whatsapp.send_message() ou instagram.send_message() via httpx
4. Salva mensagem outbound no banco (direction=outbound)
5. Retorna partials/message_bubble.html → HTMX faz swap na tela
```

---

## Configuração da Meta API — Status Detalhado

> **Importante**: WhatsApp e Instagram usam o **MESMO app** no Meta for Developers.
> A verificação do Meta Business Manager é compartilhada entre os dois produtos.
> Como o Instagram já está verificado, o WhatsApp herda essa verificação — não precisa
> verificar de novo.

### A. Meta Business Manager — CONCLUÍDO
- [x] Conta criada e empresa verificada
- [x] Conta Instagram Business vinculada

### B. App no Meta for Developers — CONCLUÍDO
- [x] App criado em `developers.facebook.com`
- [x] Produto WhatsApp adicionado ao app
- [x] Produto Messenger/Instagram adicionado ao app

### C. Configurar WhatsApp — PENDENTE
- [ ] No painel do app → WhatsApp → Primeiros Passos
- [ ] Copiar **Phone Number ID** do número de sandbox (gratuito para testes)
- [ ] Business Settings → Usuários do Sistema → Criar Usuário do Sistema (Admin)
- [ ] Gerar Token Permanente com permissões: `whatsapp_business_messaging` + `whatsapp_business_management`
- [ ] Copiar **App Secret**: Configurações → Básico → App Secret (≠ Access Token!)
- [ ] Salvar tudo no `.env`: `WHATSAPP_ACCESS_TOKEN`, `WHATSAPP_PHONE_NUMBER_ID`, `WHATSAPP_APP_SECRET`

### D. Configurar Instagram — PENDENTE (parcialmente feito)
- [x] Conta Instagram Business existe
- [ ] No app Meta → Messenger → Configurações do Instagram → confirmar conta IG vinculada
- [ ] Gerar Page Access Token com permissões: `instagram_manage_messages`, `pages_messaging`
- [ ] Copiar **Page ID** da Facebook Page vinculada ao Instagram
- [ ] Salvar no `.env`: `INSTAGRAM_ACCESS_TOKEN`, `INSTAGRAM_PAGE_ID`, `INSTAGRAM_APP_SECRET`

### E. Configurar HTTPS no servidor — PRÓXIMO PASSO IMEDIATO
- [ ] **Painel UOL**: adicionar registro DNS tipo A → hostname `crm` → IP do VPS
  - Aguardar propagação: normalmente 5-30 minutos, pode levar até 24h
  - Testar: `ping crm.dellainstore.com` deve responder com IP do VPS
- [ ] **No VPS**: `sudo certbot --nginx -d crm.dellainstore.com`
- [ ] **No VPS**: criar config nginx (usar `nginx-crm.conf.example` do projeto)
- [ ] Subir o app na porta 8520 e testar acesso pelo browser

### F. Registrar Webhooks na Meta — após HTTPS estar ativo
- [ ] WhatsApp: Configuração → Webhooks → URL: `https://crm.dellainstore.com/webhooks/whatsapp`
  - Verify Token: inventar uma string secreta → salvar como `WHATSAPP_VERIFY_TOKEN` no `.env`
  - Subscrever no campo: `messages`
  - Clicar "Testar" → deve retornar "Succeeded"
- [ ] Instagram: mesmo processo → URL: `https://crm.dellainstore.com/webhooks/instagram`
  - Verify Token diferente → salvar como `INSTAGRAM_VERIFY_TOKEN` no `.env`
  - Subscrever nos campos: `messages`, `messaging_seen`

### G. App Review para produção — após testes no sandbox
- [ ] Submeter revisão solicitando: `whatsapp_business_messaging`, `instagram_manage_messages`
- [ ] Fornecer screenshots e descrição do uso (CRM interno)
- [ ] Aguardar aprovação para usar número WhatsApp real (não só sandbox)
- Obs: sandbox de teste do WhatsApp funciona sem App Review — dá para desenvolver tudo antes

---

## Variáveis de Ambiente (`.env.example`)

```bash
# Segurança
SECRET_KEY=gere_um_valor_aleatorio_longo_aqui
DATABASE_URL=sqlite:///data/crm.db

# WhatsApp Business Cloud API
WHATSAPP_ACCESS_TOKEN=          # System User permanent token
WHATSAPP_PHONE_NUMBER_ID=       # ID do número (não o número em si)
WHATSAPP_APP_SECRET=            # App Secret (Configurações > Básico no painel Meta)
WHATSAPP_VERIFY_TOKEN=          # Qualquer string secreta que você inventar

# Instagram Graph API
INSTAGRAM_ACCESS_TOKEN=         # Page Access Token com instagram_manage_messages
INSTAGRAM_PAGE_ID=              # ID da Facebook Page vinculada à conta IG
INSTAGRAM_APP_SECRET=           # Mesmo APP_SECRET acima (mesmo app Meta)
INSTAGRAM_VERIFY_TOKEN=         # Qualquer string secreta que você inventar

# Agente admin inicial (seed no primeiro start)
ADMIN_USERNAME=admin
ADMIN_PASSWORD=
```

---

## Fases de Desenvolvimento (na ordem certa)

```
Fase 1 — Skeleton + Auth       (Dia 1)  App roda, login funciona, inbox vazio
Fase 2 — Webhook + Banco       (Dia 2)  Recebe mensagem WA e salva no SQLite
Fase 3 — UI da Inbox           (Dia 3)  Ver conversas no browser, ler histórico
Fase 4 — Resposta              (Dia 4)  Agente responde pelo browser, cliente recebe
Fase 5 — Atribuição + Status   (Dia 5)  Agentes se atribuem, marcam como resolvido
Fase 6 — Real-time SSE         (Dia 6)  Novas mensagens aparecem sem recarregar
Fase 7 — Instagram             (Dias 7-8) DMs do IG também na inbox unificada
Fase 8 — Polimento             (Dias 9-10) Busca, filtros, notas, contagem
```

---

## Convenções de Código

- Python 3.12, ruff `line-length = 100` (mesmo padrão dos outros projetos)
- Toda lógica de negócio fica em `crm/services/` — routers só orquestram
- Routers retornam `TemplateResponse` para páginas completas, `HTMLResponse` para partials HTMX
- Banco inicializado via `Base.metadata.create_all(engine)` no startup do FastAPI
- **Nunca commitar `.env`** — usar `.env.example` sem valores reais
- **Nunca commitar `data/crm.db`** — contém mensagens reais de clientes

---

## Referências Rápidas Meta API

```
# WhatsApp — enviar mensagem
POST https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages
Headers: Authorization: Bearer {WHATSAPP_ACCESS_TOKEN}

# Instagram — enviar mensagem
POST https://graph.facebook.com/v19.0/{INSTAGRAM_PAGE_ID}/messages
Headers: Authorization: Bearer {INSTAGRAM_ACCESS_TOKEN}

# Verificação de webhook (GET)
Retornar hub.challenge como plain text se hub.verify_token bater com o .env

# Validação de assinatura (POST inbound)
Header: X-Hub-Signature-256: sha256=<hex>
Calcular: HMAC-SHA256(APP_SECRET, raw_body) e comparar
```

---

## Como Rodar (quando pronto para implementar)

```bash
# Desenvolvimento
cd /var/www/della-sistemas/projetos-claude/CRM-Conversations
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # preencher os valores
uvicorn main:app --reload --port 8520

# Produção
sudo systemctl enable crm-conversations
sudo systemctl start crm-conversations
sudo journalctl -u crm-conversations -f   # logs em tempo real
```

---

## Dependências (`requirements.txt`)

```
fastapi>=0.111
uvicorn[standard]>=0.29
sqlalchemy>=2.0
pydantic-settings>=2.0
python-dotenv>=1.0
itsdangerous>=2.1
bcrypt>=4.0
jinja2>=3.1
python-multipart>=0.0.9
httpx>=0.27
sse-starlette>=1.8
```

---

## O que NÃO fazer (aprendidos no planejamento)

- Nao usar Streamlit — não suporta real-time multi-usuário para mensagens
- Nao usar webhook sem validar assinatura HMAC — qualquer um poderia injetar mensagens falsas
- Nao desabilitar WAL mode no SQLite — trava com múltiplas conexões simultâneas
- Nao bloquear o event loop no handler do webhook — tudo deve ser `async`
- Nao confundir `APP_SECRET` com `ACCESS_TOKEN` — são variáveis completamente diferentes
- Nao usar múltiplos workers uvicorn (`--workers 4`) — o broker SSE é in-memory e quebraria
- Nao commitar `.env` ou `data/crm.db`
