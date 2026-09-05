"""Fluxo de Caixa (Fase 1C) — realizado (via `MovimentoConta`, o que já
aconteceu) × previsto (via `Parcela`/`ParcelaCompraCartao` em aberto, o que
ainda vai acontecer), diário ou mensal, consolidado ou por conta.

Realizado = tudo com `MovimentoConta.data <= hoje` no período. Previsto =
parcelas de lançamento (`Parcela`) e de fatura de cartão
(`ParcelaCompraCartao`, na data de VENCIMENTO DA FATURA — é quando a
fatura inteira sai da conta, não a data da compra) ainda em aberto, com
vencimento dentro do período. O saldo projetado acumulado soma os dois: é
"quanto vai sobrar na conta se nada mais mudar", ponto central do painel.
"""
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Q, Sum

from apps.financeiro.models import (
    ESTADO_ABERTO,
    ESTADO_PARCIAL,
    ContaBancaria,
    MovimentoConta,
    Parcela,
    ParcelaCompraCartao,
    TIPOS_ENTRADA,
)


@dataclass
class LinhaFluxo:
    data: date
    realizado_entrada: Decimal = field(default_factory=lambda: Decimal("0.00"))
    realizado_saida: Decimal = field(default_factory=lambda: Decimal("0.00"))
    previsto_entrada: Decimal = field(default_factory=lambda: Decimal("0.00"))
    previsto_saida: Decimal = field(default_factory=lambda: Decimal("0.00"))
    saldo_acumulado: Decimal = Decimal("0.00")

    @property
    def realizado_liquido(self) -> Decimal:
        return self.realizado_entrada - self.realizado_saida

    @property
    def previsto_liquido(self) -> Decimal:
        return self.previsto_entrada - self.previsto_saida


def _contas_do_filtro(operacao, conta=None):
    qs = ContaBancaria.objects.filter(operacao=operacao, ativa=True)
    if conta is not None:
        qs = qs.filter(pk=conta.pk)
    return list(qs)


def _saldo_anterior(contas, data_inicio: date) -> Decimal:
    total = Decimal("0.00")
    for conta in contas:
        movimentado_antes = conta.movimentos.filter(data__lt=data_inicio).aggregate(t=Sum("valor"))["t"] or Decimal("0.00")
        total += conta.saldo_inicial + movimentado_antes
    return total


def calcular_fluxo(*, operacao, data_inicio: date, data_fim: date, conta=None, granularidade="dia", hoje=None):
    hoje = hoje or date.today()
    contas = _contas_do_filtro(operacao, conta)
    conta_ids = [c.id for c in contas]

    linhas_por_data: dict[date, LinhaFluxo] = {}

    def linha(dia: date) -> LinhaFluxo:
        return linhas_por_data.setdefault(dia, LinhaFluxo(data=dia))

    # ── Realizado: MovimentoConta com data <= hoje dentro do período ──────
    fim_realizado = min(data_fim, hoje)
    if conta_ids and fim_realizado >= data_inicio:
        movimentos = MovimentoConta.objects.filter(
            conta_id__in=conta_ids, data__gte=data_inicio, data__lte=fim_realizado,
        ).values("data", "valor")
        for m in movimentos:
            l = linha(m["data"])
            if m["valor"] >= 0:
                l.realizado_entrada += m["valor"]
            else:
                l.realizado_saida += -m["valor"]

    # ── Previsto: parcelas de lançamento em aberto, vencimento > hoje ─────
    inicio_previsto = max(data_inicio, hoje + timedelta(days=1))
    if conta_ids and inicio_previsto <= data_fim:
        filtro_conta = Q(conta_prevista_id__in=conta_ids) | (
            Q(conta_prevista__isnull=True) & Q(lancamento__conta_prevista_id__in=conta_ids)
        )
        if conta is None:
            # Consolidado: qualquer parcela da operação entra, tenha ou não
            # conta prevista definida — sem conta escolhida ainda conta pro
            # projetado consolidado.
            filtro_conta = Q()
        parcelas = Parcela.objects.filter(
            filtro_conta, lancamento__operacao=operacao,
            data_vencimento__gte=inicio_previsto, data_vencimento__lte=data_fim,
            estado_estrutural__in=[ESTADO_ABERTO, ESTADO_PARCIAL],
        ).select_related("lancamento")
        for p in parcelas:
            l = linha(p.data_vencimento)
            saldo = p.saldo_restante
            if p.lancamento.tipo in TIPOS_ENTRADA:
                l.previsto_entrada += saldo
            else:
                l.previsto_saida += saldo

        # ── Previsto: faturas de cartão em aberto (saída na data de
        # vencimento da FATURA, não da compra) ────────────────────────────
        filtro_cartao = Q()
        if conta is not None:
            filtro_cartao = Q(fatura__cartao__conta_pagamento_padrao_id__in=conta_ids)
        parcelas_cartao = ParcelaCompraCartao.objects.filter(
            filtro_cartao, compra__operacao=operacao, compra__cancelada=False,
            fatura__data_vencimento__gte=inicio_previsto, fatura__data_vencimento__lte=data_fim,
        ).select_related("fatura")
        # `saldo_restante` (valor - paga_valor) é sempre >= 0 por constraint
        # de banco — só pula quando já totalmente pago (saldo == 0).
        for p in parcelas_cartao:
            saldo = p.saldo_restante
            if saldo <= 0:
                continue
            l = linha(p.fatura.data_vencimento)
            l.previsto_saida += saldo

    # ── Monta a série completa (preenche buracos com zero) ────────────────
    saldo = _saldo_anterior(contas, data_inicio)
    linhas = []
    cursor = data_inicio
    while cursor <= data_fim:
        l = linhas_por_data.get(cursor, LinhaFluxo(data=cursor))
        saldo += l.realizado_liquido + l.previsto_liquido
        l.saldo_acumulado = saldo
        linhas.append(l)
        cursor += timedelta(days=1)

    if granularidade == "mes":
        linhas = _agrupar_por_mes(linhas)

    return linhas


def _agrupar_por_mes(linhas: list[LinhaFluxo]) -> list[LinhaFluxo]:
    agrupado: dict[tuple[int, int], LinhaFluxo] = {}
    for l in linhas:
        chave = (l.data.year, l.data.month)
        if chave not in agrupado:
            agrupado[chave] = LinhaFluxo(data=date(l.data.year, l.data.month, 1))
        acc = agrupado[chave]
        acc.realizado_entrada += l.realizado_entrada
        acc.realizado_saida += l.realizado_saida
        acc.previsto_entrada += l.previsto_entrada
        acc.previsto_saida += l.previsto_saida
        acc.saldo_acumulado = l.saldo_acumulado  # saldo no FIM do mês (última linha do grupo, dias em ordem)
    return list(agrupado.values())
