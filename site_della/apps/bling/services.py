"""
Serviços de alto nível para integração com o Bling.

Funções principais:
    enviar_pedido_bling(pedido)              → bool
    atualizar_situacao_bling(pedido, id)     → bool
    restaurar_estoque_pedido(pedido)         → None
    emitir_nfe_bling(pedido)                 → bool
"""

import logging
from datetime import date
from functools import lru_cache

from .api import BlingAPI, BlingAPIError
from .models import BlingLog

logger = logging.getLogger(__name__)

OBSERVACAO_INTERNA_PADRAO = (
    "EMPRESA OPTANTE PELO SIMPLES NACIONAL, NAO GERA DIREITO AO CREDITO DE ISS, ICMS E IPI.\n\n"
    "Banco Santander\n"
    "Ag 2200\n"
    "Cc 1300 2879 8\n"
    "Adriana Simoes Machado Confeccoes Me\n"
    "CNPJ 29 049 870 0001 37 - PIX"
)


# ── Mapeamento serviço Melhor Envio → transportadora + modalidade Bling ──────
# Bling API v3 — modalidade no objeto volume: 1=PAC, 2=SEDEX
# Nome do objeto de postagem (campo textual em transporte.volumes[].servico)
MELHOR_ENVIO_SERVICOS = {
    '1':  {'nome_servico': 'PAC',   'modalidade': 1},   # Correios - PAC
    '2':  {'nome_servico': 'SEDEX', 'modalidade': 2},   # Correios - SEDEX
}
# Nome que identifica a logística no Bling (cadastro de transportadora)
LOGISTICA_NOME_PADRAO = 'Melhor Envio - Correios'
TRANSPORTADORA_NOME   = 'CORREIOS'


# ── Situações do Bling ────────────────────────────────────────────────────────
# IDs verificados via GET /pedidos/vendas na conta D'ELLA:
#   754756 = Em andamento - Site  (custom — pedido 9638)
#   18723  = Atendido - Site      (custom — a confirmar)
#   15762  = situação custom antiga (pedidos 9634/9635)
#   15     = Em andamento         (padrão Bling)
#   9      = Atendido             (padrão Bling)
#   12     = Cancelado            (padrão Bling)
SITUACAO_EM_ANDAMENTO_SITE = 754756  # Em andamento - Site (custom D'ELLA)
SITUACAO_ATENDIDO_SITE     = 18723   # Atendido - Site (custom D'ELLA)
SITUACAO_CANCELADO         = 12      # Cancelado (padrão Bling)

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
    Antes de criar, busca o contato por CPF e depois por telefone para evitar duplicatas.
    Retorna True em caso de sucesso, False em caso de falha.
    """
    if pedido.bling_pedido_id:
        logger.info('Pedido %s já enviado ao Bling (id=%s)', pedido.numero, pedido.bling_pedido_id)
        return True

    try:
        api = BlingAPI()
    except BlingAPIError as exc:
        BlingLog.objects.create(
            tipo='pedido', pedido=pedido, sucesso=False,
            payload_enviado={}, resposta={}, erro=str(exc),
        )
        logger.error('Bling: token indisponível para pedido %s: %s', pedido.numero, exc)
        return False

    contato = _resolver_contato_bling(pedido, api)
    payload = _montar_payload_pedido(pedido, contato)

    try:
        resposta = api.criar_pedido_venda(payload)
    except BlingAPIError as exc:
        BlingLog.objects.create(
            tipo='pedido', pedido=pedido, sucesso=False,
            payload_enviado=_redact_payload_pii(payload),
            resposta=getattr(exc, 'data', {}) or {},
            erro=str(exc),
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

        # Garantia idempotente: força "Em andamento - Site" caso o Bling tenha
        # ignorado o campo situacao no POST de criação. Se já estiver na situação
        # correta, o Bling responde 400 com code 50 ("mesma situação") — ignoramos.
        try:
            api.atualizar_situacao_pedido(bling_id, SITUACAO_EM_ANDAMENTO_SITE)
            logger.info('Bling: pedido %s → Em andamento - Site', pedido.numero)
        except BlingAPIError as exc:
            campos = (getattr(exc, 'data', {}) or {}).get('error', {}).get('fields', []) or []
            if any(f.get('code') == 50 for f in campos):
                logger.info('Bling: pedido %s já estava em Em andamento - Site', pedido.numero)
            else:
                logger.warning('Bling: falha ao forçar situação inicial no pedido %s: %s',
                               pedido.numero, exc)

    return True


# ── Atualização de situação ───────────────────────────────────────────────────

def atualizar_situacao_bling(pedido, situacao_id: int) -> bool:
    """
    Atualiza a situação do pedido no Bling.

    Uso típico:
        - Pagamento confirmado → SITUACAO_ATENDIDO_SITE (18723)
        - Pedido cancelado     → SITUACAO_CANCELADO (12)

    Quando a nova situação é ATENDIDO, a data do pedido também é atualizada
    para hoje — reflete a data real do pagamento (pedido pode ter sido criado
    em outro dia e pago só hoje).
    """
    if not pedido.bling_pedido_id:
        logger.warning('Bling: pedido %s sem bling_pedido_id — situação não atualizada', pedido.numero)
        return False

    try:
        api = BlingAPI()
    except BlingAPIError as exc:
        logger.error('Bling: token indisponível para atualizar pedido %s: %s', pedido.numero, exc)
        return False

    # Atualiza data do pedido antes de marcar como atendido
    if situacao_id == SITUACAO_ATENDIDO_SITE:
        _atualizar_data_pedido_bling(pedido, api)

    try:
        api.atualizar_situacao_pedido(pedido.bling_pedido_id, situacao_id)
        logger.info('Bling: pedido %s → situacao_id=%s', pedido.numero, situacao_id)
        return True
    except BlingAPIError as exc:
        logger.error('Bling: erro ao atualizar situação pedido %s: %s', pedido.numero, exc)
        return False
    except Exception as exc:
        logger.error('Bling: exceção ao atualizar situação pedido %s: %s', pedido.numero, exc)
        return False


def _atualizar_data_pedido_bling(pedido, api) -> bool:
    """
    Atualiza a data e dataSaida do pedido no Bling para hoje.
    Usa GET+PUT (Bling v3 não tem PATCH parcial para /pedidos/vendas).
    Falha silenciosa: se algo der errado, só loga e não interrompe o fluxo.
    """
    try:
        resp = api.consultar_pedido_venda(pedido.bling_pedido_id)
    except BlingAPIError as exc:
        logger.warning('Bling: não consegui consultar pedido %s p/ atualizar data: %s',
                       pedido.numero, exc)
        return False

    atual = resp.get('data') or {}
    if not atual:
        return False

    hoje = date.today().isoformat()
    atual['data']      = hoje
    atual['dataSaida'] = hoje

    try:
        api.atualizar_pedido_venda(pedido.bling_pedido_id, atual)
        logger.info('Bling: data do pedido %s atualizada para %s', pedido.numero, hoje)
        return True
    except BlingAPIError as exc:
        logger.warning('Bling: falha ao atualizar data do pedido %s: %s', pedido.numero, exc)
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


# ── Resolução de contato (evita duplicatas no Bling) ─────────────────────────

def _dados_contato_pedido(pedido) -> dict:
    """Dados atuais do comprador formatados para o Bling (create/update)."""
    return {
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
    }


def _resolver_contato_bling(pedido, api) -> dict:
    """
    Busca contato existente no Bling pelo CPF do pedido (match exato).
    - Se encontrar um contato com o mesmo CPF → retorna {'id': X} e o Bling
      usa os dados cadastrais desse contato no pedido.
    - Se NÃO encontrar → retorna os dados completos do pedido para o Bling
      criar um contato novo.

    Obs.: não fazemos busca por telefone/nome nem PUT no contato existente —
    a busca por CPF é autoritativa e qualquer "atualização" poderia sobrescrever
    dados corretos por informação digitada no checkout.
    """
    if pedido.cpf:
        contato_id = api.buscar_contato_por_cpf(pedido.cpf)
        if contato_id:
            logger.info('Bling: contato encontrado por CPF (id=%s) — pedido %s',
                        contato_id, pedido.numero)
            return {'id': contato_id}

    logger.info('Bling: contato não encontrado por CPF — será criado no pedido %s',
                pedido.numero)
    return _dados_contato_pedido(pedido)


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


def _montar_observacoes_internas(pedido) -> str:
    """Garante a mensagem operacional/fiscal fixa em todos os pedidos do Bling."""
    observacao_extra = (pedido.observacao_interna or '').strip()
    if not observacao_extra:
        return OBSERVACAO_INTERNA_PADRAO
    if OBSERVACAO_INTERNA_PADRAO in observacao_extra:
        return observacao_extra
    return f"{OBSERVACAO_INTERNA_PADRAO}\n\n{observacao_extra}"


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


@lru_cache(maxsize=1)
def _obter_logistica_melhor_envio() -> dict:
    """
    Resolve a logística "Melhor Envio - Correios" e seus serviços reais na conta.

    O Bling ignora parcialmente payloads com apenas nomes textuais em alguns campos.
    Por isso buscamos os IDs cadastrados na própria conta e os usamos no pedido.
    """
    api = BlingAPI()
    resposta = api.listar_logisticas()

    for item in resposta.get('data', []) or []:
        if (item.get('descricao') or '').strip() != LOGISTICA_NOME_PADRAO:
            continue

        logistica_id = item.get('id')
        detalhes = api.consultar_logistica(logistica_id).get('data', {}) if logistica_id else {}
        servicos = detalhes.get('servicos') or item.get('servicos') or []

        servicos_por_codigo = {}
        for servico in servicos:
            codigo = str(servico.get('codigo') or '').strip()
            descricao = (servico.get('descricao') or '').strip().upper()
            transportador_id = servico.get('transportador', {}).get('id')
            if codigo:
                servicos_por_codigo[codigo] = {
                    'id': servico.get('id'),
                    'codigo': codigo,
                    'descricao': descricao,
                    'transportador_id': transportador_id,
                }
            if descricao == 'PAC':
                servicos_por_codigo.setdefault('1', {
                    'id': servico.get('id'),
                    'codigo': codigo,
                    'descricao': descricao,
                    'transportador_id': transportador_id,
                })
            elif descricao == 'SEDEX':
                servicos_por_codigo.setdefault('2', {
                    'id': servico.get('id'),
                    'codigo': codigo,
                    'descricao': descricao,
                    'transportador_id': transportador_id,
                })

        return {
            'id': logistica_id,
            'descricao': item.get('descricao') or LOGISTICA_NOME_PADRAO,
            'integracao_id': detalhes.get('integracao', {}).get('id') or item.get('integracao', {}).get('id'),
            'servicos': servicos_por_codigo,
        }

    raise BlingAPIError(404, {'error': {'description': f'Logística "{LOGISTICA_NOME_PADRAO}" não encontrada na conta Bling.'}})


def _resolver_servico_logistico(pedido) -> dict:
    """
    Combina o serviço escolhido no checkout com os IDs reais da logística do Bling.
    """
    servico_id = (pedido.frete_servico_id or '').strip()
    info = dict(MELHOR_ENVIO_SERVICOS.get(servico_id, {}))

    try:
        logistica = _obter_logistica_melhor_envio()
    except BlingAPIError as exc:
        logger.warning('Bling: não foi possível resolver logística Melhor Envio para o pedido %s: %s',
                       pedido.numero, exc)
        return {
            'logistica_id': None,
            'logistica_nome': LOGISTICA_NOME_PADRAO,
            'integracao_id': None,
            'nome_servico': info.get('nome_servico') or (pedido.transportadora or 'PAC'),
            'modalidade': info.get('modalidade') or 1,
            'servico_logistico_id': None,
            'transportador_id': None,
            'transportador_nome': TRANSPORTADORA_NOME,
        }

    servico = logistica.get('servicos', {}).get(servico_id, {})
    nome_servico = (
        servico.get('descricao')
        or info.get('nome_servico')
        or (pedido.transportadora or 'PAC')
    )

    return {
        'logistica_id': logistica.get('id'),
        'logistica_nome': logistica.get('descricao') or LOGISTICA_NOME_PADRAO,
        'integracao_id': logistica.get('integracao_id'),
        'nome_servico': nome_servico,
        'modalidade': info.get('modalidade') or 1,
        'servico_logistico_id': servico.get('id'),
        'transportador_id': servico.get('transportador_id'),
        'transportador_nome': TRANSPORTADORA_NOME,
    }


def _montar_transporte(pedido) -> dict:
    """
    Monta o bloco transporte do payload Bling v3.
    - fretePorConta: 1=FOB (destinatário paga) | 0=CIF (remetente paga — frete grátis)
    - logistica: "Melhor Envio - Correios" para preencher o campo logística do Bling
    - volumes: peso e dimensões da caixa padrão D'ELLA
    """
    from apps.pagamentos.services.melhorenvio import DIMENSOES_PADRAO

    servico_logistico = _resolver_servico_logistico(pedido)
    nome_servico = servico_logistico['nome_servico']
    modalidade = servico_logistico['modalidade']
    quantidade_itens = sum(int(item.quantidade) for item in pedido.itens.all()) or 1

    # FOB quando cliente paga frete; CIF quando frete é gratuito (≥R$800 ou promoção)
    frete_valor = float(pedido.frete)
    frete_por_conta = 1 if frete_valor > 0 else 0
    peso_bruto = round(DIMENSOES_PADRAO['weight'] * quantidade_itens, 3)

    volume = {
        'servico':     nome_servico,
        'modalidade':  modalidade,
        'peso':        peso_bruto,
        'altura':      DIMENSOES_PADRAO['height'],
        'largura':     DIMENSOES_PADRAO['width'],
        'comprimento': DIMENSOES_PADRAO['length'],
    }
    if servico_logistico['servico_logistico_id']:
        volume['idServicoLogistico'] = servico_logistico['servico_logistico_id']
    if pedido.codigo_rastreio:
        volume['codigoRastreamento'] = pedido.codigo_rastreio

    transporte = {
        'fretePorConta':    frete_por_conta,
        'frete':            frete_valor,
        'quantidadeVolumes': 1,
        'pesoBruto':        peso_bruto,
        'transportador':    {'nome': servico_logistico['transportador_nome']},
        'logistica':        {
            'nome': servico_logistico['logistica_nome'],
        },
        'contato':          {'nome': servico_logistico['transportador_nome']},
        'etiqueta': {
            'nome':        pedido.nome_completo,
            'endereco':    pedido.logradouro,
            'numero':      pedido.numero_entrega,
            'complemento': pedido.complemento or '',
            'municipio':   pedido.cidade,
            'uf':          pedido.estado,
            'cep':         pedido.cep_entrega,
            'bairro':      pedido.bairro,
            'nomePais':    'Brasil',
        },
        'volumes': [volume],
    }
    if servico_logistico['logistica_id']:
        transporte['logistica']['id'] = servico_logistico['logistica_id']
    if servico_logistico['integracao_id']:
        transporte['logistica']['integracao'] = {'id': servico_logistico['integracao_id']}
    if servico_logistico['servico_logistico_id']:
        transporte['idServicoLogistico'] = servico_logistico['servico_logistico_id']
    if servico_logistico['transportador_id']:
        transporte['transportador']['id'] = servico_logistico['transportador_id']
        transporte['contato']['id'] = servico_logistico['transportador_id']

    return transporte


def _montar_payload_pedido(pedido, contato: dict) -> dict:
    """Constrói o payload JSON para criar um Pedido de Venda no Bling API v3."""
    hoje = date.today().isoformat()

    itens = []
    qs = pedido.itens.select_related(
        'produto', 'variacao', 'variacao__cor', 'variacao__tamanho'
    ).all()
    for item in qs:
        # Código Bling: deve bater com o campo "Código" do produto/variação no catálogo Bling.
        # item.sku é salvo no checkout como variacao.sku_variacao (ex: "4604") — fonte primária.
        # bling_variacao_id é o ID interno numérico do Bling e NÃO deve ser usado como codigo.
        codigo = item.sku or ''
        if not codigo and item.variacao_id and item.variacao:
            codigo = item.variacao.sku_variacao or ''
        if not codigo:
            codigo = item.produto.sku or ''

        # Descrição no formato Bling: NOME PRODUTO (COR) (TAMANHO)
        nome_bling = item.nome_produto.upper()
        if item.variacao_id and item.variacao:
            if item.variacao.cor_id and item.variacao.cor:
                nome_bling += f' ({item.variacao.cor.nome.upper()})'
            if item.variacao.tamanho_id and item.variacao.tamanho:
                nome_bling += f' ({item.variacao.tamanho.nome.upper()})'
        elif item.variacao_desc:
            # fallback: parse variacao_desc salvo ("Branco Polar / Tam. G")
            for parte in item.variacao_desc.split(' / '):
                if parte.startswith('Tam. '):
                    nome_bling += f' ({parte[5:].upper()})'
                else:
                    nome_bling += f' ({parte.upper()})'

        item_payload = {
            'descricao': nome_bling,
            'quantidade': item.quantidade,
            'valor':      float(item.preco_unitario),
            'desconto':   0,
            'unidade':   'PC',
        }
        if codigo:
            item_payload['codigo'] = codigo
        # Inclui o ID interno do Bling para vincular ao produto do catálogo.
        # Prioridade: bling_variacao_id da variação; fallback para bling_id do produto pai.
        bling_produto_id = None
        if item.variacao_id and item.variacao and item.variacao.bling_variacao_id:
            try:
                bling_produto_id = int(item.variacao.bling_variacao_id)
            except (ValueError, TypeError):
                pass
        if not bling_produto_id and item.produto and item.produto.bling_id:
            try:
                bling_produto_id = int(item.produto.bling_id)
            except (ValueError, TypeError):
                pass
        if bling_produto_id:
            item_payload['produto'] = {'id': bling_produto_id}
        itens.append(item_payload)

    payload = {
        # 'numero' é auto-incrementado pelo Bling (sequencial interno).
        # Enviá-lo causa colisão com pedidos antigos. Usamos 'numeroLoja' para
        # vincular ao número do site e localizar o pedido depois.
        'numeroLoja':        pedido.numero,
        'data':              hoje,
        'dataSaida':         hoje,
        'totalProdutos':     float(pedido.subtotal),
        'total':             float(pedido.total),
        'desconto':          float(pedido.desconto),
        'observacoes':       pedido.observacao_cliente or '',
        'observacoesInternas': _montar_observacoes_internas(pedido),
        'situacao':          {'id': SITUACAO_EM_ANDAMENTO_SITE},
        'loja': {
            'id': LOJA_ID,
            'unidadeNegocio': {'id': UNIDADE_NEGOCIO_ID},
        },
        'vendedor': {'id': _resolver_vendedor_id(pedido)},
        'contato':  contato,
        'itens':    itens,
        'parcelas': _montar_parcelas(pedido),
        'transporte': _montar_transporte(pedido),
    }

    return payload
