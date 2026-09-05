"""Cliente da API REST da Loggi — autenticacao OAuth2 (client credentials).

Docs: https://docs.api.loggi.com (indice completo em
https://docs.api.loggi.com/llms.txt) — o link que a Loggi mandou
(ajuda.loggi.com/.../Guia-de-Integracoes-API-EDI) aponta pra esse mesmo
developer portal.

STATUS (2026-09-05): ESQUELETO NAO TESTADO. Ainda faltam as credenciais reais
(LOGGI_CLIENT_ID/SECRET/COMPANY_ID/EXTERNAL_SERVICE_ID no .env — ver
memory/project_loggi_integracao_motoqueiro.md pra saber onde consegui-las).
Os nomes de campo/endpoint abaixo vem direto da doc publica, mas SO validar
contra a API real (staging) antes de habilitar isso na tela de Solicitar.

Fluxo (diferente da Lalamove em dois pontos importantes — ver comentarios):
  1. autenticar()      -> POST /oauth2/token, cacheia o token em memoria
  2. criar_cotacao()   -> POST /v1/companies/{id}/quotations (sincrono, nao
                           cobra nem compromete — igual Lalamove)
  3. criar_shipment()  -> POST /v1/companies/{id}/async-shipments — AQUI e'
                           diferente: responde 202 na hora, mas o resultado
                           definitivo (sucesso real) so chega depois via
                           webhook. Exige documento fiscal por pacote
                           (documentTypes) mesmo pra corrida avulsa de
                           motoboy — ver `_content_declaration()`.
  4. criar_etiqueta()  -> POST /v1/companies/{id}/labels (PDF) — a Lalamove
                           nao tem esse conceito, motoboy so retira na mao.
  5. obter_status()    -> GET tracking (fallback se o webhook nao chegar)
  6. cancelar()         -> POST cancel

Webhook (apps/motoqueiro/views/webhook.py -> webhook_loggi): a Loggi usa
Basic Auth (usuario/senha combinados com o time de vendas deles ao cadastrar
o endpoint), nao HMAC como a Lalamove. `verificar_assinatura_webhook()`
confere isso.
"""
import time

import requests

from .config import (
    LOGGI_BASE_URL,
    LOGGI_CLIENT_ID,
    LOGGI_CLIENT_SECRET,
    LOGGI_COMPANY_ID,
    LOGGI_EXTERNAL_SERVICE_ID,
    LOGGI_WEBHOOK_PASSWORD,
    LOGGI_WEBHOOK_USER,
)

TIMEOUT = 20

# Cache do token em memoria de processo (por worker Gunicorn — suficiente
# aqui, mesmo esquema simples que o resto do modulo usa). Renovado um pouco
# antes de expirar (margem de 60s) pra nao correr risco de token vencido
# no meio de uma chamada.
_token_cache: dict = {"idToken": "", "expira_em": 0.0}


class LoggiError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Loggi API {status_code}: {body}")


def _autenticar() -> str:
    """POST /oauth2/token com client_id/client_secret -> idToken (Bearer).
    NAO CONFIRMADO ao vivo: a doc publica mostra tanto `/oauth2/token`
    quanto `/v2/oauth2/token` dependendo da pagina — testar os dois em
    staging antes de confiar; ajustar aqui se o caminho certo for outro."""
    if _token_cache["idToken"] and time.time() < _token_cache["expira_em"] - 60:
        return _token_cache["idToken"]

    resp = requests.post(
        f"{LOGGI_BASE_URL}/oauth2/token",
        json={"client_id": LOGGI_CLIENT_ID, "client_secret": LOGGI_CLIENT_SECRET},
        headers={"Content-Type": "application/json"},
        timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        raise LoggiError(resp.status_code, resp.text)
    dados = resp.json()
    token = dados.get("idToken", "")
    expira_em_segundos = float(dados.get("expiresIn") or 3600)
    _token_cache["idToken"] = token
    _token_cache["expira_em"] = time.time() + expira_em_segundos
    return token


def _request(method: str, path: str, payload: dict | None = None, params: dict | None = None) -> dict:
    token = _autenticar()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    resp = requests.request(
        method, f"{LOGGI_BASE_URL}{path}",
        json=payload, params=params, headers=headers, timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        raise LoggiError(resp.status_code, resp.text)
    if not resp.text:
        return {}
    return resp.json()


def _endereco_correios(logradouro: str, numero: str, complemento: str, bairro: str, cep: str, cidade: str, uf: str) -> dict:
    """Formato `correiosAddress`/`correios` esperado pela Loggi. Mutuamente
    exclusivo com o formato `lineAddress`/`lines` (internacional) — usar
    sempre este pra entrega nacional."""
    return {
        "logradouro": logradouro,
        "numero": numero,
        "complemento": complemento,
        "bairro": bairro,
        "cep": cep.replace("-", "").replace(".", ""),
        "cidade": cidade,
        "uf": uf,
    }


def criar_cotacao(
    *, endereco_retirada: dict, endereco_entrega: dict,
    peso_g: int, comprimento_cm: int, largura_cm: int, altura_cm: int,
    valor_declarado_reais: float = 0.0,
) -> dict:
    """POST /v1/companies/{company_id}/quotations — so cota, nao cria nada.

    `endereco_retirada`/`endereco_entrega`: dict no formato de
    `_endereco_correios()`. `pickupTypes: PICKUP_TYPE_SPOT` e' o que
    corresponde ao caso "motoboy agora" (equivalente ao LalaGo/LalaPro da
    Lalamove) — NAO CONFIRMADO ao vivo ainda qual tipo o contrato de voces
    realmente cobre; conferir com o Sales Engineering da Loggi.
    """
    reais_inteiros = int(valor_declarado_reais)
    nanos = round((valor_declarado_reais - reais_inteiros) * 1_000_000_000)
    payload = {
        "shipFrom": {"correios": endereco_retirada},
        "shipTo": {"correios": endereco_entrega},
        "packages": [
            {
                "weightG": peso_g,
                "lengthCm": comprimento_cm,
                "widthCm": largura_cm,
                "heightCm": altura_cm,
                "goodsValue": {
                    "currencyCode": "BRL",
                    "units": reais_inteiros,
                    "nanos": nanos,
                },
            }
        ],
        "pickupTypes": ["PICKUP_TYPE_SPOT"],
    }
    return _request("POST", f"/v1/companies/{LOGGI_COMPANY_ID}/quotations", payload)


def _content_declaration(descricao: str, valor_reais: float) -> dict:
    """Declaracao de conteudo — usada no lugar de NF-e real pra corridas
    avulsas de motoboy (sem pedido Bling associado). CONFIRMAR COM A LOGGI
    se isso e' aceito pro servico contratado; a doc so garante que e' uma
    das opcoes validas de `documentTypes`, nao que serve pra qualquer
    contrato."""
    return {
        "contentDeclaration": {
            "totalValue": f"{valor_reais:.2f}",
            "description": descricao[:100],
        }
    }


def criar_shipment(
    *, endereco_retirada: dict, remetente: str, remetente_telefone: str,
    endereco_entrega: dict, destinatario: str, destinatario_telefone: str,
    peso_g: int, comprimento_cm: int, largura_cm: int, altura_cm: int,
    descricao_conteudo: str, valor_declarado_reais: float,
    instrucoes_retirada: str = "", instrucoes_entrega: str = "",
) -> dict:
    """POST /v1/companies/{company_id}/async-shipments — CONFIRMA e cobra.
    Responde 202 (aceito), mas o resultado definitivo (sucesso ou erro real
    de processamento) so chega depois pelo webhook — diferente da Lalamove,
    que confirma tudo na resposta sincrona. So chamar depois que o usuario
    ja viu o preco da cotacao e apertou 'confirmar'."""
    payload = {
        "externalServiceId": LOGGI_EXTERNAL_SERVICE_ID,
        "shipFrom": {
            "name": remetente,
            "phoneNumber": remetente_telefone,
            "address": {
                "instructions": instrucoes_retirada[:300] if instrucoes_retirada else None,
                "correiosAddress": endereco_retirada,
            },
        },
        "shipTo": {
            "name": destinatario,
            "phoneNumber": destinatario_telefone,
            "address": {
                "instructions": instrucoes_entrega[:300] if instrucoes_entrega else None,
                "correiosAddress": endereco_entrega,
            },
        },
        "packages": [
            {
                "freightType": "FREIGHT_TYPE_EXPRESS",
                "weightG": peso_g,
                "lengthCm": comprimento_cm,
                "widthCm": largura_cm,
                "heightCm": altura_cm,
                "documentTypes": [
                    _content_declaration(descricao_conteudo, valor_declarado_reais)
                ],
            }
        ],
    }
    return _request("POST", f"/v1/companies/{LOGGI_COMPANY_ID}/async-shipments", payload)


def criar_etiqueta(loggi_keys: list[str]) -> dict:
    """POST /v1/companies/{company_id}/labels — so pode ser chamado depois
    que o shipment foi de fato confirmado (via webhook), nao logo apos o
    202 do criar_shipment()."""
    payload = {
        "loggiKeys": loggi_keys,
        "format": "LABEL_FORMAT_PDF",
        "layout": "LABEL_LAYOUT_A6",
        "responseType": "LABEL_RESPONSE_TYPE_URL",
    }
    return _request("POST", f"/v1/companies/{LOGGI_COMPANY_ID}/labels", payload)


def obter_status(tracking_code: str) -> dict:
    """GET tracking — consulta status atual (fallback se o webhook falhar
    ou pra conferencia manual)."""
    return _request("GET", f"/v1/companies/{LOGGI_COMPANY_ID}/packages/{tracking_code}/tracking")


def cancelar(*, loggi_key: str = "", tracking_code: str = "") -> dict:
    """POST cancel — so garante efeito se o pacote ainda nao saiu pra rota
    de entrega. Passa loggi_key OU tracking_code (loggi_key tem prioridade
    se os dois forem passados, conforme a doc)."""
    params = {}
    if loggi_key:
        params["loggi_key"] = loggi_key
    elif tracking_code:
        params["tracking_code"] = tracking_code
    return _request("POST", f"/v1/companies/{LOGGI_COMPANY_ID}/packages/cancel", params=params)


def verificar_assinatura_webhook(headers) -> bool:
    """A Loggi autentica o webhook via Basic Auth simples (usuario/senha
    combinados com o time de vendas deles), nao HMAC. Confere contra
    LOGGI_WEBHOOK_USER/LOGGI_WEBHOOK_PASSWORD do .env."""
    import base64

    auth = headers.get("Authorization", "")
    if not auth.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(auth[len("Basic "):]).decode("utf-8")
        usuario, senha = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError, base64.binascii.Error):
        return False
    return usuario == LOGGI_WEBHOOK_USER and senha == LOGGI_WEBHOOK_PASSWORD


# Mapeia o codigo de status bruto da Loggi (webhook/tracking) para os 5
# status do painel D'ELLA. Codigos confirmados pela doc publica — LISTA
# INCOMPLETA (a Loggi cita que ha mais codigos, sem publicar todos); pedir a
# lista completa ao Sales Engineering antes de depender disso em producao.
MAPA_STATUS_LOGGI = {
    1: "aguardando_coleta",   # Adicionado
    3: "aguardando_coleta",   # Em processamento
    11: "no_percurso",        # Saiu para entrega
    5: "entrega_realizada",   # Entregue
    6: "problema_coleta",     # Com problema
}


def traduzir_status(status_code: int) -> str:
    from apps.motoqueiro.models import SolicitacaoEntrega
    return MAPA_STATUS_LOGGI.get(status_code, SolicitacaoEntrega.STATUS_AGUARDANDO_COLETA)
