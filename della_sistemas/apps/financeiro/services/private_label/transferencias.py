"""Transferência entre contas — sempre 2 MovimentoConta vinculados, efeito
líquido zero, nunca entra no DRE (nenhuma categoria é atribuída)."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import MovimentoConta, Transferencia
from .auditoria import registrar_log


@transaction.atomic
def transferir(*, operacao, conta_origem, conta_destino, valor, data, observacao="", usuario=None) -> Transferencia:
    valor = Decimal(valor)
    if valor <= 0:
        raise ValueError("Valor da transferência deve ser maior que zero.")
    if conta_origem_id_igual(conta_origem, conta_destino):
        raise ValueError("Conta de origem e destino não podem ser a mesma.")

    transferencia = Transferencia.objects.create(
        operacao=operacao, conta_origem=conta_origem, conta_destino=conta_destino,
        valor=valor, data=data, observacao=observacao, criado_por=usuario,
    )
    MovimentoConta.objects.create(
        operacao=operacao, conta=conta_origem, data=data, valor=-valor,
        evento_chave=f"transferencia:{transferencia.id}:saida", transferencia=transferencia,
    )
    MovimentoConta.objects.create(
        operacao=operacao, conta=conta_destino, data=data, valor=valor,
        evento_chave=f"transferencia:{transferencia.id}:entrada", transferencia=transferencia,
    )
    registrar_log(
        operacao=operacao, entidade="transferencia", objeto_id=transferencia.id, acao="criacao",
        usuario=usuario, valor_para=f"R$ {valor}: {conta_origem} -> {conta_destino}",
    )
    return transferencia


def conta_origem_id_igual(conta_origem, conta_destino) -> bool:
    return conta_origem.pk == conta_destino.pk


@transaction.atomic
def estornar_transferencia(transferencia: Transferencia, *, usuario=None, motivo: str = "") -> Transferencia:
    if transferencia.estornada:
        raise ValueError("Transferência já estornada.")
    hoje = timezone.localdate()
    for movimento in transferencia.movimentos.filter(evento_chave__in=[
        f"transferencia:{transferencia.id}:saida", f"transferencia:{transferencia.id}:entrada",
    ]):
        MovimentoConta.objects.create(
            operacao=movimento.operacao, conta=movimento.conta, data=hoje, valor=-movimento.valor,
            evento_chave=f"estorno-{movimento.evento_chave}", transferencia=transferencia,
        )
    transferencia.estornada = True
    transferencia.estornada_em = timezone.now()
    transferencia.estornada_por = usuario
    if motivo:
        transferencia.observacao = f"{transferencia.observacao}\n[estornada] {motivo}".strip()
    transferencia.save(update_fields=["estornada", "estornada_em", "estornada_por", "observacao"])

    registrar_log(
        operacao=transferencia.operacao, entidade="transferencia", objeto_id=transferencia.id,
        acao="estorno", usuario=usuario, valor_para=motivo,
    )
    return transferencia
