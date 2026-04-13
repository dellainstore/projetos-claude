"""
Serviço de cálculo de frete via Melhor Envio API v2.
Documentação: https://docs.melhorenvio.com.br/

Quando MELHOR_ENVIO_TOKEN não está configurado, retorna
opções de fallback com valores estimados para não travar o checkout.
"""
import requests
from decimal import Decimal
from django.conf import settings


CEP_ORIGEM = '01310100'  # CEP padrão de saída (substituir pelo real no .env)

# Dimensões padrão de um produto médio (roupas)
DIMENSOES_PADRAO = {
    'width':  15,   # cm
    'height':  3,   # cm por peça
    'length': 20,   # cm
    'weight': 0.3,  # kg por peça
}

# IDs dos serviços a consultar
SERVICOS = '1,2'  # 1=PAC Correios, 2=SEDEX Correios

URL_SANDBOX    = 'https://sandbox.melhorenvio.com.br/api/v2/me/shipment/calculate'
URL_PRODUCAO   = 'https://melhorenvio.com.br/api/v2/me/shipment/calculate'

FALLBACK_OPCOES = [
    {
        'id':         'pac_fallback',
        'nome':       'PAC',
        'empresa':    'Correios',
        'preco':      Decimal('18.90'),
        'prazo':      8,
        'descricao':  'Entrega em até 8 dias úteis',
    },
    {
        'id':         'sedex_fallback',
        'nome':       'SEDEX',
        'empresa':    'Correios',
        'preco':      Decimal('34.90'),
        'prazo':      3,
        'descricao':  'Entrega em até 3 dias úteis',
    },
]


def calcular(cep_destino: str, itens: list, valor_declarado: float = 0) -> list:
    """
    Calcula opções de frete para o CEP de destino.

    itens: lista de dicts com chave 'quantidade' e 'preco'
    Retorna: lista de dicts com id, nome, empresa, preco (Decimal), prazo, descricao
    """
    token = getattr(settings, 'MELHOR_ENVIO_TOKEN', '')
    if not token:
        return FALLBACK_OPCOES

    cep_destino_limpo = ''.join(filter(str.isdigit, cep_destino))
    if len(cep_destino_limpo) != 8:
        return FALLBACK_OPCOES

    # Monta lista de produtos com dimensões
    qtd_total = sum(int(i.get('quantidade', 1)) for i in itens)
    produtos_payload = [{
        'id':               '1',
        'width':            DIMENSOES_PADRAO['width'],
        'height':           DIMENSOES_PADRAO['height'] * max(qtd_total, 1),
        'length':           DIMENSOES_PADRAO['length'],
        'weight':           DIMENSOES_PADRAO['weight'] * max(qtd_total, 1),
        'insurance_value':  max(valor_declarado, 1),
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
        'from':     {'postal_code': CEP_ORIGEM},
        'to':       {'postal_code': cep_destino_limpo},
        'products': produtos_payload,
        'options':  {'receipt': False, 'own_hand': False},
        'services': SERVICOS,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        resp.raise_for_status()
        dados = resp.json()
    except Exception:
        return FALLBACK_OPCOES

    opcoes = []
    for servico in dados:
        if servico.get('error'):
            continue
        preco = servico.get('price') or servico.get('custom_price')
        prazo = servico.get('delivery_time') or servico.get('custom_delivery_time', 0)
        if not preco:
            continue
        opcoes.append({
            'id':        str(servico.get('id', '')),
            'nome':      servico.get('name', ''),
            'empresa':   servico.get('company', {}).get('name', ''),
            'preco':     Decimal(str(preco)),
            'prazo':     int(prazo),
            'descricao': f"Entrega em até {prazo} dias úteis",
        })

    return opcoes if opcoes else FALLBACK_OPCOES
