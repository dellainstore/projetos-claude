"""Ajuste manual de saldo — ação sensível, só quem tem
`private_label.ajustar_saldo`. A checagem de permissão é feita na view; o
service só exige `motivo` preenchido (auditoria mínima) e sempre gera 1
MovimentoConta + 1 LogAuditoriaFinanceiro."""
from decimal import Decimal

from django.db import transaction

from apps.financeiro.models import AjusteSaldo, MovimentoConta
from .auditoria import registrar_log


@transaction.atomic
def ajustar_saldo(*, operacao, conta, valor, motivo: str, usuario=None) -> AjusteSaldo:
    valor = Decimal(valor)
    if valor == 0:
        raise ValueError("Valor do ajuste não pode ser zero.")
    if not motivo or not motivo.strip():
        raise ValueError("Motivo do ajuste é obrigatório.")

    ajuste = AjusteSaldo.objects.create(
        operacao=operacao, conta=conta, valor=valor, motivo=motivo.strip(), usuario=usuario,
    )
    MovimentoConta.objects.create(
        operacao=operacao, conta=conta, data=ajuste.criado_em.date(), valor=valor,
        evento_chave=f"ajuste:{ajuste.id}", ajuste=ajuste,
    )
    registrar_log(
        operacao=operacao, entidade="ajuste_saldo", objeto_id=ajuste.id, acao="ajuste",
        usuario=usuario, valor_para=f"R$ {valor} na conta {conta}: {motivo.strip()}",
    )
    return ajuste
