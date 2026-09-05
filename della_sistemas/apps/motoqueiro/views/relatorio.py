from decimal import Decimal

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required

from ..models import MovimentoSaldoLalamove, SolicitacaoEntrega, SolicitacaoEntregaEvento
from ..services.escopo import qs_do_usuario
from ..services.periodo import PERIODOS, parse_periodo


@perm_required("motoqueiro.ver_relatorio")
def view_relatorio(request: HttpRequest) -> HttpResponse:
    periodo = parse_periodo(request)

    solicitacoes = (
        qs_do_usuario(request)
        .filter(criado_em__gte=periodo.inicio, criado_em__lte=periodo.fim)
        .order_by("colaborador__nome", "-criado_em")
    )

    secoes_por_colaborador = {}
    for s in solicitacoes:
        secoes_por_colaborador.setdefault(s.colaborador_id, {
            "colaborador": s.colaborador,
            "linhas": [],
            "total_valor": Decimal("0.00"),
        })
        secoes_por_colaborador[s.colaborador_id]["linhas"].append(s)
        secoes_por_colaborador[s.colaborador_id]["total_valor"] += s.valor

    secoes = sorted(secoes_por_colaborador.values(), key=lambda d: d["colaborador"].nome)

    ctx = {
        "secoes": secoes,
        "periodo": periodo,
        "periodos": PERIODOS,
        "total_geral": sum((s["total_valor"] for s in secoes), Decimal("0.00")),
        "total_corridas": sum(len(s["linhas"]) for s in secoes),
        "status_choices": SolicitacaoEntrega.STATUS_CHOICES,
        "ve_todos": request.user.pode_ver_todas_motoqueiro,
        "saldo_lalamove": MovimentoSaldoLalamove.saldo_atual(),
    }
    return render(request, "motoqueiro/relatorio.html", ctx)


@perm_required("motoqueiro.editar_status")
@require_POST
def view_atualizar_status_manual(request: HttpRequest, pk: int) -> HttpResponse:
    """Correção manual de status — para quando o webhook falhar ou a corrida
    não tiver sido criada via API (registro avulso)."""
    solicitacao = get_object_or_404(SolicitacaoEntrega, pk=pk)
    novo_status = request.POST.get("status", "")
    validos = dict(SolicitacaoEntrega.STATUS_CHOICES)
    if novo_status not in validos:
        messages.error(request, "Status inválido.")
        return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))

    status_anterior = solicitacao.status
    solicitacao.status = novo_status
    if novo_status in SolicitacaoEntrega.STATUS_FINAIS and not solicitacao.concluido_em:
        from django.utils import timezone
        solicitacao.concluido_em = timezone.now()
    solicitacao.save(update_fields=["status", "concluido_em", "atualizado_em"])

    SolicitacaoEntregaEvento.objects.create(
        solicitacao=solicitacao,
        status_anterior=status_anterior,
        status_novo=novo_status,
        origem="manual",
        payload={"usuario": request.user.username},
    )
    messages.success(request, f"Status atualizado para \"{validos[novo_status]}\".")
    return redirect(request.META.get("HTTP_REFERER", "motoqueiro:relatorio"))
