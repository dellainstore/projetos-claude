from datetime import date
from decimal import Decimal

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.metas.models import Funcionario, MetaFuncionario, MetaCanal
from apps.metas.services.relatorio import (
    carregar_vendas_periodo,
    calcular_individual,
    calcular_canais,
    calcular_lojas,
    calcular_geral_vendedoras,
    calcular_por_situacao,
    total_geral_mes,
    meses_disponiveis,
    usa_metas_individuais,
    dias_seg_a_sab_restantes,
    calcular_por_semana,
    _iter_months,
    MESES_PT,
)


def _mes_passado(hoje: date) -> tuple[int, int]:
    if hoje.month == 1:
        return hoje.year - 1, 12
    return hoje.year, hoje.month - 1


def _add_months(ano: int, mes: int, n: int) -> tuple[int, int]:
    m = mes + n
    a = ano + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return a, m


def _periodo_label(ano_ini, mes_ini, ano_fim, mes_fim) -> str:
    if (ano_ini, mes_ini) == (ano_fim, mes_fim):
        return f"{MESES_PT[mes_ini]}/{ano_ini}"
    return f"{MESES_PT[mes_ini]}/{ano_ini} a {MESES_PT[mes_fim]}/{ano_fim}"


@perm_required("metas.ver")
def view_dashboard(request: HttpRequest) -> HttpResponse:
    hoje = date.today()
    ano_atual, mes_atual = hoje.year, hoje.month
    ano_ant, mes_ant = _mes_passado(hoje)

    filtro = request.GET.get("filtro", "atual")

    if filtro == "passado":
        ano_ini = ano_fim = ano_ant
        mes_ini = mes_fim = mes_ant
    elif filtro == "custom":
        try:
            ano_ini = int(request.GET.get("ano_ini", ano_atual))
            mes_ini = int(request.GET.get("mes_ini", mes_atual))
            ano_fim = int(request.GET.get("ano_fim", ano_atual))
            mes_fim = int(request.GET.get("mes_fim", mes_atual))
        except (ValueError, TypeError):
            ano_ini = ano_fim = ano_atual
            mes_ini = mes_fim = mes_atual
        # Clamp: fim >= ini, e máx 4 meses
        if (ano_fim, mes_fim) < (ano_ini, mes_ini):
            ano_fim, mes_fim = ano_ini, mes_ini
        max_fim_a, max_fim_m = _add_months(ano_ini, mes_ini, 11)  # ini + 11 = 12 meses total
        if (ano_fim, mes_fim) > (max_fim_a, max_fim_m):
            ano_fim, mes_fim = max_fim_a, max_fim_m
    else:
        filtro = "atual"
        ano_ini = ano_fim = ano_atual
        mes_ini = mes_fim = mes_atual

    # Coleta todos os meses do período
    meses_periodo = list(_iter_months(ano_ini, mes_ini, ano_fim, mes_fim))

    # Vendas e metas do período completo
    vendas = carregar_vendas_periodo(ano_ini, mes_ini, ano_fim, mes_fim)
    funcionarios = list(Funcionario.objects.filter(ativo=True).order_by("nome"))

    metas_ind = []
    metas_canal_qs = []
    for a, m in meses_periodo:
        metas_ind.extend(MetaFuncionario.objects.filter(ano=a, mes=m))
        metas_canal_qs.extend(MetaCanal.objects.filter(ano=a, mes=m))

    # Usa modo individual se qualquer mês do período o suporta
    modo_individual = any(usa_metas_individuais(a, m) for a, m in meses_periodo)

    individual = []
    if modo_individual:
        individual = calcular_individual(vendas, funcionarios, metas_ind)

    canais = calcular_canais(
        vendas, metas_canal_qs, ano_ini, mes_ini,
        funcionarios_com_meta=funcionarios if modo_individual else None,
        metas_ind=metas_ind if modo_individual else None,
    )
    lojas = calcular_lojas(vendas)
    vendedoras = calcular_geral_vendedoras(vendas, funcionarios)
    por_situacao = calcular_por_situacao(vendas)
    totais = total_geral_mes(vendas)

    meses_lista = meses_disponiveis()
    anos_disponiveis = sorted({mv[0] for mv in meses_lista}, reverse=True)
    meses_nomes = [(i, MESES_PT[i]) for i in range(1, 13)]

    is_multi = len(meses_periodo) > 1
    periodo_label = _periodo_label(ano_ini, mes_ini, ano_fim, mes_fim)

    # Dias úteis restantes (Seg-Sáb) até o fim do período
    dias = dias_seg_a_sab_restantes(ano_fim, mes_fim)

    # Adiciona por_semana a cada card individual
    for item in individual:
        item["por_semana"] = calcular_por_semana(item["faltam"], dias)

    # Adiciona por_semana a cada card canal
    for canal in canais:
        canal["por_semana"] = calcular_por_semana(canal["faltam"], dias)

    # Meta geral (soma de todos os canais exceto Londrina)
    meta_total = sum(
        (m.valor for m in metas_canal_qs if m.canal != "londrina"),
        Decimal("0"),
    )
    pct_meta_total = float(totais["total"] / meta_total * 100) if meta_total > 0 else 0.0
    faltam_total = max(meta_total - totais["total"], Decimal("0")) if meta_total > 0 else Decimal("0")
    por_semana_total = calcular_por_semana(faltam_total, dias)

    return render(request, "metas/dashboard.html", {
        # período
        "ano_ini": ano_ini, "mes_ini": mes_ini,
        "ano_fim": ano_fim, "mes_fim": mes_fim,
        "periodo_label": periodo_label,
        "is_multi": is_multi,
        # compatibilidade com o template (single month)
        "ano": ano_fim, "mes": mes_fim,
        "mes_nome": MESES_PT.get(mes_fim, ""),
        # dados
        "modo_individual": modo_individual,
        "individual": individual,
        "canais": canais,
        "lojas": lojas,
        "vendedoras": vendedoras,
        "por_situacao": por_situacao,
        "totais": totais,
        "total_pedidos": len(vendas),
        "sem_dados": len(vendas) == 0,
        # meta geral
        "meta_total": meta_total,
        "pct_meta_total": pct_meta_total,
        "faltam_total": faltam_total,
        "por_semana_total": por_semana_total,
        "dias_restantes": dias,
        # filtro
        "filtro": filtro,
        "ano_atual": ano_atual,
        "mes_atual": mes_atual,
        "anos_disponiveis": anos_disponiveis,
        "meses_nomes": meses_nomes,
    })
