"""
Views de relatório para o Django Admin da Della Instore.
Acessível em: /painel/relatorio/
"""
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Sum, Count, Q
from django.utils import timezone


@staff_member_required
def relatorio(request):
    from apps.pedidos.models import Pedido, ItemPedido
    from apps.produtos.models import Produto, Variacao, Avaliacao
    from apps.usuarios.models import Cliente

    agora = timezone.now()
    inicio_30d = agora - timezone.timedelta(days=30)

    # Faturamento e pedidos confirmados dos últimos 30 dias
    qs_30d = Pedido.objects.filter(
        criado_em__gte=inicio_30d,
        status__in=('pagamento_confirmado', 'em_separacao', 'enviado', 'entregue'),
    )
    faturamento_30d = qs_30d.aggregate(total=Sum('total'))['total'] or Decimal('0')
    pedidos_confirmados = qs_30d.count()

    # Pedidos aguardando pagamento (todos os tempos)
    pedidos_aguardando = Pedido.objects.filter(status='aguardando_pagamento').count()

    # Totais gerais
    total_clientes = Cliente.objects.filter(is_active=True, is_staff=False).count()
    total_produtos = Produto.objects.filter(ativo=True).count()
    sem_estoque = Variacao.objects.filter(ativa=True, estoque=0).count()
    avaliacoes_pendentes = Avaliacao.objects.filter(aprovada=False).count()

    # Pedidos por status
    STATUS_LABELS = dict(Pedido.STATUS)
    pedidos_por_status = []
    for status_key, label in Pedido.STATUS:
        agg = Pedido.objects.filter(status=status_key).aggregate(
            quantidade=Count('id'), total=Sum('total')
        )
        if agg['quantidade']:
            pedidos_por_status.append({
                'label': label,
                'quantidade': agg['quantidade'],
                'total': _fmt(agg['total'] or Decimal('0')),
            })

    # Top 10 produtos mais vendidos
    top_produtos = (
        ItemPedido.objects
        .filter(pedido__status__in=('pagamento_confirmado', 'em_separacao', 'enviado', 'entregue'))
        .values('produto__id', 'produto__nome')
        .annotate(total_qty=Sum('quantidade'), receita=Sum('subtotal'))
        .order_by('-total_qty')[:10]
    )
    top_produtos = [
        {**p, 'receita': _fmt(p['receita'] or Decimal('0'))}
        for p in top_produtos
    ]

    # Estoque crítico (variações ativas com 0 a 4 unidades)
    estoque_critico = (
        Variacao.objects
        .filter(ativa=True, estoque__lte=4)
        .select_related('produto')
        .order_by('estoque', 'produto__nome')[:50]
    )

    context = {
        'title': 'Relatório Geral',
        'faturamento_30d': _fmt(faturamento_30d),
        'pedidos_confirmados': pedidos_confirmados,
        'pedidos_aguardando': pedidos_aguardando,
        'total_clientes': total_clientes,
        'total_produtos': total_produtos,
        'sem_estoque': sem_estoque,
        'avaliacoes_pendentes': avaliacoes_pendentes,
        'pedidos_por_status': pedidos_por_status,
        'top_produtos': top_produtos,
        'estoque_critico': estoque_critico,
    }
    return render(request, 'admin/relatorio.html', context)


def _fmt(valor):
    """Formata Decimal no padrão brasileiro: 1.234,56"""
    return f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
