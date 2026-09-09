import os

LALAMOVE_API_KEY = os.environ.get("LALAMOVE_API_KEY", "").strip()
LALAMOVE_API_SECRET = os.environ.get("LALAMOVE_API_SECRET", "").strip()
LALAMOVE_MARKET = os.environ.get("LALAMOVE_MARKET", "BR").strip() or "BR"
LALAMOVE_SANDBOX = os.environ.get("LALAMOVE_SANDBOX", "True").strip().lower() in ("1", "true", "yes")
# A Lalamove NAO assina os webhooks — a doc v3 nao define assinatura, header
# de autenticacao nem nada equivalente, so exige que o endpoint responda 200.
# Entao a protecao do endpoint publico e um token secreto no proprio caminho
# da URL cadastrada no portal deles:
#   https://sistemas.dellainstore.com/motoqueiro/webhook/lalamove/<token>/
LALAMOVE_WEBHOOK_TOKEN = os.environ.get("LALAMOVE_WEBHOOK_TOKEN", "").strip()

LALAMOVE_BASE_URL = (
    "https://sandbox-rest.lalamove.com" if LALAMOVE_SANDBOX else "https://rest.lalamove.com"
)

# Loggi — conseguir com o time comercial/Sales Engineering da Loggi (nao tem
# autoatendimento tipo a Lalamove): client_id/secret + company_id vem da
# ativacao da conta PJ; external_service_id e especifico do servico
# contratado (confirmar que corresponde a entrega expressa tipo moto —
# PICKUP_TYPE_SPOT + FREIGHT_TYPE_EXPRESS). Ver detalhes em
# memory/project_loggi_integracao_motoqueiro.md.
LOGGI_CLIENT_ID = os.environ.get("LOGGI_CLIENT_ID", "").strip()
LOGGI_CLIENT_SECRET = os.environ.get("LOGGI_CLIENT_SECRET", "").strip()
LOGGI_COMPANY_ID = os.environ.get("LOGGI_COMPANY_ID", "").strip()
LOGGI_EXTERNAL_SERVICE_ID = os.environ.get("LOGGI_EXTERNAL_SERVICE_ID", "").strip()
LOGGI_SANDBOX = os.environ.get("LOGGI_SANDBOX", "True").strip().lower() in ("1", "true", "yes")
# Webhook: a Loggi autentica via Basic Auth (usuario/senha combinados com o
# time de vendas deles na hora de cadastrar o endpoint) — nao e' HMAC como a
# Lalamove.
LOGGI_WEBHOOK_USER = os.environ.get("LOGGI_WEBHOOK_USER", "").strip()
LOGGI_WEBHOOK_PASSWORD = os.environ.get("LOGGI_WEBHOOK_PASSWORD", "").strip()

LOGGI_BASE_URL = (
    "https://stg.api.loggi.com" if LOGGI_SANDBOX else "https://api.loggi.com"
)

# Monitoramento de cotação (Financeiro > Motoqueiro > Monitoramento) — avisa
# num bot/grupo do Telegram quando acha o preço-alvo. Criar o bot no
# @BotFather (token vem de lá); TELEGRAM_CHAT_ID é o id do grupo/conversa que
# vai receber o aviso — ver instruções em services/telegram.py.
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "").strip()

# Domínio público do painel (não o do site) — usado só pra montar o link
# "Pedir agora" dentro da mensagem do Telegram (fora do navegador, não dá
# pra usar request.build_absolute_uri()).
PAINEL_BASE_URL = os.environ.get("PAINEL_BASE_URL", "https://sistemas.dellainstore.com").strip().rstrip("/")
