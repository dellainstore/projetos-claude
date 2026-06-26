from datetime import date, timedelta

from django.http import HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.pedidos.models import HistoricoDataPedido, HistoricoSituacaoPedido
from apps.pedidos.services.situacoes import ATENDIDO_IDS, CANCELADO_IDS


# Situações que, quando aparecem como ANTERIOR, indicam mudança relevante
_IDS_RELEVANTES = set(ATENDIDO_IDS.keys()) | set(CANCELADO_IDS.keys())


@perm_required("pedidos.ver")
def view_historico(request):
    limite = date.today() - timedelta(days=90)

    # Só mudanças de situação relevantes: quando saiu de Atendido ou Cancelado
    mudancas_situacao = (
        HistoricoSituacaoPedido.objects
        .filter(
            situacao_anterior_id__isnull=False,
            situacao_anterior_id__in=_IDS_RELEVANTES,
            registrado_em__date__gte=limite,
        )
        .select_related("pedido")
        .order_by("-registrado_em")[:200]
    )

    # Todas as mudanças de data (sempre relevantes)
    mudancas_data = (
        HistoricoDataPedido.objects
        .filter(registrado_em__date__gte=limite)
        .select_related("pedido")
        .order_by("-registrado_em")[:200]
    )

    eventos = []
    for h in mudancas_situacao:
        eventos.append({
            "id": h.pk,
            "tipo": "situacao",
            "pedido": h.pedido,
            "de": h.situacao_anterior_nome,
            "para": h.situacao_nome,
            "quando": h.registrado_em,
        })
    for h in mudancas_data:
        eventos.append({
            "id": h.pk,
            "tipo": "data",
            "pedido": h.pedido,
            "de": h.data_anterior.strftime("%d/%m/%Y"),
            "para": h.data_nova.strftime("%d/%m/%Y"),
            "quando": h.registrado_em,
        })

    # Ordena por pedido (desc) depois por data (desc)
    eventos.sort(key=lambda e: (-e["pedido"].bling_id, -int(e["quando"].timestamp())))

    return render(request, "pedidos/historico.html", {
        "eventos": eventos[:300],
        "sem_registros": not eventos,
    })


@perm_required("admin.usuarios")
@require_POST
def view_historico_excluir(request, tipo: str, pk: int):
    if tipo == "situacao":
        HistoricoSituacaoPedido.objects.filter(pk=pk).delete()
    elif tipo == "data":
        HistoricoDataPedido.objects.filter(pk=pk).delete()
    return HttpResponse("")
