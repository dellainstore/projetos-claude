"""Compra parcelada no cartão, geração de fatura por competência e
pagamento (total/parcial) — ver plano, seções 3 e 11.

Regra de qual fatura recebe a 1ª parcela de uma compra: se a compra
acontece DEPOIS do dia de fechamento do cartão naquele mês, ela cai na
fatura do mês seguinte (a do mês corrente já fechou); caso contrário, cai
na fatura do próprio mês (ainda aberta). As parcelas seguintes vão sempre
para o mês seguinte à anterior — parcelamento de cartão é sempre mensal.

`ParcelaCompraCartao.paga_valor` nunca é editado direto: só via
`pagar_fatura`/`estornar_pagamento_fatura`, que também gravam
`FaturaPagamentoAlocacao` (de onde saiu/voltou cada real) e o
`MovimentoConta` da conta usada."""
import calendar
from datetime import date
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import (
    CompraCartao,
    FaturaCartao,
    FaturaPagamento,
    FaturaPagamentoAlocacao,
    MovimentoConta,
    ParcelaCompraCartao,
)
from .auditoria import registrar_log
from .datas import normalizar_data, somar_meses
from .lancamentos import gerar_valores_parcelas


def _competencia_da_primeira_parcela(cartao, data_compra):
    if data_compra.day > cartao.dia_fechamento:
        proxima = somar_meses(data_compra.replace(day=1), 1)
        return proxima.year, proxima.month
    return data_compra.year, data_compra.month


def _data_fechamento(cartao, ano: int, mes: int):
    dia = min(cartao.dia_fechamento, calendar.monthrange(ano, mes)[1])
    return date(ano, mes, dia)


def _data_vencimento(cartao, ano: int, mes: int):
    if cartao.dia_vencimento > cartao.dia_fechamento:
        dia = min(cartao.dia_vencimento, calendar.monthrange(ano, mes)[1])
        return date(ano, mes, dia)
    proximo = somar_meses(date(ano, mes, 1), 1)
    dia = min(cartao.dia_vencimento, calendar.monthrange(proximo.year, proximo.month)[1])
    return date(proximo.year, proximo.month, dia)


def obter_ou_criar_fatura(cartao, ano: int, mes: int) -> FaturaCartao:
    fatura, criada = FaturaCartao.objects.get_or_create(
        cartao=cartao, competencia_ano=ano, competencia_mes=mes,
        defaults={
            "data_fechamento": _data_fechamento(cartao, ano, mes),
            "data_vencimento": _data_vencimento(cartao, ano, mes),
        },
    )
    return fatura


@transaction.atomic
def lancar_compra_cartao(
    *, operacao, cartao, categoria, descricao, valor_total, data_compra,
    parcelas_qtd=1, centro_custo=None, contato=None, numero_documento="",
    observacoes="", usuario=None,
) -> CompraCartao:
    valor_total = Decimal(valor_total)
    if valor_total <= 0:
        raise ValueError("Valor total da compra deve ser maior que zero.")
    if categoria is None:
        raise ValueError("Categoria é obrigatória.")
    parcelas_qtd = int(parcelas_qtd)
    if parcelas_qtd < 1:
        raise ValueError("Quantidade de parcelas deve ser pelo menos 1.")
    data_compra = normalizar_data(data_compra)

    compra = CompraCartao.objects.create(
        operacao=operacao, cartao=cartao, descricao=descricao, categoria=categoria,
        centro_custo=centro_custo, contato=contato, valor_total=valor_total,
        data_compra=data_compra, parcelas_qtd=parcelas_qtd, numero_documento=numero_documento,
        observacoes=observacoes, criado_por=usuario,
    )

    valores = gerar_valores_parcelas(valor_total, parcelas_qtd)
    ano, mes = _competencia_da_primeira_parcela(cartao, data_compra)
    for numero, valor in enumerate(valores, start=1):
        fatura = obter_ou_criar_fatura(cartao, ano, mes)
        ParcelaCompraCartao.objects.create(compra=compra, numero=numero, valor=valor, fatura=fatura)
        proxima = somar_meses(date(ano, mes, 1), 1)
        ano, mes = proxima.year, proxima.month

    registrar_log(
        operacao=operacao, entidade="compra_cartao", objeto_id=compra.id, acao="criacao",
        usuario=usuario, valor_para=f"R$ {valor_total} em {parcelas_qtd}x no {cartao.nome}",
    )
    return compra


@transaction.atomic
def cancelar_compra_cartao(compra: CompraCartao, *, usuario=None) -> CompraCartao:
    """Só permitida enquanto NENHUMA parcela recebeu pagamento — ver plano,
    seção 19 ("estorno de parcela já paga fica bloqueado na Fase 1B, usa
    ajuste manual auditado até haver caso real que justifique automatizar")."""
    if compra.cancelada:
        return compra
    if compra.parcelas.filter(paga_valor__gt=0).exists():
        raise ValueError(
            "Esta compra já tem parcela(s) paga(s) em alguma fatura — cancelamento automático não "
            "é suportado nesse caso. Use um ajuste de saldo manual para corrigir."
        )
    compra.cancelada = True
    compra.cancelada_em = timezone.now()
    compra.cancelada_por = usuario
    compra.save(update_fields=["cancelada", "cancelada_em", "cancelada_por"])
    for fatura in FaturaCartao.objects.filter(parcelas__compra=compra).distinct():
        fatura.recalcular_estado()
    registrar_log(
        operacao=compra.operacao, entidade="compra_cartao", objeto_id=compra.id,
        acao="cancelamento", usuario=usuario,
    )
    return compra


@transaction.atomic
def pagar_fatura(*, fatura: FaturaCartao, valor, data, conta, observacao="", usuario=None) -> FaturaPagamento:
    valor = Decimal(valor)
    if valor <= 0:
        raise ValueError("Valor do pagamento deve ser maior que zero.")
    saldo = fatura.saldo_restante
    if valor > saldo:
        raise ValueError(f"Valor do pagamento (R$ {valor}) maior que o saldo da fatura (R$ {saldo}).")

    pagamento = FaturaPagamento.objects.create(
        fatura=fatura, valor=valor, data=data, conta=conta, observacao=observacao, usuario=usuario,
    )

    restante = valor
    parcelas_em_aberto = fatura.parcelas.filter(compra__cancelada=False).order_by(
        "compra__data_compra", "compra_id", "numero",
    )
    for parcela in parcelas_em_aberto:
        if restante <= 0:
            break
        aberto = parcela.saldo_restante
        if aberto <= 0:
            continue
        aplicado = min(aberto, restante)
        FaturaPagamentoAlocacao.objects.create(pagamento=pagamento, parcela=parcela, valor=aplicado)
        parcela.paga_valor = parcela.paga_valor + aplicado
        parcela.save(update_fields=["paga_valor"])
        restante -= aplicado

    MovimentoConta.objects.create(
        operacao=fatura.cartao.operacao, conta=conta, data=data, valor=-valor,
        evento_chave=f"fatura-pagamento:{pagamento.id}", fatura_pagamento=pagamento,
    )
    fatura.recalcular_estado()

    registrar_log(
        operacao=fatura.cartao.operacao, entidade="fatura_pagamento", objeto_id=pagamento.id,
        acao="baixa", usuario=usuario, valor_para=f"R$ {valor} na conta {conta} — {fatura}",
    )
    return pagamento


@transaction.atomic
def estornar_pagamento_fatura(pagamento: FaturaPagamento, *, usuario=None, motivo: str = "") -> FaturaPagamento:
    if pagamento.estornado:
        raise ValueError("Pagamento já estornado.")

    for alocacao in pagamento.alocacoes.select_related("parcela").all():
        parcela = alocacao.parcela
        parcela.paga_valor = parcela.paga_valor - alocacao.valor
        parcela.save(update_fields=["paga_valor"])

    movimento_original = pagamento.movimentos.filter(evento_chave=f"fatura-pagamento:{pagamento.id}").first()
    if movimento_original is None:
        raise RuntimeError(f"Pagamento {pagamento.id} sem movimento original — dado inconsistente.")
    MovimentoConta.objects.create(
        operacao=movimento_original.operacao, conta=movimento_original.conta,
        data=timezone.localdate(), valor=-movimento_original.valor,
        evento_chave=f"estorno-fatura-pagamento:{pagamento.id}", fatura_pagamento=pagamento,
    )

    pagamento.estornado = True
    pagamento.estornado_em = timezone.now()
    pagamento.estornado_por = usuario
    if motivo:
        pagamento.observacao = f"{pagamento.observacao}\n[estornado] {motivo}".strip()
    pagamento.save(update_fields=["estornado", "estornado_em", "estornado_por", "observacao"])

    pagamento.fatura.recalcular_estado()

    registrar_log(
        operacao=movimento_original.operacao, entidade="fatura_pagamento", objeto_id=pagamento.id,
        acao="estorno", usuario=usuario, valor_de=f"R$ {pagamento.valor}", valor_para=motivo,
    )
    return pagamento
