"""Aplicação, resgate, rendimento e taxa/imposto de investimentos (Fase 2)
— ver plano, seções 1.4 e 3.

Aplicação/resgate remanejam patrimônio: saem/voltam de uma `ContaBancaria`
de verdade (1 `MovimentoConta`) e crescem/diminuem o saldo da
`ContaInvestimento` (1 `MovimentoContaInvestimento`) — ficam FORA do DRE,
igual uma `Transferencia` (nenhuma categoria é atribuída). Rendimento/taxa
não tocam conta bancária nenhuma — só o saldo do investimento muda — e
ENTRAM no DRE pela `categoria` informada (validada por natureza)."""
from decimal import ROUND_HALF_UP, Decimal

from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import (
    InvestimentoTransacao,
    MovimentoConta,
    MovimentoContaInvestimento,
)
from .auditoria import registrar_log

# Tabela regressiva de IOF (Anexo I da IN RFB 907/2009) — incide só sobre o
# RENDIMENTO (nunca sobre o principal), zera a partir do 30º dia corrido
# contado da aplicação. Índice da lista = dias corridos desde a aplicação
# (1 a 29); dia 0 (resgate no mesmo dia da aplicação) usa a alíquota do dia 1.
TABELA_IOF_REGRESSIVA = {
    1: 96, 2: 93, 3: 90, 4: 86, 5: 83, 6: 80, 7: 76, 8: 73, 9: 70, 10: 66,
    11: 63, 12: 60, 13: 56, 14: 53, 15: 50, 16: 46, 17: 43, 18: 40, 19: 36,
    20: 33, 21: 30, 22: 26, 23: 23, 24: 20, 25: 16, 26: 13, 27: 10, 28: 6, 29: 3,
}


def _aliquota_iof(dias_corridos: int) -> Decimal:
    if dias_corridos >= 30:
        return Decimal("0")
    dias_corridos = max(dias_corridos, 1)
    return Decimal(TABELA_IOF_REGRESSIVA[dias_corridos]) / Decimal("100")


def _calcular_iof_resgate(conta_investimento, *, valor_resgate: Decimal, data_resgate) -> Decimal:
    """Calcula o IOF regressivo de um resgate — aproximação deliberada, não
    contabilidade de lote bancária completa (ver plano de implementação,
    2026-09-16): rendimento não fica preso a uma aplicação específica (é um
    ledger só, `MovimentoContaInvestimento`), então a fração do resgate que é
    "rendimento" é estimada pela proporção rendimento líquido acumulado ÷
    saldo atual (antes deste resgate). Essa fração é aplicada a cada pedaço
    do valor resgatado, consumindo as aplicações mais antigas primeiro
    (FIFO, mesmo espírito de estoque) — cada pedaço usa a idade (dias desde
    a SUA aplicação original) pra achar a alíquota na tabela regressiva. O
    rendimento nunca "reinicia a idade": ele cresce dentro do lote antigo
    que já existia, nunca vira um lote novo. Se as aplicações registradas já
    tiverem sido totalmente consumidas por resgates anteriores (sobra só
    rendimento acumulado sem aplicação viva), o restante usa a idade da
    aplicação mais recente conhecida (fallback conservador)."""
    saldo_antes = conta_investimento.saldo_atual()
    if saldo_antes <= 0 or valor_resgate <= 0:
        return Decimal("0.00")

    aplicacoes = list(
        conta_investimento.transacoes.filter(tipo="aplicacao", estornada=False).order_by("data", "id")
    )
    if not aplicacoes:
        return Decimal("0.00")
    resgates_anteriores = list(
        conta_investimento.transacoes.filter(tipo="resgate", estornada=False)
        .exclude(data__gt=data_resgate)
        .order_by("data", "id")
    )

    # Reconstrói os lotes ainda "vivos" no momento deste resgate, consumindo
    # as aplicações (FIFO) pelos resgates que já aconteceram antes dele.
    lotes = [{"data": a.data, "valor": a.valor} for a in aplicacoes]
    for resgate in resgates_anteriores:
        restante = resgate.valor
        for lote in lotes:
            if restante <= 0:
                break
            consumo = min(lote["valor"], restante)
            lote["valor"] -= consumo
            restante -= consumo

    principal_vivo = sum((lote["valor"] for lote in lotes), Decimal("0.00"))
    rendimento_liquido = max(saldo_antes - principal_vivo, Decimal("0.00"))
    razao_rendimento = (rendimento_liquido / saldo_antes) if saldo_antes > 0 else Decimal("0")

    ultima_data_aplicacao = aplicacoes[-1].data
    iof_total = Decimal("0.00")
    restante = valor_resgate
    for lote in lotes:
        if restante <= 0:
            break
        if lote["valor"] <= 0:
            continue
        consumo = min(lote["valor"], restante)
        dias = (data_resgate - lote["data"]).days
        rendimento_chunk = consumo * razao_rendimento
        iof_total += rendimento_chunk * _aliquota_iof(dias)
        restante -= consumo
    if restante > 0:
        # sobrou valor resgatado além de toda aplicação viva conhecida —
        # trata como se fosse da aplicação mais recente (fallback).
        dias = (data_resgate - ultima_data_aplicacao).days
        rendimento_chunk = restante * razao_rendimento
        iof_total += rendimento_chunk * _aliquota_iof(dias)

    return iof_total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


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

    iof = (
        _calcular_iof_resgate(conta_investimento, valor_resgate=valor, data_resgate=data)
        if conta_investimento.iof_automatico else Decimal("0.00")
    )
    # IOF é retido na fonte — sai do valor líquido que cai na conta bancária
    # (igual o banco faz de verdade), nunca some do investimento uma 2ª vez:
    # o resgate já tira o valor BRUTO inteiro do saldo investido logo abaixo.
    valor_liquido_banco = valor - iof

    transacao = InvestimentoTransacao.objects.create(
        operacao=operacao, conta_investimento=conta_investimento, conta_bancaria=conta_bancaria,
        tipo="resgate", valor=valor, data=data, observacao=observacao, usuario=usuario,
    )
    MovimentoConta.objects.create(
        operacao=operacao, conta=conta_bancaria, data=data, valor=valor_liquido_banco,
        evento_chave=f"investimento:{transacao.id}:entrada-banco", investimento_transacao=transacao,
    )
    MovimentoContaInvestimento.objects.create(
        conta_investimento=conta_investimento, transacao=transacao, data=data, valor=-valor,
        evento_chave=f"investimento:{transacao.id}:saida-investimento",
    )
    registrar_log(
        operacao=operacao, entidade="investimento_transacao", objeto_id=transacao.id, acao="criacao",
        usuario=usuario, valor_para=f"Resgate de R$ {valor} de {conta_investimento}"
        + (f" (líquido de R$ {iof} de IOF)" if iof > 0 else ""),
    )

    if iof > 0:
        # Só entra no DRE (natureza despesa_financeira) — NÃO gera
        # MovimentoContaInvestimento próprio, pra não descontar o saldo do
        # investimento 2 vezes (o resgate acima já levou o valor bruto
        # inteiro). `transacao_origem` liga esse registro ao resgate, pra
        # estornar o resgate também estornar o IOF junto (ver abaixo).
        InvestimentoTransacao.objects.create(
            operacao=operacao, conta_investimento=conta_investimento, categoria=conta_investimento.categoria_iof,
            tipo="taxa", valor=iof, data=data, transacao_origem=transacao,
            observacao=f"IOF automático retido no resgate #{transacao.id}", usuario=usuario,
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

    # Resgate com IOF automático tem uma taxa "filha" (transacao_origem) sem
    # ledger próprio — estornar o resgate sozinho deixaria esse IOF fantasma
    # no DRE. Estorna ela junto (não tem movimento pra reverter, só marca).
    for taxa_derivada in transacao.taxas_derivadas.filter(estornada=False):
        taxa_derivada.estornada = True
        taxa_derivada.estornada_em = timezone.now()
        taxa_derivada.estornada_por = usuario
        taxa_derivada.observacao = f"{taxa_derivada.observacao}\n[estornada junto do resgate #{transacao.id}]".strip()
        taxa_derivada.save(update_fields=["estornada", "estornada_em", "estornada_por", "observacao"])

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
