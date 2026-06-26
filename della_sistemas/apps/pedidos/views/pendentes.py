from datetime import date

from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.pedidos.models import PedidoBling
from apps.pedidos.services.situacoes import EM_ANDAMENTO_IDS

INICIO_2026 = date(2026, 1, 1)


@perm_required("pedidos.ver")
def view_pendentes(request):
    hoje = date.today()
    ids_filtro = list(EM_ANDAMENTO_IDS.keys())

    pedidos_qs = PedidoBling.objects.filter(
        situacao_id__in=ids_filtro,
        data_pedido__gte=INICIO_2026,
        is_permuta=False,
    ).order_by("-data_pedido", "-bling_id") if ids_filtro else PedidoBling.objects.none()

    linhas = []
    for p in pedidos_qs:
        dias = (hoje - p.data_pedido).days
        linhas.append({"pedido": p, "dias_em_aberto": dias, "alerta": dias > 3})

    return render(request, "pedidos/pendentes.html", {
        "linhas": linhas,
        "hoje": hoje,
        "total": len(linhas),
    })
