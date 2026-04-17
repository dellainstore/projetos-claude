"""
Serviços de alto nível para integração com o Bling.

Funções principais:
    enviar_pedido_bling(pedido)              → bool
    atualizar_situacao_bling(pedido, id)     → bool
    restaurar_estoque_pedido(pedido)         → None
    emitir_nfe_bling(pedido)                 → bool
"""

import logging
from datetime import date, timedelta

from .api import BlingAPI, BlingAPIError
from .models import BlingLog

logger = logging.getLogger(__name__)


# ── Situações do Bling ────────────────────────────────────────────────────────
SITUACAO_EM_ANDAMENTO_SITE = 6      # reserva estoque, sem financeiro
SITUACAO_ATENDIDO_SITE     = 18723  # gera estoque e contas a pagar
SITUACAO_CANCELADO         = 12

# ── Loja e unidade de negócio ─────────────────────────────────────────────────
LOJA_ID            = 204582763   # Show Room - D'ella
UNIDADE_NEGOCIO_ID = 1484433     # Matriz

# ── Vendedores (nome em maiúsculas → bling_vendedor_id) ───────────────────────
VENDEDOR_PADRAO_ID = 7616577942   # CRISLAINY SILVERIO GIACOMELLI
VENDEDORES_BLING = {
    'TINA DIAS':                     7613793453,
    'CRISLAINY SILVERIO GIACOMELLI': 7616577942,
    'MICHELLE ALVES FERNANDES':      15205612892,
    'SARA OLIVEIRA':                 15596882226,
}

# ── Formas de pagamento (PAG SEGURO Via Link + PIX) ──────────────────────────
FORMA_PAG_PIX = 1194065        # TED/DOC/TRANSF./PIX (À Vista)

# PAG SEGURO Cartão de Crédito Via Link por número de parcelas
FORMA_PAG_CARTAO = {
    1: 929656,    # À Vista
    2: 2103282,   # 2x
    3: 7128327,   # 3x
    4: 7128329,   # 4x
    5: 7128331,   # 5x
}


# ── Envio de pedido ───────────────────────────────────────────────────────────

def enviar_pedido_bling(pedido) -> bool:
    """
    Envia pedido ao Bling como "Em andamento - Site".
    Cria reserva de estoque no Bling, sem gerar financeiro.
    Retorna True em caso de sucesso, False em caso de falha.
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
            tipo='pedido', pedido=pedido, sucesso=False,
            payload_enviado=_redact_payload_pii(payload), resposta={}, erro=str(exc),
        )
        logger.error('Bling: erro ao enviar pedido %s: %s', pedido.numero, exc)
        return False
    except Exception as exc:
        BlingLog.objects.create(
            tipo='pedido', pedido=pedido, sucesso=False,
            payload_enviado=_redact_payload_pii(payload), resposta={},
            erro=f'Erro inesperado: {exc}',
        )
        logger.error('Bling: exceção inesperada no pedido %s: %s', pedido.numero, exc)
        return False

    bling_id = str(resposta.get('data', {}).get('id', ''))

    BlingLog.objects.create(
        tipo='pedido', pedido=pedido, sucesso=True,
        payload_enviado=_redact_payload_pii(payload), resposta=resposta,
    )

    if bling_id:
        pedido.bling_pedido_id = bling_id
        pedido.save(update_fields=['bling_pedido_id', 'atualizado_em'])
        logger.info('Pedido %s enviado ao Bling (id=%s)', pedido.numero, bling_id)

    return True


# ── Atualização de situação ───────────────────────────────────────────────────

def atualizar_situacao_bling(pedido, situacao_id: int) -> bool:
    """
    Atualiza a situação do pedido no Bling.

    Uso típico:
        - Pagamento confirmado → SITUACAO_ATENDIDO_SITE (18723)
        - Pedido cancelado     → SITUACAO_CANCELADO (12)
    """
    if not pedido.bling_pedido_id:
        logger.warning('Bling: pedido %s sem bling_pedido_id — situação não atualizada', pedido.numero)
        return False

    try:
        api = BlingAPI()
        api.atualizar_situacao_pedido(pedido.bling_pedido_id, situacao_id)
        logger.info('Bling: pedido %s → situacao_id=%s', pedido.numero, situacao_id)
        return True
    except BlingAPIError as exc:
        logger.error('Bling: erro ao atualizar situação pedido %s: %s', pedido.numero, exc)
        return False
    except Exception as exc:
        logger.error('Bling: exceção ao atualizar situação pedido %s: %s', pedido.numero, exc)
        return False


# ── Restauração de estoque ────────────────────────────────────────────────────

def restaurar_estoque_pedido(pedido) -> None:
    """
    Devolve ao estoque do site as quantidades dos itens de um pedido cancelado.
    Chamado antes de marcar o pedido como cancelado.
    """
    from django.db.models import F
    from apps.produtos.models import Variacao

    for item in pedido.itens.select_related('variacao').all():
        if item.variacao_id:
            Variacao.objects.filter(pk=item.variacao_id).update(
                estoque=F('estoque') + item.quantidade
            )
            logger.info(
                'Estoque restaurado: variação %s +%s (pedido %s)',
                item.variacao_id, item.quantidade, pedido.numero,
            )


# ── NF-e ──────────────────────────────────────────────────────────────────────

def emitir_nfe_bling(pedido) -> bool:
    """
    Emite NF-e para um pedido a partir do pedido já criado no Bling.
    Pré-requisito: pedido.bling_pedido_id deve estar preenchido.
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
            tipo='nfe', pedido=pedido, sucesso=False,
            payload_enviado={'bling_pedido_id': pedido.bling_pedido_id}, resposta={}, erro=str(exc),
        )
        logger.error('Bling: erro ao emitir NF-e do pedido %s: %s', pedido.numero, exc)
        return False
    except Exception as exc:
        BlingLog.objects.create(
            tipo='nfe', pedido=pedido, sucesso=False,
            payload_enviado={'bling_pedido_id': pedido.bling_pedido_id}, resposta={},
            erro=f'Erro inesperado: {exc}',
        )
        return False

    nfe_id    = str(resposta.get('data', {}).get('id', ''))
    nfe_chave = resposta.get('data', {}).get('chaveAcesso', '')

    BlingLog.objects.create(
        tipo='nfe', pedido=pedido, sucesso=True,
        payload_enviado={'bling_pedido_id': pedido.bling_pedido_id}, resposta=resposta,
    )

    if nfe_id:
        pedido.bling_nfe_id = nfe_id
        pedido.nfe_chave    = nfe_chave or ''
        pedido.save(update_fields=['bling_nfe_id', 'nfe_chave', 'atualizado_em'])
        logger.info('NF-e emitida para pedido %s: nfe_id=%s', pedido.numero, nfe_id)

    return True


# ── Redação de PII para logs ──────────────────────────────────────────────────

def _redact_payload_pii(payload: dict) -> dict:
    import copy
    redacted = copy.deepcopy(payload)
    contato = redacted.get('contato')
    if isinstance(contato, dict):
        for campo in ('cpfCnpj', 'email', 'telefone', 'enderecos', 'nome'):
            if campo in contato:
                contato[campo] = '[REDACTED]'
    return redacted


# ── Payload ───────────────────────────────────────────────────────────────────

def _resolver_vendedor_id(pedido) -> int:
    """
    Retorna o bling_vendedor_id correspondente ao código de vendedor do pedido.
    Se não houver código ou o nome não for encontrado, usa CRISLAINY (padrão).
    """
    if pedido.codigo_vendedor_id:
        nome = (pedido.codigo_vendedor.nome or '').upper().strip()
        vendedor_id = VENDEDORES_BLING.get(nome)
        if vendedor_id:
            return vendedor_id
        logger.warning('Bling: vendedor "%s" não mapeado — usando padrão (Crislainy)', nome)
    return VENDEDOR_PADRAO_ID


def _montar_parcelas(pedido) -> list:
    """
    Sempre 1 parcela (antecipação — recebimento à vista independente do parcelamento).
    - Pix: forma TED/DOC/TRANSF./PIX
    - Cartão: forma PAG SEGURO Via Link pelo nº de parcelas; autorização PagSeguro na observação
    """
    hoje      = date.today()
    total     = float(pedido.total)
    n         = max(1, int(pedido.parcelas or 1))
    forma_pag = pedido.forma_pagamento

    if forma_pag == 'pix':
        return [{
            'dataVencimento': hoje.isoformat(),
            'valor':          round(total, 2),
            'observacoes':    'Pix',
            'formaPagamento': {'id': FORMA_PAG_PIX},
        }]

    # Cartão — forma de pagamento pelo nº de parcelas (máx. 5)
    n_clamped = min(n, 5)
    forma_id  = FORMA_PAG_CARTAO.get(n_clamped, FORMA_PAG_CARTAO[1])

    label = 'À Vista' if n == 1 else f'{n}x'
    obs   = f'Cartão de Crédito {label}'
    if pedido.gateway_id:
        obs += f' — Autorização: {pedido.gateway_id}'

    return [{
        'dataVencimento': hoje.isoformat(),
        'valor':          round(total, 2),
        'observacoes':    obs,
        'formaPagamento': {'id': forma_id},
    }]


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
            'unidade':   'PC',
        })

    payload = {
        'numero':            pedido.numero,
        'numeroLoja':        pedido.numero,
        'data':              hoje,
        'dataSaida':         hoje,
        'dataPrevista':      prevista,
        'total':             float(pedido.total),
        'desconto':          float(pedido.desconto),
        'observacoes':       pedido.observacao_cliente or '',
        'situacao':          {'id': SITUACAO_EM_ANDAMENTO_SITE},
        'loja': {
            'id': LOJA_ID,
            'unidadeNegocio': {'id': UNIDADE_NEGOCIO_ID},
        },
        'vendedor': {'id': _resolver_vendedor_id(pedido)},
        'contato': {
            'nome':       pedido.nome_completo,
            'tipoPessoa': 'F',
            'cpfCnpj':    pedido.cpf,
            'email':      pedido.email,
            'telefone':   pedido.telefone or '',
            'enderecos': [{
                'geral': {
                    'endereco':    pedido.logradouro,
                    'numero':      pedido.numero_entrega,
                    'complemento': pedido.complemento or '',
                    'bairro':      pedido.bairro,
                    'cep':         pedido.cep_entrega,
                    'municipio':   pedido.cidade,
                    'uf':          pedido.estado,
                }
            }],
        },
        'itens':    itens,
        'parcelas': _montar_parcelas(pedido),
        'transporte': {
            'fretePorConta': 1,
            'frete':         float(pedido.frete),
            'transportadora': {'id': 0},
        },
    }

    return payload
