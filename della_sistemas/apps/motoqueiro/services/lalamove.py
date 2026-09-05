"""Cliente da API Lalamove v3 (REST) — assinatura HMAC-SHA256.

Docs: https://developers.lalamove.com/
Fluxo usado pelo modulo Motoqueiro:
  1. geocodificar_endereco()  -> lat/lng via Nominatim (sem chave, gratis)
  2. criar_cotacao()          -> POST /v3/quotations (nao cobra nada, so cota)
  3. criar_pedido()           -> POST /v3/orders (aqui sim confirma e cobra)
  4. obter_pedido()           -> GET /v3/orders/{id} (consulta status)

Webhook (recebe status atualizado sem precisar ficar consultando):
  verificar_assinatura_webhook() valida o payload recebido em
  apps/motoqueiro/views/webhook.py antes de aplicar qualquer mudanca de status.
"""
import hashlib
import hmac
import json
import time
import uuid

import requests

from .config import (
    LALAMOVE_API_KEY,
    LALAMOVE_API_SECRET,
    LALAMOVE_BASE_URL,
    LALAMOVE_MARKET,
    LALAMOVE_WEBHOOK_SECRET,
)

TIMEOUT = 20


class LalamoveError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Lalamove API {status_code}: {body}")


def _assinar(timestamp: str, method: str, path: str, body: str) -> str:
    raw = f"{timestamp}\r\n{method}\r\n{path}\r\n\r\n{body}"
    return hmac.new(
        LALAMOVE_API_SECRET.encode("utf-8"), raw.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _request(method: str, path: str, payload: dict | None = None) -> dict:
    body = json.dumps(payload, ensure_ascii=False) if payload is not None else ""
    timestamp = str(int(time.time() * 1000))
    assinatura = _assinar(timestamp, method, path, body)
    headers = {
        "Authorization": f"hmac {LALAMOVE_API_KEY}:{timestamp}:{assinatura}",
        "Market": LALAMOVE_MARKET,
        "Content-Type": "application/json",
        "Request-Id": str(uuid.uuid4()),
        "Accept": "application/json",
    }
    resp = requests.request(
        method, f"{LALAMOVE_BASE_URL}{path}",
        data=body if payload is not None else None,
        headers=headers, timeout=TIMEOUT,
    )
    if resp.status_code >= 400:
        raise LalamoveError(resp.status_code, resp.text)
    if not resp.text:
        return {}
    return resp.json()


def geocodificar_endereco(endereco: str) -> tuple[float, float] | None:
    """Nominatim (OpenStreetMap) — gratis, sem chave, limite 1 req/s. So um
    resultado direto (sem lista pra escolher) — usado como fallback; o fluxo
    principal da tela de Solicitar usa `geocoding.buscar_enderecos()`
    (autocomplete com lista) e ja manda o lat/lng escolhido direto."""
    from .geocoding import _VIEWBOX_SP

    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={
            "q": endereco, "format": "json", "limit": 1, "countrycodes": "br",
            "viewbox": _VIEWBOX_SP, "bounded": 1,
        },
        headers={"User-Agent": "della-sistemas-motoqueiro/1.0"},
        timeout=10,
    )
    resp.raise_for_status()
    resultados = resp.json()
    if not resultados:
        return None
    r = resultados[0]
    return float(r["lat"]), float(r["lon"])


def criar_cotacao(
    *, endereco_retirada: str, lat_retirada: float, lng_retirada: float,
    endereco_entrega: str, lat_entrega: float, lng_entrega: float,
    service_type: str = "LALAGO",
) -> dict:
    """POST /v3/quotations — so cota, nao cobra e nao compromete nada.

    service_type default = "LALAGO": confirmado via GET /v3/cities (mercado
    BR SAO, Sao Paulo & Campinas) como o servico de entrega pequena/moto
    (limite 20kg, ~0.3x0.4x0.3m, opcao de bag termica) — Lalamove Brasil NAO
    usa o codigo generico "MOTORCYCLE" de outros mercados. NAO trocar para
    CAR/HATCHBACK sem confirmar, senao cota/pede carro em vez de moto.
    """
    payload = {
        "data": {
            "serviceType": service_type,
            "language": "pt_BR",
            "stops": [
                {
                    "coordinates": {"lat": str(lat_retirada), "lng": str(lng_retirada)},
                    "address": endereco_retirada,
                },
                {
                    "coordinates": {"lat": str(lat_entrega), "lng": str(lng_entrega)},
                    "address": endereco_entrega,
                },
            ],
        }
    }
    return _request("POST", "/v3/quotations", payload)


def criar_pedido(
    *, quotation_id: str, stop_id_retirada: str, stop_id_entrega: str,
    remetente: str, remetente_telefone: str,
    destinatario: str, destinatario_telefone: str,
    observacao: str = "",
) -> dict:
    """POST /v3/orders — CONFIRMA e cobra de verdade. So chamar depois que o
    usuario ja viu o preco da cotacao e apertou 'confirmar' na tela."""
    payload = {
        "data": {
            "quotationId": quotation_id,
            "sender": {
                "stopId": stop_id_retirada,
                "name": remetente,
                "phone": remetente_telefone,
            },
            "recipients": [
                {
                    "stopId": stop_id_entrega,
                    "name": destinatario,
                    "phone": destinatario_telefone,
                    "remarks": observacao,
                }
            ],
        }
    }
    return _request("POST", "/v3/orders", payload)


def obter_pedido(order_id: str) -> dict:
    """GET /v3/orders/{orderId} — consulta status atual (fallback se o
    webhook falhar ou pra conferencia manual)."""
    return _request("GET", f"/v3/orders/{order_id}")


def verificar_assinatura_webhook(headers, raw_body: bytes) -> bool:
    """Confere a assinatura do webhook antes de confiar no payload.

    ATENCAO: o formato exato do header/assinatura do webhook v3 da Lalamove
    nao pode ser confirmado sem ver um payload real chegando (a doc publica
    varia por versao). Implementado com o mesmo esquema HMAC das chamadas de
    API (Authorization: hmac key:timestamp:signature). Se o primeiro webhook
    real vier num formato diferente, ajustar aqui — o evento inteiro (headers
    + body) fica logado em SolicitacaoEntregaEvento mesmo quando a assinatura
    nao bate, exatamente para permitir esse ajuste sem perder dado.
    """
    auth = headers.get("Authorization", "")
    if not auth.startswith("hmac "):
        return False
    try:
        key, timestamp, assinatura_recebida = auth[len("hmac "):].split(":", 2)
    except ValueError:
        return False
    if key != LALAMOVE_API_KEY:
        return False
    esperada = hmac.new(
        LALAMOVE_WEBHOOK_SECRET.encode("utf-8"),
        f"{timestamp}\r\n{raw_body.decode('utf-8')}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(esperada, assinatura_recebida)


# Mapeia o status bruto da Lalamove para os 5 status do painel D'ELLA.
# Referencia (ordens de lifecycle da Lalamove): ASSIGNING_DRIVER -> ON_GOING
# -> PICKED_UP -> COMPLETED, alem de CANCELED/REJECTED/EXPIRED.
MAPA_STATUS_LALAMOVE = {
    "ASSIGNING_DRIVER": "aguardando_coleta",
    "ON_GOING": "aguardando_coleta",
    "PICKED_UP": "no_percurso",
    "COMPLETED": "entrega_realizada",
    "REJECTED": "problema_coleta",
    "EXPIRED": "problema_coleta",
    "CANCELED": "problema_entrega",
}


def traduzir_status(status_lalamove: str) -> str:
    from apps.motoqueiro.models import SolicitacaoEntrega
    return MAPA_STATUS_LALAMOVE.get(status_lalamove, SolicitacaoEntrega.STATUS_AGUARDANDO_COLETA)
