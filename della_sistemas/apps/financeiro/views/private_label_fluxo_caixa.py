"""Fluxo de Caixa (Fase 1C) — ver `services/private_label/fluxo_caixa.py`
para a lógica de cálculo. A view só resolve o período/conta escolhidos e
formata o contexto pro template."""
import calendar
from datetime import date
from decimal import Decimal

from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.financeiro.models import ContaBancaria
from apps.financeiro.services.private_label.datas import normalizar_data, somar_meses
from apps.financeiro.services.private_label.fluxo_caixa import calcular_fluxo
from apps.financeiro.services.private_label.operacao import obter_operacao_padrao
from apps.financeiro.services.private_label.recorrencias import verificar_lazy


def _periodo(request, hoje):
    escolha = request.GET.get("periodo", "mes")
    if escolha == "trimestre":
        inicio = hoje.replace(day=1)
        mes_fim = somar_meses(inicio, 2)
        fim = date(mes_fim.year, mes_fim.month, calendar.monthrange(mes_fim.year, mes_fim.month)[1])
        granularidade = "mes"
    elif escolha == "personalizado":
        bruto_inicio = request.GET.get("inicio")
        bruto_fim = request.GET.get("fim")
        inicio = normalizar_data(bruto_inicio) if bruto_inicio else hoje.replace(day=1)
        fim = normalizar_data(bruto_fim) if bruto_fim else hoje
        granularidade = "mes" if (fim - inicio).days > 92 else "dia"
    else:
        escolha = "mes"
        inicio = hoje.replace(day=1)
        fim = date(hoje.year, hoje.month, calendar.monthrange(hoje.year, hoje.month)[1])
        granularidade = "dia"
    return escolha, inicio, fim, granularidade


@perm_required("private_label.ver_fluxo_caixa")
def pl_fluxo_caixa(request):
    verificar_lazy()
    operacao = obter_operacao_padrao()
    hoje = date.today()
    escolha, inicio, fim, granularidade = _periodo(request, hoje)

    conta_pk = request.GET.get("conta")
    conta = ContaBancaria.objects.filter(pk=conta_pk, operacao=operacao).first() if conta_pk else None

    linhas = calcular_fluxo(
        operacao=operacao, data_inicio=inicio, data_fim=fim, conta=conta,
        granularidade=granularidade, hoje=hoje,
    )

    totais = {
        "realizado_entrada": sum((l.realizado_entrada for l in linhas), Decimal("0.00")),
        "realizado_saida": sum((l.realizado_saida for l in linhas), Decimal("0.00")),
        "previsto_entrada": sum((l.previsto_entrada for l in linhas), Decimal("0.00")),
        "previsto_saida": sum((l.previsto_saida for l in linhas), Decimal("0.00")),
    }
    saldo_final = linhas[-1].saldo_acumulado if linhas else Decimal("0.00")

    contexto = {
        "periodo": escolha, "inicio": inicio, "fim": fim, "granularidade": granularidade,
        "hoje": hoje, "linhas": linhas, "totais": totais, "saldo_final": saldo_final,
        "contas": ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome"),
        "conta_selecionada": conta,
    }
    return render(request, "financeiro/private_label/fluxo_caixa.html", contexto)
