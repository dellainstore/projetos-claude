"""
Serviço PagSeguro (PagBank) — Checkout Transparente via API v4.
Documentação: https://dev.pagbank.uol.com.br/reference

Fluxo do cartão de crédito:
  1. Frontend carrega o SDK PagSeguro e usa obter_chave_publica() para
     encriptar os dados do cartão no browser — o PAN nunca chega ao nosso
     servidor.
  2. O frontend envia apenas o encryptedCard ao backend.
  3. criar_ordem_cartao() chama a API PagSeguro com o encryptedCard.
  4. O webhook pagseguro_notificacao (views.py) atualiza o status do pedido
     conforme notificações assíncronas (ex: confirmação pós-antifraude).
"""
import logging

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

_CACHE_KEY_PUBKEY = 'pagseguro_public_key'
_CACHE_TIMEOUT    = 60 * 60   # 1 hora


# ─── Helpers internos ─────────────────────────────────────────────────────────

def _base_url() -> str:
    if settings.PAGSEGURO_SANDBOX:
        return 'https://sandbox.api.pagseguro.com'
    return 'https://api.pagseguro.com'


def _headers() -> dict:
    token = (settings.PAGSEGURO_TOKEN or '').strip()
    return {
        'Authorization': f'Bearer {token}',
        'Content-Type':  'application/json',
        'Accept':        'application/json',
    }


# ─── Chave pública ────────────────────────────────────────────────────────────

def obter_chave_publica() -> str:
    """
    Retorna a chave pública do merchant para encriptação de cartão no frontend.
    Cacheada por 1 hora para evitar chamadas repetidas à API.
    Retorna string vazia em caso de erro (token inválido, API fora do ar, etc.).
    """
    chave = cache.get(_CACHE_KEY_PUBKEY)
    if chave:
        return chave

    url = f'{_base_url()}/public-keys/card'
    try:
        r = requests.get(url, headers=_headers(), timeout=8)
        r.raise_for_status()
        chave = r.json().get('public_key', '')
        if chave:
            cache.set(_CACHE_KEY_PUBKEY, chave, _CACHE_TIMEOUT)
        return chave
    except requests.HTTPError as exc:
        logger.error(
            'PagSeguro: erro %s ao obter chave pública: %s',
            exc.response.status_code if exc.response else '?',
            exc.response.text[:200] if exc.response else exc,
        )
        return ''
    except Exception as exc:
        logger.error('PagSeguro: falha ao obter chave pública: %s', exc)
        return ''


# ─── Criação de ordem com cartão ──────────────────────────────────────────────

def criar_ordem_cartao(pedido, encrypted_card: str, parcelas: int = 1) -> dict:
    """
    Cria uma ordem de pagamento com cartão de crédito via Checkout Transparente.

    Args:
        pedido:         instância de apps.pedidos.models.Pedido já salva no banco
        encrypted_card: string gerada pelo PagSeguro JS SDK no frontend
        parcelas:       número de parcelas (1–12)

    Returns:
        dict com a resposta completa da API (inclui charges[0].status).

    Raises:
        requests.HTTPError  se a API retornar 4xx/5xx
        requests.Timeout    se a API não responder em 30 s
    """
    valor_centavos = int(round(float(pedido.total) * 100))
    cpf_limpo      = ''.join(c for c in (pedido.cpf or '') if c.isdigit())

    items = [
        {
            'reference_id': str(item.pk),
            'name':         item.nome_produto[:64],
            'quantity':     item.quantidade,
            'unit_amount':  int(round(float(item.preco_unitario) * 100)),
        }
        for item in pedido.itens.select_related('produto').all()
    ]

    payload: dict = {
        'reference_id': pedido.numero,
        'customer': {
            'name':   pedido.nome_completo,
            'email':  pedido.email,
            'tax_id': cpf_limpo,
        },
        'items': items,
        'shipping': {
            'address': {
                'street':      pedido.logradouro,
                'number':      pedido.numero_entrega,
                'complement':  pedido.complemento or '',
                'locality':    pedido.bairro,
                'city':        pedido.cidade,
                'region_code': pedido.estado.upper(),
                'country':     'BRA',
                'postal_code': pedido.cep_entrega,
            }
        },
        'charges': [
            {
                'reference_id': pedido.numero,
                'description':  f'Pedido {pedido.numero}',
                'amount': {
                    'value':    valor_centavos,
                    'currency': 'BRL',
                },
                'payment_method': {
                    'type':            'CREDIT_CARD',
                    'installments':    max(1, int(parcelas)),
                    'capture':         True,
                    'soft_descriptor': 'DELLA INSTORE',
                    'card': {
                        'encrypted': encrypted_card,
                        'store':     False,
                    },
                },
                'notification_urls': [
                    f'{settings.SITE_URL.rstrip("/")}/pagamento/pagseguro/notificacao/',
                ],
            }
        ],
    }

    # Telefone (opcional, mas melhora aprovação no antifraude)
    tel_digits = ''.join(c for c in (pedido.telefone or '') if c.isdigit())
    if len(tel_digits) >= 10:
        payload['customer']['phones'] = [{
            'country': '55',
            'area':    tel_digits[:2],
            'number':  tel_digits[2:],
            'type':    'MOBILE',
        }]

    url = f'{_base_url()}/orders'
    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=30)
        if not r.ok:
            logger.error(
                'PagSeguro: erro %s ao criar ordem %s: %s',
                r.status_code, pedido.numero, r.text[:500],
            )
            r.raise_for_status()
        return r.json()
    except requests.HTTPError:
        raise
    except Exception as exc:
        logger.error(
            'PagSeguro: falha de comunicação ao criar ordem %s: %s',
            pedido.numero, exc,
        )
        raise


# ─── Criação de ordem PIX ────────────────────────────────────────────────────

def criar_ordem_pix(pedido) -> dict:
    """
    Cria uma ordem de pagamento PIX via PagBank API.
    Retorna dict com o QR code text e image_link (ou levanta HTTPError).
    Resposta inclui qr_codes[0].text (payload copia-e-cola) e links para PNG.
    """
    from datetime import datetime, timezone, timedelta

    valor_centavos = int(round(float(pedido.total) * 100))
    cpf_limpo      = ''.join(c for c in (pedido.cpf or '') if c.isdigit())

    expira = (datetime.now(timezone.utc) + timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S-03:00')

    site_url = settings.SITE_URL.rstrip('/')
    payload: dict = {
        'reference_id': pedido.numero,
        'customer': {
            'name':   pedido.nome_completo,
            'email':  pedido.email,
            'tax_id': cpf_limpo,
        },
        'items': [{
            'reference_id': pedido.numero,
            'name':         f'Pedido {pedido.numero}',
            'quantity':     1,
            'unit_amount':  valor_centavos,
        }],
        'qr_codes': [{
            'amount':          {'value': valor_centavos},
            'expiration_date': expira,
        }],
        'notification_urls': [
            f'{site_url}/pagamento/pagseguro/notificacao/',
        ],
    }

    tel_digits = ''.join(c for c in (pedido.telefone or '') if c.isdigit())
    if len(tel_digits) >= 10:
        payload['customer']['phones'] = [{
            'country': '55',
            'area':    tel_digits[:2],
            'number':  tel_digits[2:],
            'type':    'MOBILE',
        }]

    url = f'{_base_url()}/orders'
    try:
        r = requests.post(url, json=payload, headers=_headers(), timeout=30)
        if not r.ok:
            logger.error(
                'PagSeguro PIX: erro %s ao criar ordem %s: %s',
                r.status_code, pedido.numero, r.text[:500],
            )
            r.raise_for_status()
        return r.json()
    except requests.HTTPError:
        raise
    except Exception as exc:
        logger.error('PagSeguro PIX: falha na ordem %s: %s', pedido.numero, exc)
        raise


# ─── Mapeamento de status ─────────────────────────────────────────────────────

# Status da charge PagSeguro → status interno do Pedido
_STATUS_CHARGE_MAP: dict[str, str] = {
    'PAID':       'pagamento_confirmado',
    'AUTHORIZED': 'pagamento_confirmado',
    'DECLINED':   'cancelado',
    'CANCELED':   'cancelado',
    # IN_ANALYSIS, WAITING → fica como 'aguardando_pagamento' (webhook atualiza)
}

# Mensagens amigáveis para recusa de cartão
_DECLINE_MESSAGES: dict[str, str] = {
    '20001': 'Saldo insuficiente. Tente outro cartão.',
    '20002': 'Dados do cartão inválidos. Verifique e tente novamente.',
    '20003': 'Cartão bloqueado. Entre em contato com seu banco.',
    '20004': 'Cartão vencido. Tente outro cartão.',
    '20005': 'Transação não autorizada pelo banco emissor.',
    '20006': 'Valor da transação inválido.',
    '20007': 'Cartão não permite este tipo de transação.',
    '20008': 'Número de tentativas excedido. Aguarde e tente novamente.',
    '20009': 'Transação suspeita de fraude.',
}


def consultar_ordem(order_id: str) -> dict | None:
    """
    Reconsulta uma ordem diretamente na API PagBank via GET /orders/{id}.
    Usado pelo webhook para verificar o status real antes de atualizar o pedido,
    evitando que payloads forjados alterem status indevidamente.
    Retorna o dict da resposta ou None em caso de falha.
    """
    url = f'{_base_url()}/orders/{order_id}'
    try:
        r = requests.get(url, headers=_headers(), timeout=10)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.error('PagSeguro: erro ao consultar ordem %s: %s', order_id, exc)
        return None


def mensagem_recusa(charge: dict) -> str:
    """Extrai mensagem amigável da recusa de cartão."""
    response = charge.get('payment_response', {})
    code     = str(response.get('code', ''))
    return _DECLINE_MESSAGES.get(code, 'Pagamento recusado. Tente outro cartão ou use o Pix.')


def status_interno(charge_status: str) -> str | None:
    """Converte status PagSeguro para status interno do Pedido."""
    return _STATUS_CHARGE_MAP.get((charge_status or '').upper())
