"""
Serviços de alto nível para integração com o Bling.

Funções principais:
    enviar_pedido_bling(pedido) → bool
    emitir_nfe_bling(pedido)    → bool
"""

import logging
from datetime import date, timedelta

from django.conf import settings

from .api import BlingAPI, BlingAPIError
from .models import BlingLog

logger = logging.getLogger(__name__)


# ── Mapeamento de situações do Bling ─────────────────────────────────────────
# Situação padrão para novos pedidos no Bling
SITUACAO_EM_ANDAMENTO = 6
SITUACAO_APROVADO     = 9
SITUACAO_CANCELADO    = 12


def enviar_pedido_bling(pedido) -> bool:
    """
    Envia um pedido para o Bling como "Pedido de Venda".

    Retorna True em caso de sucesso, False em caso de falha.
    Registra tudo em BlingLog para diagnóstico.
    """
    if pedido.bling_pedido_id:
        logger.info('Pedido %s já enviado ao Bling (id=%s)', pedido.numero, pedido.bling_pedido_id)
        return True

    payload = _montar_payload_pedido(pedido)

    try:
        api = BlingAPI()
        resposta = api.criar_pedido_venda(payload)
    except BlingAPIError as exc:
        BlingLog.objects.create(
            tipo='pedido',
            pedido=pedido,
            sucesso=False,
            payload_enviado=payload,
            resposta={},
            erro=str(exc),
        )
        logger.error('Bling: erro ao enviar pedido %s: %s', pedido.numero, exc)
        return False
    except Exception as exc:
        BlingLog.objects.create(
            tipo='pedido',
            pedido=pedido,
            sucesso=False,
            payload_enviado=payload,
            resposta={},
            erro=f'Erro inesperado: {exc}',
        )
        logger.error('Bling: exceção inesperada no pedido %s: %s', pedido.numero, exc)
        return False

    # Extrai o ID do Bling da resposta
    # A API v3 retorna: {"data": {"id": 12345, ...}}
    bling_id = str(resposta.get('data', {}).get('id', ''))

    BlingLog.objects.create(
        tipo='pedido',
        pedido=pedido,
        sucesso=True,
        payload_enviado=payload,
        resposta=resposta,
    )

    if bling_id:
        pedido.bling_pedido_id = bling_id
        pedido.save(update_fields=['bling_pedido_id', 'atualizado_em'])
        logger.info('Pedido %s enviado ao Bling com id=%s', pedido.numero, bling_id)

    return True


def emitir_nfe_bling(pedido) -> bool:
    """
    Emite NF-e para um pedido a partir do pedido já criado no Bling.

    Pré-requisito: pedido.bling_pedido_id deve estar preenchido.
    A configuração fiscal (CFOP, NCM, tributação) deve estar feita no Bling.

    Retorna True em caso de sucesso, False em caso de falha.
    """
    if not pedido.bling_pedido_id:
        logger.warning('Não é possível emitir NF-e: pedido %s sem bling_pedido_id', pedido.numero)
        return False

    if pedido.bling_nfe_id:
        logger.info('NF-e já emitida para pedido %s (nfe_id=%s)', pedido.numero, pedido.bling_nfe_id)
        return True

    try:
        api = BlingAPI()
        resposta = api.emitir_nfe_do_pedido(pedido.bling_pedido_id)
    except BlingAPIError as exc:
        BlingLog.objects.create(
            tipo='nfe',
            pedido=pedido,
            sucesso=False,
            payload_enviado={'bling_pedido_id': pedido.bling_pedido_id},
            resposta={},
            erro=str(exc),
        )
        logger.error('Bling: erro ao emitir NF-e do pedido %s: %s', pedido.numero, exc)
        return False
    except Exception as exc:
        BlingLog.objects.create(
            tipo='nfe',
            pedido=pedido,
            sucesso=False,
            payload_enviado={'bling_pedido_id': pedido.bling_pedido_id},
            resposta={},
            erro=f'Erro inesperado: {exc}',
        )
        return False

    nfe_id  = str(resposta.get('data', {}).get('id', ''))
    nfe_chave = resposta.get('data', {}).get('chaveAcesso', '')

    BlingLog.objects.create(
        tipo='nfe',
        pedido=pedido,
        sucesso=True,
        payload_enviado={'bling_pedido_id': pedido.bling_pedido_id},
        resposta=resposta,
    )

    if nfe_id:
        pedido.bling_nfe_id = nfe_id
        pedido.nfe_chave    = nfe_chave or ''
        pedido.save(update_fields=['bling_nfe_id', 'nfe_chave', 'atualizado_em'])
        logger.info('NF-e emitida para pedido %s: nfe_id=%s', pedido.numero, nfe_id)

    return True


# ── Payload ───────────────────────────────────────────────────────────────────

def _montar_payload_pedido(pedido) -> dict:
    """Constrói o payload JSON para criar um Pedido de Venda no Bling API v3."""
    hoje     = date.today().isoformat()
    prevista = (date.today() + timedelta(days=7)).isoformat()

    itens = []
    for item in pedido.itens.select_related('produto').all():
        itens.append({
            'codigo':    item.sku or item.produto.sku or '',
            'descricao': item.nome_produto + (f' — {item.variacao_desc}' if item.variacao_desc else ''),
            'quantidade': item.quantidade,
            'valor':      float(item.preco_unitario),
            'desconto':   0,
            'unidade':   'UN',
        })

    forma_map = {
        'pix':            'PIX',
        'cartao_credito': f'Cartão de Crédito {pedido.parcelas}x',
        'boleto':         'Boleto',
    }
    obs_pagamento = forma_map.get(pedido.forma_pagamento, pedido.get_forma_pagamento_display())

    payload = {
        'numero':              pedido.numero,
        'numeroLoja':          pedido.numero,
        'data':                hoje,
        'dataSaida':           hoje,
        'dataPrevista':        prevista,
        'total':               float(pedido.total),
        'desconto':            float(pedido.desconto),
        'observacoes':         pedido.observacao_cliente or '',
        'observacaoInterna':   pedido.observacao_interna or '',
        'situacao':            {'id': SITUACAO_APROVADO},
        'contato': {
            'nome':       pedido.nome_completo,
            'tipoPessoa': 'F',
            'cpfCnpj':    pedido.cpf,
            'email':      pedido.email,
            'telefone':   pedido.telefone or '',
            'enderecos': [
                {
                    'geral': {
                        'endereco':    pedido.logradouro,
                        'numero':      pedido.numero_entrega,
                        'complemento': pedido.complemento or '',
                        'bairro':      pedido.bairro,
                        'cep':         pedido.cep_entrega,
                        'municipio':   pedido.cidade,
                        'uf':          pedido.estado,
                    }
                }
            ],
        },
        'itens': itens,
        'parcelas': [
            {
                'dataVencimento': hoje,
                'valor':          float(pedido.total),
                'observacoes':    obs_pagamento,
            }
        ],
        'transporte': {
            'fretePorConta': 1,
            'frete':         float(pedido.frete),
            'transportadora': {'id': 0},
        },
    }

    return payload
