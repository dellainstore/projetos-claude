"""Aplicação, resgate, rendimento e taxa/imposto de investimentos (Fase 2)
— ver plano, seções 1.4 e 3.

Aplicação/resgate remanejam patrimônio: saem/voltam de uma `ContaBancaria`
de verdade (1 `MovimentoConta`) e crescem/diminuem o saldo da
`ContaInvestimento` (1 `MovimentoContaInvestimento`) — ficam FORA do DRE,
igual uma `Transferencia` (nenhuma categoria é atribuída). Rendimento/taxa
não tocam conta bancária nenhuma — só o saldo do investimento muda — e
ENTRAM no DRE pela `categoria` informada (validada por natureza)."""
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import (
    InvestimentoTransacao,
    MovimentoConta,
    MovimentoContaInvestimento,
)
from .auditoria import registrar_log


@transaction.atomic
def aplicar(*, operacao, conta_investimento, conta_bancaria, valor, data, observacao="", usuario=None) -> InvestimentoTransacao:
    valor = Decimal(valor)
    if valor <= 0:
        raise ValueError("Valor da aplicação deve ser maior que zero.")

    transacao = InvestimentoTransacao.objects.create(
        operacao=operacao, conta_investimento=conta_investimento, conta_bancaria=conta_bancaria,
        tipo="aplicacao", valor=valor, data=data, observacao=observacao, usuario=usuario,
    )
    MovimentoConta.objects.create(
        operacao=operacao, conta=conta_bancaria, data=data, valor=-valor,
        evento_chave=f"investimento:{transacao.id}:saida-banco", investimento_transacao=transacao,
    )
    MovimentoContaInvestimento.objects.create(
        conta_investimento=conta_investimento, transacao=transacao, data=data, valor=valor,
        evento_chave=f"investimento:{transacao.id}:entrada-investimento",
    )
    registrar_log(
        operacao=operacao, entidade="investimento_transacao", objeto_id=transacao.id, acao="criacao",
        usuario=usuario, valor_para=f"Aplicação de R$ {valor} em {conta_investimento}",
    )
    return transacao


@transaction.atomic
def resgatar(*, operacao, conta_investimento, conta_bancaria, valor, data, observacao="", usuario=None) -> InvestimentoTransacao:
    valor = Decimal(valor)
    if valor <= 0:
        raise ValueError("Valor do resgate deve ser maior que zero.")
    saldo = conta_investimento.saldo_atual()
    if valor > saldo:
        raise ValueError(f"Valor do resgate (R$ {valor}) maior que o saldo do investimento (R$ {saldo}).")

    transacao = InvestimentoTransacao.objects.create(
        operacao=operacao, conta_investimento=conta_investimento, conta_bancaria=conta_bancaria,
        tipo="resgate", valor=valor, data=data, observacao=observacao, usuario=usuario,
    )
    MovimentoConta.objects.create(
        operacao=operacao, conta=conta_bancaria, data=data, valor=valor,
        evento_chave=f"investimento:{transacao.id}:entrada-banco", investimento_transacao=transacao,
    )
    MovimentoContaInvestimento.objects.create(
        conta_investimento=conta_investimento, transacao=transacao, data=data, valor=-valor,
        evento_chave=f"investimento:{transacao.id}:saida-investimento",
    )
    registrar_log(
        operacao=operacao, entidade="investimento_transacao", objeto_id=transacao.id, acao="criacao",
        usuario=usuario, valor_para=f"Resgate de R$ {valor} de {conta_investimento}",
    )
    return transacao


@transaction.atomic
def registrar_rendimento(*, operacao, conta_investimento, categoria, valor, data, observacao="", usuario=None) -> InvestimentoTransacao:
    valor = Decimal(valor)
    if valor <= 0:
        raise ValueError("Valor do rendimento deve ser maior que zero.")
    if categoria is None or categoria.natureza != "receita_financeira":
        raise ValueError("Rendimento precisa de uma categoria de natureza 'Receita financeira'.")

    transacao = InvestimentoTransacao.objects.create(
        operacao=operacao, conta_investimento=conta_investimento, categoria=categoria,
        tipo="rendimento", valor=valor, data=data, observacao=observacao, usuario=usuario,
    )
    MovimentoContaInvestimento.objects.create(
        conta_investimento=conta_investimento, transacao=transacao, data=data, valor=valor,
        evento_chave=f"investimento:{transacao.id}:rendimento",
    )
    registrar_log(
        operacao=operacao, entidade="investimento_transacao", objeto_id=transacao.id, acao="criacao",
        usuario=usuario, valor_para=f"Rendimento de R$ {valor} em {conta_investimento}",
    )
    return transacao


@transaction.atomic
def registrar_taxa(*, operacao, conta_investimento, categoria, valor, data, observacao="", usuario=None) -> InvestimentoTransacao:
    valor = Decimal(valor)
    if valor <= 0:
        raise ValueError("Valor da taxa/imposto deve ser maior que zero.")
    if categoria is None or categoria.natureza != "despesa_financeira":
        raise ValueError("Taxa/imposto precisa de uma categoria de natureza 'Despesa financeira'.")
    saldo = conta_investimento.saldo_atual()
    if valor > saldo:
        raise ValueError(f"Valor da taxa (R$ {valor}) maior que o saldo do investimento (R$ {saldo}).")

    transacao = InvestimentoTransacao.objects.create(
        operacao=operacao, conta_investimento=conta_investimento, categoria=categoria,
        tipo="taxa", valor=valor, data=data, observacao=observacao, usuario=usuario,
    )
    MovimentoContaInvestimento.objects.create(
        conta_investimento=conta_investimento, transacao=transacao, data=data, valor=-valor,
        evento_chave=f"investimento:{transacao.id}:taxa",
    )
    registrar_log(
        operacao=operacao, entidade="investimento_transacao", objeto_id=transacao.id, acao="criacao",
        usuario=usuario, valor_para=f"Taxa/imposto de R$ {valor} em {conta_investimento}",
    )
    return transacao


@transaction.atomic
def estornar_transacao(transacao: InvestimentoTransacao, *, usuario=None, motivo: str = "") -> InvestimentoTransacao:
    if transacao.estornada:
        raise ValueError("Transação já estornada.")
    hoje = timezone.localdate()

    for movimento in transacao.movimentos.all():
        MovimentoContaInvestimento.objects.create(
            conta_investimento=movimento.conta_investimento, transacao=transacao, data=hoje,
            valor=-movimento.valor, evento_chave=f"estorno-{movimento.evento_chave}",
        )
    for movimento in transacao.movimentos_conta_bancaria.all():
        MovimentoConta.objects.create(
            operacao=movimento.operacao, conta=movimento.conta, data=hoje, valor=-movimento.valor,
            evento_chave=f"estorno-{movimento.evento_chave}", investimento_transacao=transacao,
        )

    transacao.estornada = True
    transacao.estornada_em = timezone.now()
    transacao.estornada_por = usuario
    if motivo:
        transacao.observacao = f"{transacao.observacao}\n[estornada] {motivo}".strip()
    transacao.save(update_fields=["estornada", "estornada_em", "estornada_por", "observacao"])

    registrar_log(
        operacao=transacao.operacao, entidade="investimento_transacao", objeto_id=transacao.id,
        acao="estorno", usuario=usuario, valor_de=f"R$ {transacao.valor}", valor_para=motivo,
    )
    return transacao
