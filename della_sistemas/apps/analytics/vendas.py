"""Regra unica de "o que conta como venda" no analytics do site.

O evento `pedido_finalizado` e gravado pelo site_della na CRIACAO do pedido.
Sozinho ele conta como venda um PIX que foi gerado e nunca pago, ou um pedido
depois cancelado. Aqui o numero do pedido do evento e cruzado com o status real
em `pedidos_pedido` (espelho `PedidoSite`):

- pago      -> conta como venda / receita
- aguardando pagamento -> nao conta; aparece separado como "aguardando pagamento"
- cancelado / estornado -> nao conta em lugar nenhum

Os eventos de `pedido_finalizado` vem em duas formas:
- total do pedido: `pedido_numero` preenchido e `produto_slug` vazio
- item do pedido:  `produto_slug` preenchido (com `pedido_numero` desde 2026-07-28)
"""

from django.db.models import Exists, OuterRef, Q

STATUS_PAGOS = (
    'pagamento_confirmado', 'em_separacao', 'pronto_retirada', 'enviado', 'entregue',
)
STATUS_AGUARDANDO = ('aguardando_pagamento',)


def _numeros(status):
    from apps.analytics.models import PedidoSite
    return PedidoSite.objects.filter(status__in=status).values('numero')


def numeros_pagos():
    return _numeros(STATUS_PAGOS)


def numeros_aguardando():
    return _numeros(STATUS_AGUARDANDO)


def eventos_pedidos(periodo, status=STATUS_PAGOS):
    """Eventos de TOTAL de pedido (1 por pedido) com o status pedido."""
    from apps.analytics.models import EventoSite
    return EventoSite.objects.filter(
        periodo, tipo='pedido_finalizado', produto_slug='',
        pedido_numero__in=_numeros(status),
    )


def eventos_itens(periodo):
    """Eventos de ITEM de pedidos pagos.

    Eventos gravados antes de 2026-07-28 nao tem `pedido_numero`; para esses o
    criterio e a sessao ter um pedido pago (fallback historico).
    """
    from apps.analytics.models import EventoSite
    sessao_pagou = Exists(
        EventoSite.objects.filter(
            sessao_id=OuterRef('sessao_id'), tipo='pedido_finalizado',
            pedido_numero__in=numeros_pagos(),
        )
    )
    return (
        EventoSite.objects
        .filter(periodo, tipo='pedido_finalizado', produto_slug__gt='')
        .annotate(sessao_pagou=sessao_pagou)
        .filter(Q(pedido_numero__in=numeros_pagos())
                | Q(pedido_numero='', sessao_pagou=True))
    )


def sessoes_com_venda_paga():
    """Subquery Exists para "esta sessao gerou uma venda paga"."""
    from apps.analytics.models import EventoSite
    return EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='pedido_finalizado',
        pedido_numero__in=numeros_pagos(),
    )


def sessoes_com_pedido_pendente():
    from apps.analytics.models import EventoSite
    return EventoSite.objects.filter(
        sessao=OuterRef('pk'), tipo='pedido_finalizado',
        pedido_numero__in=numeros_aguardando(),
    )


def ids_com_carrinho_liquido_positivo(session_ids):
    """Filtra, entre os ids de sessao dados, os que ainda tem algo no carrinho.

    `produto_removido` nao carrega quantidade/valor (so casa pelo nome do
    produto, ver apps/pedidos/carrinho.py:Carrinho.adicionar no site_della),
    entao uma remocao apaga a linha inteira daquele produto na sessao. Sem
    esse filtro, uma sessao que adicionou um item e o removeu antes de sair
    (carrinho esvaziado, nao abandonado) ainda contava como "carrinho
    abandonado" em qualquer lugar que so checasse Exists(produto_adicionado)
    -- aparecia com 0 itens e R$ 0,00 em "Carrinhos recentes".
    """
    from apps.analytics.models import EventoSite

    session_ids = list(session_ids)
    if not session_ids:
        return set()

    itens_por_sessao: dict = {}
    for evt in (
        EventoSite.objects
        .filter(sessao_id__in=session_ids, tipo__in=['produto_adicionado', 'produto_removido'])
        .values('sessao_id', 'tipo', 'produto_nome')
        .order_by('ocorrido_em')
    ):
        sid = evt['sessao_id']
        carrinho = itens_por_sessao.setdefault(sid, set())
        chave = evt['produto_nome'] or ''
        if evt['tipo'] == 'produto_adicionado':
            carrinho.add(chave)
        else:
            carrinho.discard(chave)

    return {sid for sid, itens in itens_por_sessao.items() if itens}
