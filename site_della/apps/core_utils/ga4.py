"""
GA4 Measurement Protocol — disparo server-side do evento purchase.

Espelha o papel do Meta CAPI (apps/core_utils/meta.py) para o GA4: quando o
pagamento e confirmado fora do browser (ex: webhook do PagBank no caso do PIX),
envia o purchase pelo Measurement Protocol usando o MESMO transaction_id do
evento client-side (gtag). O GA4 deduplica purchases pelo transaction_id, entao
o disparo client + server e seguro e nunca conta a venda duas vezes.

Requer GA_API_SECRET (GA4 Admin > Fluxos de dados > Measurement Protocol API
secrets). Sem o secret, a funcao e um no-op silencioso — igual ao CAPI sem token.
"""
import logging

import requests
from django.conf import settings


logger = logging.getLogger(__name__)

_ENDPOINT = 'https://www.google-analytics.com/mp/collect'


def enviar_ga4_purchase(pedido, *, analytics_consent: bool, client_id: str = '',
                        session_id: str = '') -> bool:
    """
    Envia o evento purchase ao GA4 via Measurement Protocol.

    - analytics_consent: consentimento de Analise persistido no pedido. Sem ele,
      nao envia (LGPD — espelha o gate client-side do gtag).
    - client_id: o client_id do GA4 (cookie _ga) capturado no checkout. Garante a
      mesma identidade/atribuicao do disparo client-side. Sem ele, usa um fallback
      deterministico derivado do numero do pedido (a dedup por transaction_id ainda
      funciona, mas a atribuicao de sessao fica prejudicada).
    - session_id: o session_id GA4 (cookie _ga_<stream>) capturado no checkout.
      Sem ele o GA4 nao consegue vincular o purchase a uma sessao existente e o
      canal de origem aparece como 'Unassigned' no relatorio.
    """
    measurement_id = getattr(settings, 'GA_MEASUREMENT_ID', '') or ''
    api_secret = getattr(settings, 'GA_API_SECRET', '') or ''

    if not measurement_id or not api_secret:
        return False

    if not analytics_consent:
        logger.info('GA4 MP: envio ignorado (purchase %s) por falta de consentimento.', pedido.numero)
        return False

    if not client_id:
        # Fallback: client_id sintetico no formato esperado pelo GA4 (<int>.<int>).
        # Mantem o evento valido; a dedup por transaction_id continua garantida.
        client_id = f'{pedido.pk}.{int(pedido.criado_em.timestamp())}'

    items = list(pedido.itens.select_related('produto').all())

    params = {
        'transaction_id': pedido.numero,
        'currency': 'BRL',
        'value': float(pedido.total),
        'shipping': float(pedido.frete),
        'tax': 0,
        'coupon': getattr(pedido, 'cupom_codigo', '') or '',
        'items': [
            {
                'item_id': str(item.produto_id),
                'item_name': item.nome_produto,
                'item_category': (
                    item.produto.categoria.nome
                    if item.produto and item.produto.categoria_id
                    else ''
                ),
                'price': float(item.preco_unitario),
                'quantity': item.quantidade,
            }
            for item in items
        ],
    }
    if session_id:
        # session_id vincula o evento a uma sessao real — essencial para atribuicao
        # de canal. engagement_time_msec evita que o GA4 descarte o evento.
        params['session_id'] = session_id
        params['engagement_time_msec'] = 1

    payload = {
        'client_id': client_id,
        'non_personalized_ads': False,
        'timestamp_micros': int(pedido.criado_em.timestamp() * 1_000_000),
        'events': [{'name': 'purchase', 'params': params}],
    }

    try:
        response = requests.post(
            _ENDPOINT,
            params={'measurement_id': measurement_id, 'api_secret': api_secret},
            json=payload,
            timeout=5,
        )
        response.raise_for_status()
        logger.info('GA4 MP: purchase enviado com sucesso (%s).', pedido.numero)
        return True
    except requests.RequestException as exc:
        detalhe = ''
        if getattr(exc, 'response', None) is not None:
            detalhe = exc.response.text[:600]
        logger.warning('GA4 MP: falha ao enviar purchase (%s): %s %s', pedido.numero, exc, detalhe)
        return False
