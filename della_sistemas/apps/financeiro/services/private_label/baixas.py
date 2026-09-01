"""Baixa (total/parcial) de parcelas — sempre grava 1 MovimentoConta e 1
LogAuditoriaFinanceiro dentro da mesma transação. `Baixa` é imutável após
criada; corrigir = estornar + lançar de novo (ver plano, seções 7/10/13)."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import (
    ESTADO_CANCELADO,
    ESTADO_QUITADO,
    Baixa,
    MovimentoConta,
    sinal_movimento,
)
from .auditoria import registrar_log


@transaction.atomic
def dar_baixa(
    *, parcela, valor_principal, data, conta, forma_pagamento=None,
    juros=Decimal("0"), multa=Decimal("0"), desconto=Decimal("0"),
    observacao="", usuario=None, permitir_excedente=False,
) -> Baixa:
    if parcela.estado_estrutural == ESTADO_CANCELADO:
        raise ValueError("Parcela cancelada não pode receber baixa.")
    if parcela.estado_estrutural == ESTADO_QUITADO:
        raise ValueError("Parcela já quitada.")

    valor_principal = Decimal(valor_principal)
    juros = Decimal(juros or 0)
    multa = Decimal(multa or 0)
    desconto = Decimal(desconto or 0)

    if valor_principal <= 0:
        raise ValueError("Valor principal da baixa deve ser maior que zero.")
    if juros < 0 or multa < 0 or desconto < 0:
        raise ValueError("Juros, multa e desconto não podem ser negativos.")

    saldo = parcela.saldo_restante
    if valor_principal > saldo and not permitir_excedente:
        raise ValueError(
            f"Valor da baixa (R$ {valor_principal}) maior que o saldo restante da parcela (R$ {saldo})."
        )

    valor_movimentado = valor_principal + juros + multa - desconto
    if valor_movimentado < 0:
        raise ValueError("Valor movimentado não pode ser negativo (desconto maior que principal+juros+multa).")

    baixa = Baixa.objects.create(
        parcela=parcela, valor_principal=valor_principal, juros=juros, multa=multa,
        desconto=desconto, valor_movimentado=valor_movimentado, data=data, conta=conta,
        forma_pagamento=forma_pagamento, observacao=observacao, usuario=usuario,
    )

    sinal = sinal_movimento(parcela.lancamento.tipo)
    MovimentoConta.objects.create(
        operacao=parcela.lancamento.operacao, conta=conta, data=data,
        valor=valor_movimentado * sinal, evento_chave=f"baixa:{baixa.id}", baixa=baixa,
    )

    parcela.recalcular_estado()
    parcela.lancamento.recalcular_estado()

    registrar_log(
        operacao=parcela.lancamento.operacao, entidade="baixa", objeto_id=baixa.id, acao="baixa",
        usuario=usuario, valor_para=f"R$ {valor_movimentado} na conta {conta}",
    )
    return baixa


@transaction.atomic
def estornar_baixa(baixa: Baixa, *, usuario=None, motivo: str = "") -> Baixa:
    if baixa.estornada:
        raise ValueError("Baixa já estornada.")

    movimento_original = baixa.movimentos.filter(evento_chave=f"baixa:{baixa.id}").first()
    if movimento_original is None:
        raise RuntimeError(f"Baixa {baixa.id} sem movimento original — dado inconsistente.")

    baixa.estornada = True
    baixa.estornada_em = timezone.now()
    baixa.estornada_por = usuario
    if motivo:
        baixa.observacao = f"{baixa.observacao}\n[estornada] {motivo}".strip()
    baixa.save(update_fields=["estornada", "estornada_em", "estornada_por", "observacao"])

    # Ledger append-only: nunca edita o movimento original, lança o inverso.
    MovimentoConta.objects.create(
        operacao=movimento_original.operacao, conta=movimento_original.conta,
        data=timezone.localdate(), valor=-movimento_original.valor,
        evento_chave=f"estorno-baixa:{baixa.id}", baixa=baixa,
    )

    baixa.parcela.recalcular_estado()
    baixa.parcela.lancamento.recalcular_estado()

    registrar_log(
        operacao=movimento_original.operacao, entidade="baixa", objeto_id=baixa.id, acao="estorno",
        usuario=usuario, valor_de=f"R$ {baixa.valor_movimentado}", valor_para=motivo,
    )
    return baixa


@transaction.atomic
def dar_baixa_em_lote(parcelas, *, data, conta, forma_pagamento=None, usuario=None) -> list[Baixa]:
    """Baixa total (sem juros/multa/desconto) de várias parcelas de uma vez
    — ação de seleção múltipla da tela de Lançamentos."""
    resultado = []
    for parcela in parcelas:
        if parcela.estado_estrutural in (ESTADO_CANCELADO, ESTADO_QUITADO):
            continue
        resultado.append(
            dar_baixa(
                parcela=parcela, valor_principal=parcela.saldo_restante, data=data, conta=conta,
                forma_pagamento=forma_pagamento, usuario=usuario,
            )
        )
    return resultado
