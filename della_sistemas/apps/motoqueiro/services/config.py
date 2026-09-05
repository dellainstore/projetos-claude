import os

LALAMOVE_API_KEY = os.environ.get("LALAMOVE_API_KEY", "").strip()
LALAMOVE_API_SECRET = os.environ.get("LALAMOVE_API_SECRET", "").strip()
LALAMOVE_MARKET = os.environ.get("LALAMOVE_MARKET", "BR").strip() or "BR"
LALAMOVE_SANDBOX = os.environ.get("LALAMOVE_SANDBOX", "True").strip().lower() in ("1", "true", "yes")
# Se a Lalamove nao expuser um segredo de webhook separado no painel deles,
# a verificacao da assinatura do webhook cai para o API_SECRET normal.
LALAMOVE_WEBHOOK_SECRET = os.environ.get("LALAMOVE_WEBHOOK_SECRET", "").strip() or LALAMOVE_API_SECRET

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
