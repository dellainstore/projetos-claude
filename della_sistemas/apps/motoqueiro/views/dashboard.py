import json
from calendar import month_abbr
from datetime import date
from decimal import Decimal

from django.db.models import Count, Sum
from django.db.models.functions import TruncMonth
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.core.decorators import perm_required

from ..models import MovimentoSaldoLalamove, SolicitacaoEntrega
from ..services.escopo import qs_do_usuario
from ..services.periodo import PERIODOS, parse_periodo


@perm_required("motoqueiro.ver_dashboard")
def view_dashboard(request: HttpRequest) -> HttpResponse:
    periodo = parse_periodo(request)

    qs_base = qs_do_usuario(request)
    qs_periodo = qs_base.filter(
        criado_em__gte=periodo.inicio, criado_em__lte=periodo.fim
    )

    total_corridas = qs_periodo.count()
    total_valor = qs_periodo.aggregate(v=Sum("valor"))["v"] or Decimal("0.00")

    resumo_funcionario = list(
        qs_periodo.values("colaborador__nome")
        .annotate(corridas=Count("id"), valor=Sum("valor"))
        .order_by("-valor")
    )

    resumo_plataforma = list(
        qs_periodo.values("plataforma")
        .annotate(corridas=Count("id"), valor=Sum("valor"))
        .order_by("-valor")
    )
    plataforma_labels = dict(SolicitacaoEntrega.PLATAFORMA_CHOICES)
    for r in resumo_plataforma:
        r["plataforma_label"] = plataforma_labels.get(r["plataforma"], r["plataforma"])

    resumo_finalidade = list(
        qs_periodo.values("finalidade")
        .annotate(corridas=Count("id"), valor=Sum("valor"))
        .order_by("-valor")
    )
    finalidade_labels = dict(SolicitacaoEntrega.FINALIDADE_CHOICES)
    for r in resumo_finalidade:
        r["finalidade_label"] = finalidade_labels.get(r["finalidade"], "Não informado")

    # Grafico mensal: SEMPRE ultimos 12 meses (independente do filtro acima,
    # que e de dia/periodo curto - tendencia mensal precisa de janela maior).
    hoje = timezone.localdate()
    primeiro_mes = date(hoje.year, hoje.month, 1)
    meses = []
    m = primeiro_mes
    for _ in range(12):
        meses.insert(0, m)
        ano_ant = m.year - 1 if m.month == 1 else m.year
        mes_ant = 12 if m.month == 1 else m.month - 1
        m = date(ano_ant, mes_ant, 1)
    inicio_janela = meses[0]

    agregados_mes = (
        qs_base
        .filter(criado_em__date__gte=inicio_janela)
        .annotate(mes=TruncMonth("criado_em"))
        .values("mes")
        .annotate(valor=Sum("valor"), corridas=Count("id"))
    )
    mapa_mes = {a["mes"].date().replace(day=1): a for a in agregados_mes}

    labels_mes = [f"{month_abbr[m.month]}/{str(m.year)[2:]}" for m in meses]
    valores_mes = [float(mapa_mes.get(m, {}).get("valor") or 0) for m in meses]
    corridas_mes = [mapa_mes.get(m, {}).get("corridas") or 0 for m in meses]

    ctx = {
        "periodo": periodo,
        "periodos": PERIODOS,
        "total_corridas": total_corridas,
        "total_valor": total_valor,
        "resumo_funcionario": resumo_funcionario,
        "resumo_plataforma": resumo_plataforma,
        "resumo_finalidade": resumo_finalidade,
        "ve_todos": request.user.pode_ver_todas_motoqueiro,
        "saldo_lalamove": MovimentoSaldoLalamove.saldo_atual(),
        "grafico_mensal_json": json.dumps({
            "labels": labels_mes,
            "valores": valores_mes,
            "corridas": corridas_mes,
        }),
    }
    return render(request, "motoqueiro/dashboard.html", ctx)
