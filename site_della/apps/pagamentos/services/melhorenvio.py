"""
Serviço de cálculo de frete via Melhor Envio API v2.
Documentação: https://docs.melhorenvio.com.br/

Quando MELHOR_ENVIO_TOKEN não está configurado, retorna
opções de fallback com valores estimados para não travar o checkout.
"""
import logging
import requests
from decimal import Decimal
from django.conf import settings


logger = logging.getLogger(__name__)

# CEP de saída: usa MELHOR_ENVIO_CEP_ORIGEM do .env (sem máscara, 8 dígitos)
CEP_ORIGEM = getattr(settings, 'MELHOR_ENVIO_CEP_ORIGEM', '') or '01310100'

# Dimensões da caixa de envio D'ELLA Instore
DIMENSOES_PADRAO = {
    'width':  17,   # cm — largura da caixa
    'height':  8,   # cm — altura da caixa
    'length': 28,   # cm — comprimento da caixa
    'weight': 0.5,  # kg por peça
}

# IDs dos serviços a consultar
SERVICOS = '1,2'  # 1=PAC Correios, 2=SEDEX Correios

URL_SANDBOX    = 'https://sandbox.melhorenvio.com.br/api/v2/me/shipment/calculate'
URL_PRODUCAO   = 'https://melhorenvio.com.br/api/v2/me/shipment/calculate'

FALLBACK_OPCOES = [
    {
        'id':         'pac',
        'nome':       'PAC',
        'empresa':    'Correios',
        'preco':      Decimal('18.90'),
        'prazo':      8,
        'descricao':  'Entrega em até 8 dias úteis',
    },
    {
        'id':         'sedex',
        'nome':       'SEDEX',
        'empresa':    'Correios',
        'preco':      Decimal('34.90'),
        'prazo':      3,
        'descricao':  'Entrega em até 3 dias úteis',
    },
]


def calcular(cep_destino: str, itens: list) -> list:
    """
    Calcula opções de frete para o CEP de destino.

    itens: lista de dicts com chave 'quantidade' e 'preco'
    Retorna: lista de dicts com id, nome, empresa, preco (Decimal), prazo, descricao
    """
    token = getattr(settings, 'MELHOR_ENVIO_TOKEN', '')
    if not token:
        logger.warning('Melhor Envio: token vazio — usando fallback')
        return FALLBACK_OPCOES

    cep_destino_limpo = ''.join(filter(str.isdigit, cep_destino))
    if len(cep_destino_limpo) != 8:
        logger.warning('Melhor Envio: CEP destino inválido "%s" — usando fallback', cep_destino)
        return FALLBACK_OPCOES

    cep_origem_limpo = ''.join(filter(str.isdigit, CEP_ORIGEM))
    if len(cep_origem_limpo) != 8:
        logger.error('Melhor Envio: CEP origem inválido "%s" — usando fallback', CEP_ORIGEM)
        return FALLBACK_OPCOES

    # Monta lista de produtos com dimensões
    peso_total_g = sum(int(i.get('peso', 500)) * int(i.get('quantidade', 1)) for i in itens)
    peso_total_kg = round(max(peso_total_g, 1) / 1000, 3)
    produtos_payload = [{
        'id':               '1',
        'width':            DIMENSOES_PADRAO['width'],
        'height':           DIMENSOES_PADRAO['height'],
        'length':           DIMENSOES_PADRAO['length'],
        'weight':           peso_total_kg,
        'insurance_value':  0,
        'quantity':         1,
    }]

    url = URL_SANDBOX if getattr(settings, 'MELHOR_ENVIO_SANDBOX', True) else URL_PRODUCAO

    headers = {
        'Accept':        'application/json',
        'Content-Type':  'application/json',
        'Authorization': f'Bearer {token}',
        'User-Agent':    'DellaSite/1.0 (contato@dellainstore.com.br)',
    }

    payload = {
        'from':     {'postal_code': cep_origem_limpo},
        'to':       {'postal_code': cep_destino_limpo},
        'products': produtos_payload,
        'options':  {'receipt': False, 'own_hand': False},
        'services': SERVICOS,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        if resp.status_code == 422:
            # CEP rejeitado pelo Melhor Envio — tenta com o CEP raiz (primeiros 5 + "000")
            cep_raiz = cep_destino_limpo[:5] + '000'
            if cep_raiz != cep_destino_limpo:
                logger.warning('Melhor Envio: CEP %s inválido, tentando raiz %s', cep_destino_limpo, cep_raiz)
                payload['to']['postal_code'] = cep_raiz
                try:
                    resp = requests.post(url, json=payload, headers=headers, timeout=10)
                except Exception as exc2:
                    logger.error('Melhor Envio: exceção na tentativa com CEP raiz — %s', exc2)
                    return FALLBACK_OPCOES
        if not resp.ok:
            logger.error('Melhor Envio: HTTP %s — resposta: %s', resp.status_code, resp.text[:500])
            return FALLBACK_OPCOES
        dados = resp.json()
    except Exception as exc:
        logger.error('Melhor Envio: exceção no cálculo — %s', exc)
        return FALLBACK_OPCOES

    opcoes = []
    for servico in dados:
        if servico.get('error'):
            logger.warning('Melhor Envio: serviço %s retornou erro: %s',
                           servico.get('id'), servico.get('error'))
            continue
        preco = servico.get('price') or servico.get('custom_price')
        prazo = servico.get('delivery_time') or servico.get('custom_delivery_time', 0)
        if not preco:
            continue
        prazo_final = int(prazo) + 1
        preco_final = Decimal(str(preco)) + Decimal('3.00')
        opcoes.append({
            'id':        str(servico.get('id', '')),
            'nome':      servico.get('name', ''),
            'empresa':   servico.get('company', {}).get('name', ''),
            'preco':     preco_final,
            'prazo':     prazo_final,
            'descricao': f"Entrega em até {prazo_final} dias úteis",
        })

    if not opcoes:
        logger.warning('Melhor Envio: nenhum serviço válido retornado — usando fallback')
        return FALLBACK_OPCOES
    return opcoes
