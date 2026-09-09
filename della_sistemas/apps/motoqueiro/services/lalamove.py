"""Cliente da API Lalamove v3 (REST) — assinatura HMAC-SHA256.

Docs: https://developers.lalamove.com/
Fluxo usado pelo modulo Motoqueiro:
  1. geocodificar_endereco()  -> lat/lng via Nominatim (sem chave, gratis)
  2. criar_cotacao()          -> POST /v3/quotations (nao cobra nada, so cota)
  3. criar_pedido()           -> POST /v3/orders (aqui sim confirma e cobra)
  4. obter_pedido()           -> GET /v3/orders/{id} (consulta status)

Webhook (recebe status atualizado sem precisar ficar consultando):
  verificar_token_webhook() valida o token da URL recebida em
  apps/motoqueiro/views/webhook.py antes de aplicar qualquer mudanca de status.
"""
import hashlib
import hmac
import json
import re
import time
import uuid

import requests

from .config import (
    LALAMOVE_API_KEY,
    LALAMOVE_API_SECRET,
    LALAMOVE_BASE_URL,
    LALAMOVE_MARKET,
    LALAMOVE_WEBHOOK_TOKEN,
)

TIMEOUT = 20


def _telefone_e164(telefone: str) -> str:
    """Normaliza pro formato E.164 exigido pela Lalamove (ex: +5511991771687).
    A tela de Solicitar aceita texto livre ((11) 90000-0000, com espaço,
    traço etc.) — aqui limpa tudo que não é dígito e garante o DDI 55 na
    frente. Só cobre número nacional (DDD + 8 ou 9 dígitos); se já vier com
    o 55 na frente, não duplica."""
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return ""
    if not digitos.startswith("55") or len(digitos) not in (12, 13):
        digitos = "55" + digitos
    return "+" + digitos


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


def _request(method: str, path: str, payload: dict | None = None, timeout: int | None = None) -> dict:
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
        headers=headers, timeout=timeout or TIMEOUT,
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
                "phone": _telefone_e164(remetente_telefone),
            },
            "recipients": [
                {
                    "stopId": stop_id_entrega,
                    "name": destinatario,
                    "phone": _telefone_e164(destinatario_telefone),
                    "remarks": observacao,
                }
            ],
        }
    }
    return _request("POST", "/v3/orders", payload)


def obter_pedido(order_id: str, timeout: int | None = None) -> dict:
    """GET /v3/orders/{orderId} — consulta status atual (fallback se o
    webhook falhar ou pra conferencia manual).

    `timeout` menor e' usado quando a consulta acontece dentro do carregamento
    de uma pagina: melhor a linha ficar com o status velho do que a tela
    inteira pendurar esperando a Lalamove."""
    return _request("GET", f"/v3/orders/{order_id}", timeout=timeout)


def cancelar_pedido(order_id: str) -> dict:
    """DELETE /v3/orders/{orderId} — cancela a corrida na Lalamove.

    So e' aceito enquanto o pedido esta procurando motoboy (ASSIGNING_DRIVER)
    ou ate 5 minutos depois de casar com um. Fora disso a API responde 409
    com {"message": "ERR_CANCELLATION_FORBIDDEN"} — que sobe como
    LalamoveError pra view traduzir numa mensagem util. Sucesso e' 204 sem
    corpo, entao o retorno normal e' um dict vazio."""
    return _request("DELETE", f"/v3/orders/{order_id}")


def adicionar_prioridade(order_id: str, valor) -> dict:
    """POST /v3/orders/{orderId}/priority-fee — aumenta a taxa de prioridade.

    Regras da Lalamove: so aceita antes de um motoboy aceitar a corrida, e
    cada valor novo SUBSTITUI o anterior (nao soma) e precisa ser maior que o
    anterior. Erros conhecidos: ERR_EXCEED_MIN_TIPS / ERR_EXCEED_MAX_TIPS
    quando o valor esta fora da faixa daquele mercado."""
    return _request("POST", f"/v3/orders/{order_id}/priority-fee",
                    {"data": {"priorityFee": f"{valor:.0f}" if valor == int(valor) else f"{valor:.2f}"}})


def verificar_token_webhook(token: str) -> bool:
    """Confere o token secreto que vem no caminho da URL do webhook.

    A Lalamove nao assina os webhooks: a doc v3 nao especifica assinatura,
    header de autenticacao nem verificacao de origem — so pede que o endpoint
    responda 200. A tentativa anterior (HMAC no header Authorization, no mesmo
    esquema das chamadas de API) rejeitava 100% das notificacoes reais, porque
    esse header simplesmente nunca chega.

    A protecao passa a ser o segredo no proprio caminho da URL cadastrada no
    portal da Lalamove. Quem nao conhece o token nao consegue nem chegar na
    view. Se LALAMOVE_WEBHOOK_TOKEN estiver vazio, nada e aceito — melhor o
    status ficar parado do que abrir o endpoint pra qualquer um.
    """
    if not LALAMOVE_WEBHOOK_TOKEN:
        return False
    return hmac.compare_digest(token or "", LALAMOVE_WEBHOOK_TOKEN)


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
    "CANCELED": "cancelado",
}


def traduzir_status(status_lalamove: str) -> str:
    from apps.motoqueiro.models import SolicitacaoEntrega
    return MAPA_STATUS_LALAMOVE.get(status_lalamove, SolicitacaoEntrega.STATUS_AGUARDANDO_COLETA)
