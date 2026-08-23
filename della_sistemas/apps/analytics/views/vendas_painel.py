"""Painel Vendas: quanto entrou, veio de onde e do que.

Par do painel Visitas. Aqui a unidade e o pedido pago e a fonte da verdade e o
espelho `PedidoSite`, nao o evento de analytics (ver apps/analytics/faturamento.py).
"""

import csv

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required

from .dashboard import _db_disponivel, _resolver_periodo


@perm_required("analytics.ver")
def vendas(request: HttpRequest) -> HttpResponse:
    if not _db_disponivel():
        return render(request, 'analytics/vendas.html',
                      {'sem_config': True, 'filtro': '7d'})

    filtro, inicio, fim, de_val, ate_val = _resolver_periodo(request)

    try:
        from apps.analytics import faturamento as F
        from apps.analytics.views.dashboard import _calcular_carrinhos_recentes
        from apps.analytics.vendas import eventos_itens
        from django.db.models import Count, Q, Sum

        resumo     = F.resumo(inicio, fim)
        origens    = F.por_origem(inicio, fim)
        campanhas  = F.por_campanha(inicio, fim)
        qualidade  = F.qualidade_atribuicao(inicio, fim)
        clientes   = F.novos_x_recorrentes(inicio, fim)
        pedidos    = F.ultimos_pedidos(inicio, fim)
        carrinhos  = _calcular_carrinhos_recentes(inicio, fim)

        mais_vendidos = list(
            eventos_itens(Q(ocorrido_em__range=(inicio, fim)))
            .values('produto_slug', 'produto_nome')
            .annotate(total=Count('id'), receita=Sum('valor_total'))
            .order_by('-total')[:10]
        )
        db_ok = True
    except Exception:
        resumo = {'vendas': 0, 'receita': 0, 'ticket': 0, 'itens': 0,
                  'aguardando': 0, 'aguardando_valor': 0}
        origens = campanhas = pedidos = carrinhos = mais_vendidos = []
        qualidade = {'com_origem': 0, 'sem_origem': 0, 'receita_com': 0,
                     'receita_sem': 0, 'pct': 0}
        clientes = {'novos': 0, 'recorrentes': 0}
        db_ok = False

    return render(request, 'analytics/vendas.html', {
        'filtro': filtro, 'de_val': de_val, 'ate_val': ate_val,
        'resumo': resumo, 'origens': origens, 'campanhas': campanhas,
        'qualidade': qualidade, 'clientes': clientes, 'pedidos': pedidos,
        'carrinhos': carrinhos, 'mais_vendidos': mais_vendidos,
        'db_ok': db_ok,
    })


@perm_required("analytics.ver")
def vendas_export(request: HttpRequest) -> HttpResponse:
    """Exporta origens ou campanhas do periodo em CSV."""
    if not _db_disponivel():
        return HttpResponse('Banco do site nao configurado.', status=503)

    from apps.analytics import faturamento as F

    _, inicio, fim, _, _ = _resolver_periodo(request)
    tipo = request.GET.get('tipo', 'origem')

    def _num(valor):
        """Decimal no formato que o Excel em portugues entende como numero."""
        return f'{valor:.2f}'.replace('.', ',')

    if tipo == 'campanha':
        cabecalho = ['Campanha', 'Canal', 'Vendas', 'Faturamento', 'Ticket medio']
        linhas = [
            [c['campanha'], c['origem'], c['vendas'], _num(c['receita']), _num(c['ticket'])]
            for c in F.por_campanha(inicio, fim)
        ]
        nome = 'campanhas'
    else:
        cabecalho = ['Canal', 'Vendas', 'Faturamento', 'Ticket medio', '% do faturamento']
        linhas = [
            [o['origem'], o['vendas'], _num(o['receita']), _num(o['ticket']), o['pct']]
            for o in F.por_origem(inicio, fim)
        ]
        nome = 'origens'

    arquivo = f'vendas_{nome}_{inicio:%Y%m%d}-{fim:%Y%m%d}.csv'
    # charset=utf-8 (nao utf-8-sig): o Django codifica CADA write com o charset
    # da resposta, entao utf-8-sig repetiria o BOM em toda linha. O BOM vai uma
    # vez so, em bytes, e sem ele o Excel em portugues abre os acentos errados.
    resposta = HttpResponse(content_type='text/csv; charset=utf-8')
    resposta['Content-Disposition'] = f'attachment; filename="{arquivo}"'
    resposta.write(b'\xef\xbb\xbf')
    escritor = csv.writer(resposta, delimiter=';')
    escritor.writerow(cabecalho)
    escritor.writerows(linhas)
    return resposta
