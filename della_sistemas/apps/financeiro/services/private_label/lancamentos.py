"""Criação, edição, cancelamento e duplicação de lançamentos.

Escopo assumido para a Fase 1A: campos descritivos (descrição, categoria,
contato, centro de custo, forma de pagamento, documento, observações, tags)
podem ser editados livremente enquanto o lançamento não estiver cancelado.
Reestruturar valor/parcelamento de um lançamento que já tem baixa não é
suportado por edição direta — o caminho é cancelar (se possível) e lançar de
novo, mantendo o razão sempre coerente com o que realmente aconteceu.
"""
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.financeiro.models import (
    ESTADO_ABERTO,
    ESTADO_CANCELADO,
    ESTADO_QUITADO,
    LancamentoFinanceiro,
    Parcela,
)
from .auditoria import registrar_log
from .datas import normalizar_data, somar_periodo


def gerar_valores_parcelas(valor_total: Decimal, quantidade: int) -> list[Decimal]:
    """Divide `valor_total` em `quantidade` parcelas iguais; a diferença de
    centavos do arredondamento é sempre absorvida pela ÚLTIMA parcela, de
    forma que a soma bate exatamente com o valor original."""
    quantidade = int(quantidade)
    if quantidade < 1:
        raise ValueError("Quantidade de parcelas deve ser pelo menos 1.")
    valor_unitario = (valor_total / quantidade).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    valores = [valor_unitario] * quantidade
    diferenca = valor_total - (valor_unitario * quantidade)
    valores[-1] = valores[-1] + diferenca
    return valores


@transaction.atomic
def criar_lancamento(
    *, operacao, tipo, descricao, valor_original, data_competencia, primeiro_vencimento,
    categoria, contato=None, centro_custo=None, conta_prevista=None, forma_pagamento=None,
    numero_documento="", observacoes="", tags=None, parcelas_qtd=1, frequencia_parcelas="mensal",
    usuario=None,
) -> LancamentoFinanceiro:
    valor_original = Decimal(valor_original)
    if valor_original <= 0:
        raise ValueError("Valor original deve ser maior que zero.")
    if categoria is None:
        raise ValueError("Categoria é obrigatória.")
    data_competencia = normalizar_data(data_competencia)
    primeiro_vencimento = normalizar_data(primeiro_vencimento)

    lancamento = LancamentoFinanceiro.objects.create(
        operacao=operacao, tipo=tipo, descricao=descricao, contato=contato,
        categoria=categoria, centro_custo=centro_custo, conta_prevista=conta_prevista,
        valor_original=valor_original, data_competencia=data_competencia,
        data_vencimento=primeiro_vencimento, forma_pagamento=forma_pagamento,
        numero_documento=numero_documento, observacoes=observacoes,
        estado_estrutural=ESTADO_ABERTO, criado_por=usuario,
    )
    if tags:
        lancamento.tags.set(tags)

    valores = gerar_valores_parcelas(valor_original, parcelas_qtd)
    vencimento = primeiro_vencimento
    for numero, valor in enumerate(valores, start=1):
        Parcela.objects.create(lancamento=lancamento, numero=numero, valor=valor, data_vencimento=vencimento)
        vencimento = somar_periodo(vencimento, frequencia_parcelas)

    registrar_log(
        operacao=operacao, entidade="lancamento", objeto_id=lancamento.id, acao="criacao",
        usuario=usuario, valor_para=f"R$ {valor_original} em {parcelas_qtd}x",
    )
    return lancamento


CAMPOS_EDITAVEIS = [
    "descricao", "contato", "categoria", "centro_custo", "conta_prevista",
    "forma_pagamento", "numero_documento", "observacoes",
]


@transaction.atomic
def editar_lancamento(lancamento: LancamentoFinanceiro, *, usuario=None, tags=None, **campos) -> LancamentoFinanceiro:
    if lancamento.estado_estrutural == ESTADO_CANCELADO:
        raise ValueError("Lançamento cancelado não pode ser editado.")
    alterados = []
    for campo, novo_valor in campos.items():
        if campo not in CAMPOS_EDITAVEIS:
            raise ValueError(f"Campo '{campo}' não é editável diretamente.")
        valor_atual = getattr(lancamento, campo)
        if valor_atual != novo_valor:
            registrar_log(
                operacao=lancamento.operacao, entidade="lancamento", objeto_id=lancamento.id,
                acao="edicao", usuario=usuario, campo=campo, valor_de=valor_atual, valor_para=novo_valor,
            )
            setattr(lancamento, campo, novo_valor)
            alterados.append(campo)
    if alterados:
        lancamento.save(update_fields=alterados + ["atualizado_em"])
    if tags is not None:
        lancamento.tags.set(tags)
    return lancamento


@transaction.atomic
def cancelar_lancamento(lancamento: LancamentoFinanceiro, *, usuario=None) -> LancamentoFinanceiro:
    if lancamento.estado_estrutural == ESTADO_CANCELADO:
        return lancamento
    if lancamento.parcelas.filter(estado_estrutural=ESTADO_QUITADO).exists() and (
        lancamento.parcelas.exclude(estado_estrutural__in=[ESTADO_QUITADO, ESTADO_CANCELADO]).exists() is False
    ):
        raise ValueError("Lançamento já totalmente quitado não pode ser cancelado.")
    if lancamento.parcelas.filter(estado_estrutural="parcial").exists():
        raise ValueError("Existe parcela com baixa parcial — estorne as baixas antes de cancelar.")
    lancamento.parcelas.exclude(estado_estrutural=ESTADO_QUITADO).update(estado_estrutural=ESTADO_CANCELADO)
    lancamento.estado_estrutural = ESTADO_CANCELADO
    lancamento.cancelado_em = timezone.now()
    lancamento.cancelado_por = usuario
    lancamento.save(update_fields=["estado_estrutural", "cancelado_em", "cancelado_por", "atualizado_em"])
    registrar_log(
        operacao=lancamento.operacao, entidade="lancamento", objeto_id=lancamento.id,
        acao="cancelamento", usuario=usuario,
    )
    return lancamento


@transaction.atomic
def cancelar_parcela(parcela: Parcela, *, usuario=None) -> Parcela:
    if parcela.estado_estrutural == ESTADO_QUITADO:
        raise ValueError("Parcela já quitada não pode ser cancelada.")
    if parcela.valor_baixado_principal > 0:
        raise ValueError("Parcela com baixa (mesmo parcial) — estorne a baixa antes de cancelar.")
    parcela.estado_estrutural = ESTADO_CANCELADO
    parcela.save(update_fields=["estado_estrutural"])
    parcela.lancamento.recalcular_estado()
    registrar_log(
        operacao=parcela.lancamento.operacao, entidade="parcela", objeto_id=parcela.id,
        acao="cancelamento", usuario=usuario,
    )
    return parcela


@transaction.atomic
def duplicar_lancamento(lancamento: LancamentoFinanceiro, *, usuario=None, nova_data_vencimento=None) -> LancamentoFinanceiro:
    """Duplica como um novo lançamento de parcela única — não replica o
    parcelamento original (evita ambiguidade sobre "duplicar a série
    inteira" vs. "duplicar só esta parcela"; o usuário reparcelamento se
    precisar, no próprio modal)."""
    hoje = timezone.localdate()
    return criar_lancamento(
        operacao=lancamento.operacao, tipo=lancamento.tipo, descricao=lancamento.descricao,
        valor_original=lancamento.valor_original, data_competencia=hoje,
        primeiro_vencimento=nova_data_vencimento or hoje,
        categoria=lancamento.categoria, contato=lancamento.contato,
        centro_custo=lancamento.centro_custo, conta_prevista=lancamento.conta_prevista,
        forma_pagamento=lancamento.forma_pagamento, observacoes=lancamento.observacoes,
        tags=list(lancamento.tags.all()), parcelas_qtd=1, usuario=usuario,
    )
