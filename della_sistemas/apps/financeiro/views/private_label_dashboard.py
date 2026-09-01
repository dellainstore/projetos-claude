"""Dashboard do Private Label — visão rápida de saldo por conta, quanto
entrou/saiu no período (realizado, via `Baixa`/`MovimentoConta`, não
previsto), gasto por categoria, recebido por forma de pagamento e as
compras parceladas em aberto com a próxima parcela a vencer.

Período por padrão = mês atual, usando a data da BAIXA (regime de caixa —
"quanto gastei/recebi" é sobre dinheiro que de fato saiu/entrou da conta,
diferente do DRE por competência que virá na Fase 1C)."""
import calendar
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Count, Sum
from django.shortcuts import render
from django.utils import timezone

from apps.core.decorators import perm_required
from apps.financeiro.models import (
    ESTADO_ABERTO,
    ESTADO_CANCELADO,
    ESTADO_PARCIAL,
    Baixa,
    ContaBancaria,
    LancamentoFinanceiro,
)
from apps.financeiro.services.private_label.operacao import obter_operacao_padrao
from apps.financeiro.services.private_label.recorrencias import verificar_lazy

TIPOS_SAIDA = ["despesa"]
TIPOS_ENTRADA = ["receita"]


def _periodo(request):
    escolha = request.GET.get("periodo", "atual")
    hoje = timezone.localdate()
    if escolha == "anterior":
        primeiro_dia_atual = hoje.replace(day=1)
        ultimo_dia_anterior = primeiro_dia_atual - timedelta(days=1)
        inicio = ultimo_dia_anterior.replace(day=1)
        fim = ultimo_dia_anterior
    elif escolha == "tudo":
        inicio, fim = None, None
    else:
        escolha = "atual"
        inicio = hoje.replace(day=1)
        ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
        fim = date(hoje.year, hoje.month, ultimo_dia)
    return escolha, inicio, fim


@perm_required("private_label.ver_dashboard")
def pl_dashboard(request):
    verificar_lazy()
    operacao = obter_operacao_padrao()
    escolha, inicio, fim = _periodo(request)

    baixas = Baixa.objects.filter(parcela__lancamento__operacao=operacao, estornada=False)
    if inicio:
        baixas = baixas.filter(data__gte=inicio)
    if fim:
        baixas = baixas.filter(data__lte=fim)

    despesas = baixas.filter(parcela__lancamento__tipo__in=TIPOS_SAIDA)
    receitas = baixas.filter(parcela__lancamento__tipo__in=TIPOS_ENTRADA)

    total_gasto = despesas.aggregate(total=Sum("valor_movimentado"))["total"] or Decimal("0.00")
    total_recebido = receitas.aggregate(total=Sum("valor_movimentado"))["total"] or Decimal("0.00")

    gasto_por_categoria = list(
        despesas.values(
            "parcela__lancamento__categoria__id",
            "parcela__lancamento__categoria__nome",
            "parcela__lancamento__categoria__icone",
        )
        .annotate(total=Sum("valor_movimentado"))
        .order_by("-total")
    )
    recebido_por_forma = list(
        receitas.values("forma_pagamento__id", "forma_pagamento__nome")
        .annotate(total=Sum("valor_movimentado"))
        .order_by("-total")
    )

    contas = ContaBancaria.objects.filter(operacao=operacao, ativa=True).order_by("nome")
    saldo_consolidado = Decimal("0.00")
    for conta in contas:
        conta.saldo = conta.saldo_atual()
        if conta.incluir_consolidado:
            saldo_consolidado += conta.saldo

    parcelados_qs = (
        LancamentoFinanceiro.objects.filter(operacao=operacao)
        .exclude(estado_estrutural=ESTADO_CANCELADO)
        .annotate(qtd_parcelas=Count("parcelas"))
        .filter(qtd_parcelas__gt=1)
        .select_related("categoria")
        .prefetch_related("parcelas")
        .order_by("-data_competencia")
    )
    linhas_parceladas = []
    total_parcelados = Decimal("0.00")
    total_parcelados_restante = Decimal("0.00")
    for lancamento in parcelados_qs:
        proxima = (
            lancamento.parcelas.filter(estado_estrutural__in=[ESTADO_ABERTO, ESTADO_PARCIAL])
            .order_by("data_vencimento")
            .first()
        )
        saldo_restante = lancamento.saldo_restante
        linhas_parceladas.append({
            "lancamento": lancamento,
            "proxima_parcela": proxima,
            "saldo_restante": saldo_restante,
        })
        total_parcelados += lancamento.valor_original
        total_parcelados_restante += saldo_restante

    contexto = {
        "periodo": escolha, "inicio": inicio, "fim": fim,
        "contas": contas, "saldo_consolidado": saldo_consolidado,
        "total_gasto": total_gasto, "total_recebido": total_recebido,
        "resultado": total_recebido - total_gasto,
        "gasto_por_categoria": gasto_por_categoria,
        "recebido_por_forma": recebido_por_forma,
        "linhas_parceladas": linhas_parceladas,
        "total_parcelados": total_parcelados,
        "total_parcelados_restante": total_parcelados_restante,
    }
    return render(request, "financeiro/private_label/dashboard.html", contexto)
