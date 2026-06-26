import threading
from datetime import date, timedelta

from django.contrib import messages
from django.db.models import Exists, OuterRef
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.core.decorators import perm_required
from apps.pedidos.models import HistoricoSituacaoPedido, PedidoBling
from apps.pedidos.services import sync_state
from apps.pedidos.services.situacoes import ATENDIDO_IDS, EM_ABERTO_IDS, EM_ANDAMENTO_IDS

INICIO_2026 = date(2026, 1, 1)


@perm_required("pedidos.ver")
def view_dashboard(request):
    hoje = date.today()
    limite_andamento = hoje - timedelta(days=3)

    em_aberto = [
        {"pedido": p, "dias": (hoje - p.data_pedido).days}
        for p in PedidoBling.objects.filter(
            situacao_id__in=list(EM_ABERTO_IDS.keys()),
            data_pedido__gte=INICIO_2026,
            data_pedido__lt=limite_andamento,
            is_permuta=False,
        ).order_by("-data_pedido", "-bling_id")
    ] if EM_ABERTO_IDS else []

    em_andamento_qs = PedidoBling.objects.filter(
        situacao_id__in=list(EM_ANDAMENTO_IDS.keys()),
        data_pedido__gte=INICIO_2026,
        data_pedido__lt=limite_andamento,
        is_permuta=False,
    ).order_by("-data_pedido", "-bling_id") if EM_ANDAMENTO_IDS else PedidoBling.objects.none()
    em_andamento_antigos = [
        {"pedido": p, "dias": (hoje - p.data_pedido).days}
        for p in em_andamento_qs
    ]

    teve_atendido = HistoricoSituacaoPedido.objects.filter(
        pedido=OuterRef("pk"),
        situacao_id__in=list(ATENDIDO_IDS.keys()),
    )
    revertidos = list(
        PedidoBling.objects.annotate(
            teve_atendido=Exists(teve_atendido)
        ).filter(
            teve_atendido=True,
            data_pedido__gte=INICIO_2026,
            is_permuta=False,
        ).exclude(
            situacao_id__in=list(ATENDIDO_IDS.keys()),
        ).order_by("-atualizado_em")
    )

    return render(request, "pedidos/dashboard.html", {
        "em_aberto": em_aberto,
        "em_andamento_antigos": em_andamento_antigos,
        "revertidos": revertidos,
        "hoje": hoje,
        "dias_limite_andamento": 3,
        "sync_state": sync_state.get(),
    })


@perm_required("pedidos.sync")
@require_POST
def view_sync_start(request):
    """Inicia sync em background e retorna widget de progresso via HTMX."""
    state = sync_state.get()
    if state["running"]:
        return render(request, "pedidos/_sync_widget.html", {"sync_state": state})

    completo = request.POST.get("completo") == "1"
    modo = "Sync completo 2026" if completo else "Sync 30 dias"
    sync_state.update(running=True, pct=0, msg="Iniciando…", result=None, error=None, modo=modo)

    def _run():
        from apps.pedidos.services.sync import sync_pedidos
        try:
            stats = sync_pedidos(
                dias_retroativos=None if completo else 30,
                on_progress=lambda pct, msg: sync_state.update(pct=pct, msg=msg),
            )
            sync_state.update(
                running=False, pct=100, msg="Concluído!",
                result=stats,
            )
        except Exception as exc:
            logger.error("Sync falhou: %s", exc, exc_info=True)
            sync_state.update(running=False, pct=0, msg="", error=str(exc))

    threading.Thread(target=_run, daemon=True).start()
    return render(request, "pedidos/_sync_widget.html", {"sync_state": sync_state.get()})


@perm_required("pedidos.ver")
@require_GET
def view_sync_status(request):
    """Retorna o widget de progresso atual (polling HTMX)."""
    return render(request, "pedidos/_sync_widget.html", {"sync_state": sync_state.get()})


import logging
logger = logging.getLogger(__name__)
