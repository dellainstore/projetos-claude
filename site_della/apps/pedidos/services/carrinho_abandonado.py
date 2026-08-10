"""Regras de recuperacao de carrinho abandonado.

Um carrinho so e considerado RECUPERADO quando o pedido gerado a partir dele
foi efetivamente PAGO. Gerar o pedido (PIX emitido, cartao em analise) apenas
vincula o carrinho ao pedido e o mantem como "aguardando pagamento": se o
pagamento nunca acontecer (ou o pedido for cancelado), o carrinho volta a
contar como abandonado.

Antes (ate 2026-07-28) o checkout marcava `recuperado=True` na criacao do
pedido, entao um PIX gerado e nunca pago aparecia como carrinho recuperado.
"""

import logging

logger = logging.getLogger(__name__)

# Status em que o dinheiro ja entrou. Espelha STATUS_PAGOS de
# apps/core_utils/admin_views.py.
STATUS_PAGOS = (
    'pagamento_confirmado',
    'em_separacao',
    'pronto_retirada',
    'enviado',
    'entregue',
)


def pedido_esta_pago(pedido) -> bool:
    return pedido.status in STATUS_PAGOS


def vincular_pedido(pedido, request=None, email='') -> None:
    """Liga os carrinhos da cliente ao pedido recem-criado no checkout.

    Nao marca `recuperado`: quem faz isso e `sincronizar_recuperacao`, chamada
    pelo signal de `Pedido` sempre que o status muda.
    """
    try:
        from apps.pedidos.models import CarrinhoAbandonado

        pago = pedido_esta_pago(pedido)
        filtros = []

        cliente = getattr(pedido, 'cliente', None)
        if cliente is not None:
            filtros.append({'cliente': cliente})
        elif request is not None and getattr(request, 'user', None) is not None \
                and request.user.is_authenticated:
            filtros.append({'cliente': request.user})

        email_guest = email or (
            request.session.get('guest_checkout_email', '') if request is not None else ''
        )
        if email_guest and cliente is None:
            filtros.append({'cliente': None, 'email': email_guest, 'recuperado': False})

        for filtro in filtros:
            CarrinhoAbandonado.objects.filter(**filtro).update(
                pedido=pedido, recuperado=pago,
            )
    except Exception as exc:
        logger.debug('Nao foi possivel vincular carrinho ao pedido %s: %s',
                     getattr(pedido, 'numero', '?'), exc)


def sincronizar_recuperacao(pedido) -> None:
    """Reflete o status do pedido nos carrinhos vinculados a ele.

    Pago -> `recuperado=True`. Aguardando pagamento, cancelado ou estornado ->
    `recuperado=False` (volta para a lista de abandonados).
    """
    try:
        from apps.pedidos.models import CarrinhoAbandonado

        pago = pedido_esta_pago(pedido)
        (
            CarrinhoAbandonado.objects
            .filter(pedido=pedido)
            .exclude(recuperado=pago)
            .update(recuperado=pago)
        )
    except Exception as exc:
        logger.debug('Nao foi possivel sincronizar carrinho do pedido %s: %s',
                     getattr(pedido, 'numero', '?'), exc)
