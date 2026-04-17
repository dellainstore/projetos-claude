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

# ── Formas de pagamento ───────────────────────────────────────────────────────
FORMA_PAG_PIX    = 1194065
FORMA_PAG_CARTAO = 917629


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
    Monta a lista de parcelas conforme a forma de pagamento do pedido.
    - Pix: 1 parcela à vista
    - Cartão: N parcelas mensais
    """
    hoje      = date.today()
    total     = float(pedido.total)
    n         = max(1, int(pedido.parcelas or 1))
    forma_pag = pedido.forma_pagamento

    forma_id  = FORMA_PAG_PIX if forma_pag == 'pix' else FORMA_PAG_CARTAO
    obs       = 'Pix' if forma_pag == 'pix' else f'Cartão de Crédito {n}x'

    if n == 1:
        return [{
            'dataVencimento': hoje.isoformat(),
            'valor':          round(total, 2),
            'observacoes':    obs,
            'formaPagamento': {'id': forma_id},
        }]

    # Parcelado: divide igualmente, a última parcela absorve o centavo restante
    valor_parcela = round(total / n, 2)
    parcelas = []
    acumulado = 0.0
    for i in range(n):
        vencimento = (hoje + timedelta(days=30 * i)).isoformat()
        if i == n - 1:
            valor = round(total - acumulado, 2)
        else:
            valor = valor_parcela
            acumulado += valor
        parcelas.append({
            'dataVencimento': vencimento,
            'valor':          valor,
            'observacoes':    f'{obs} — parcela {i+1}/{n}',
            'formaPagamento': {'id': forma_id},
        })
    return parcelas


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

    obs_vendedor = ''
    if pedido.codigo_vendedor_id:
        obs_vendedor = f'Vendedora: {pedido.codigo_vendedor.nome}'

    payload = {
        'numero':            pedido.numero,
        'numeroLoja':        pedido.numero,
        'data':              hoje,
        'dataSaida':         hoje,
        'dataPrevista':      prevista,
        'total':             float(pedido.total),
        'desconto':          float(pedido.desconto),
        'observacoes':       pedido.observacao_cliente or '',
        'observacaoInterna': obs_vendedor,
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
