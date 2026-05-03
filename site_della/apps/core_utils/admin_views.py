"""
Views de relatório para o Django Admin da Della Instore.
Acessível em: /painel/relatorio/
"""
from decimal import Decimal

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.db.models import Sum, Count
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


@staff_member_required
def dashboard_pedidos(request):
    from apps.pedidos.models import Pedido, ItemPedido, HistoricoPedido

    dias_opcoes = [1, 7, 15, 30, 60, 90]
    try:
        dias = int(request.GET.get('dias', 7))
    except (TypeError, ValueError):
        dias = 7
    if dias not in dias_opcoes:
        dias = 7

    agora = timezone.now()
    inicio_periodo = agora - timezone.timedelta(days=dias)
    status_validos = ('pagamento_confirmado', 'em_separacao', 'enviado', 'entregue')

    pedidos_a_enviar = Pedido.objects.filter(
        status__in=('pagamento_confirmado', 'em_separacao'),
    ).count()

    pedidos_periodo = Pedido.objects.filter(
        criado_em__gte=inicio_periodo,
        status__in=status_validos,
    )

    historico_enviados = (
        HistoricoPedido.objects
        .filter(criado_em__gte=inicio_periodo, status_novo='enviado')
        .values('pedido_id')
        .distinct()
    )

    faturamento_periodo = pedidos_periodo.aggregate(total=Sum('total'))['total'] or Decimal('0')
    clientes_periodo = (
        pedidos_periodo.exclude(email='')
        .values('email')
        .distinct()
        .count()
    )
    sku_vendidos_periodo = (
        ItemPedido.objects
        .filter(pedido__in=pedidos_periodo)
        .aggregate(total=Sum('quantidade'))['total'] or 0
    )

    enviados_recentes = (
        Pedido.objects
        .filter(id__in=historico_enviados.values('pedido_id'))
        .order_by('-atualizado_em')[:10]
    )

    pedidos_para_envio = (
        Pedido.objects
        .filter(status__in=('pagamento_confirmado', 'em_separacao'))
        .order_by('criado_em')[:10]
    )

    context = {
        'title': 'Dashboard de Pedidos',
        'dias': dias,
        'dias_opcoes': dias_opcoes,
        'pedidos_a_enviar': pedidos_a_enviar,
        'pedidos_enviados': historico_enviados.count(),
        'faturamento_periodo': _fmt(faturamento_periodo),
        'clientes_periodo': clientes_periodo,
        'sku_vendidos_periodo': sku_vendidos_periodo,
        'pedidos_para_envio': pedidos_para_envio,
        'enviados_recentes': enviados_recentes,
    }
    return render(request, 'admin/dashboard_pedidos.html', context)


@staff_member_required
def instagram_refresh(request):
    """
    Limpa o cache do Instagram e força nova busca na próxima visita à homepage.
    Acessível em: /painel/instagram/refresh/
    """
    from apps.produtos.instagram import limpar_cache_instagram, buscar_posts_instagram
    from django.contrib import messages
    from django.shortcuts import redirect

    limpar_cache_instagram()

    # Tenta buscar imediatamente para validar o token
    posts = buscar_posts_instagram(limit=9)

    if posts:
        messages.success(request, f'Feed do Instagram atualizado: {len(posts)} post(s) carregados.')
    else:
        messages.warning(
            request,
            'Cache limpo, mas nenhum post foi carregado. '
            'Verifique se INSTAGRAM_ACCESS_TOKEN está configurado e válido no .env.'
        )

    return redirect('/painel/')


def _fmt(valor):
    """Formata Decimal no padrão brasileiro: 1.234,56"""
    return f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
