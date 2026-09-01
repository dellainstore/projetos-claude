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
from django.db.models import Sum
from django.utils import timezone

from apps.financeiro.models import (
    ESTADO_ABERTO,
    ESTADO_CANCELADO,
    ESTADO_QUITADO,
    Baixa,
    LancamentoFinanceiro,
    Parcela,
)
from .auditoria import registrar_log
from .baixas import dar_baixa
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

    # Parcela.conta_prevista fica em branco na criação — ela só existe pra
    # override pontual de UMA parcela (ver `editar_parcela`). Enquanto em
    # branco, `conta_prevista_efetiva` cai no `conta_prevista` do
    # lançamento (este, sim, o "padrão" de fato), então mudar o padrão do
    # lançamento depois continua valendo pra toda parcela que não foi
    # ajustada individualmente.
    valores = gerar_valores_parcelas(valor_original, parcelas_qtd)
    vencimento = primeiro_vencimento
    for numero, valor in enumerate(valores, start=1):
        Parcela.objects.create(lancamento=lancamento, numero=numero, valor=valor, data_vencimento=vencimento)
        vencimento = somar_periodo(vencimento, frequencia_parcelas)

    registrar_log(
        operacao=operacao, entidade="lancamento", objeto_id=lancamento.id, acao="criacao",
        usuario=usuario, valor_para=f"R$ {valor_original} em {parcelas_qtd}x",
    )

    # Pedido do dono (2026-09-02): lançamento com data no passado é
    # histórico (já aconteceu), não uma pendência — já entra como
    # pago/recebido automaticamente, sem precisar dar baixa manual depois.
    # Data de hoje ou futura continua "a pagar"/"a receber" até baixar.
    # Só dá pra baixar automaticamente quando há uma conta informada (baixa
    # exige conta real) — sem conta, fica em aberto mesmo com data passada
    # (aparece como "Vencido"; o usuário informa a conta na hora de baixar).
    if conta_prevista is not None:
        hoje = timezone.localdate()
        for parcela in lancamento.parcelas.all():
            if parcela.data_vencimento < hoje:
                dar_baixa(
                    parcela=parcela, valor_principal=parcela.valor, data=parcela.data_vencimento,
                    conta=conta_prevista, forma_pagamento=forma_pagamento, usuario=usuario,
                )

    return lancamento


CAMPOS_EDITAVEIS = [
    "descricao", "contato", "categoria", "centro_custo", "conta_prevista",
    "forma_pagamento", "numero_documento", "observacoes", "tipo",
]


@transaction.atomic
def editar_lancamento(lancamento: LancamentoFinanceiro, *, usuario=None, tags=None, **campos) -> LancamentoFinanceiro:
    if lancamento.estado_estrutural == ESTADO_CANCELADO:
        raise ValueError("Lançamento cancelado não pode ser editado.")
    if "tipo" in campos and campos["tipo"] != lancamento.tipo:
        # Trocar despesa<->receita depois que já existe baixa inverteria o
        # sinal de movimentos já gravados no razão — trava técnica, vale
        # pra qualquer usuário (mesmo superadmin, que só ganha permissão
        # pra trocar tipo antes de qualquer baixa acontecer).
        if Baixa.objects.filter(parcela__lancamento=lancamento).exists():
            raise ValueError(
                "Não dá pra trocar entre despesa e receita depois que já existe baixa registrada nesta série."
            )
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
def editar_parcela(
    parcela: Parcela, *, usuario=None, valor=None, data_vencimento=None, conta_prevista="__manter__",
    ignorar_baixa=False,
) -> Parcela:
    """Edita SÓ esta parcela. `valor` só pode mudar enquanto a parcela não
    tiver nenhuma baixa, a menos que `ignorar_baixa=True` (reservado a
    superadmin, checado na view) — útil pra corrigir um valor errado que já
    foi baixado, sem precisar estornar antes; o saldo restante passa a
    refletir a diferença automaticamente. `data_vencimento` pode mudar
    sempre. `conta_prevista` é a conta prevista DESTA parcela (não a do
    lançamento inteiro — cada parcela tem a sua própria, pra permitir por
    exemplo "parcela 1 sai do Santander, as demais do Itaú" sem afetar as
    outras); passar `None` explicitamente limpa (cai no fallback do
    lançamento), e o sentinela default (não passar o argumento) mantém o
    valor atual sem mexer. Depois de mudar valor, `lancamento.valor_original`
    é recalculado como a soma de todas as parcelas — ele é sempre um espelho
    da soma, nunca editado direto."""
    if parcela.estado_estrutural == ESTADO_CANCELADO:
        raise ValueError("Parcela cancelada não pode ser editada.")
    alterou = []
    if conta_prevista != "__manter__":
        if conta_prevista != parcela.conta_prevista:
            registrar_log(
                operacao=parcela.lancamento.operacao, entidade="parcela", objeto_id=parcela.id,
                acao="edicao", usuario=usuario, campo="conta_prevista",
                valor_de=parcela.conta_prevista, valor_para=conta_prevista,
            )
            parcela.conta_prevista = conta_prevista
            alterou.append("conta_prevista")
    if valor is not None:
        valor = Decimal(valor)
        if valor <= 0:
            raise ValueError("Valor da parcela deve ser maior que zero.")
        if valor != parcela.valor:
            if parcela.valor_baixado_principal > 0 and not ignorar_baixa:
                raise ValueError(
                    "Esta parcela já tem baixa registrada — não dá pra mudar o valor. "
                    "Estorne a baixa primeiro, ou reparcele a série inteira se nenhuma outra parcela tiver baixa."
                )
            registrar_log(
                operacao=parcela.lancamento.operacao, entidade="parcela", objeto_id=parcela.id,
                acao="edicao", usuario=usuario, campo="valor", valor_de=parcela.valor, valor_para=valor,
            )
            parcela.valor = valor
            alterou.append("valor")
    if data_vencimento is not None:
        data_vencimento = normalizar_data(data_vencimento)
        if data_vencimento != parcela.data_vencimento:
            registrar_log(
                operacao=parcela.lancamento.operacao, entidade="parcela", objeto_id=parcela.id,
                acao="edicao", usuario=usuario, campo="data_vencimento",
                valor_de=parcela.data_vencimento, valor_para=data_vencimento,
            )
            parcela.data_vencimento = data_vencimento
            alterou.append("data_vencimento")
    if alterou:
        parcela.save(update_fields=alterou)
        if "valor" in alterou:
            # o saldo restante mudou — o estado (aberto/parcial/quitado)
            # precisa refletir isso agora, não só quando uma baixa nova
            # acontece.
            parcela.recalcular_estado()
            parcela.lancamento.recalcular_estado()
        lancamento = parcela.lancamento
        novo_total = lancamento.parcelas.aggregate(total=Sum("valor"))["total"] or Decimal("0.00")
        if novo_total != lancamento.valor_original:
            lancamento.valor_original = novo_total
            lancamento.save(update_fields=["valor_original", "atualizado_em"])
    return parcela


@transaction.atomic
def reparcelar(
    lancamento: LancamentoFinanceiro, *, usuario=None, novo_valor_total, novas_parcelas_qtd,
    primeiro_vencimento=None, frequencia_parcelas="mensal",
) -> LancamentoFinanceiro:
    """Reparcela a série INTEIRA — pedido do dono: opção de "alterar todas
    as parcelas". Só permitido quando NENHUMA parcela ainda tem baixa
    (nada de dinheiro se moveu ainda); com qualquer baixa registrada, o
    caminho é `editar_parcela` uma a uma, ou estornar antes. Apaga as
    parcelas atuais (nenhuma tem baixa, então `Baixa.parcela=PROTECT` não
    bloqueia) e gera novas do zero com o novo total/quantidade."""
    if Baixa.objects.filter(parcela__lancamento=lancamento).exists():
        raise ValueError(
            "Esta série já tem baixa registrada em alguma parcela — não dá pra reparcelar tudo de uma vez. "
            "Edite parcela por parcela, ou estorne as baixas antes."
        )
    if lancamento.estado_estrutural == ESTADO_CANCELADO:
        raise ValueError("Lançamento cancelado não pode ser reparcelado.")
    novo_valor_total = Decimal(novo_valor_total)
    if novo_valor_total <= 0:
        raise ValueError("Valor total deve ser maior que zero.")
    novas_parcelas_qtd = int(novas_parcelas_qtd)
    if novas_parcelas_qtd < 1:
        raise ValueError("Quantidade de parcelas deve ser pelo menos 1.")

    primeira_parcela_atual = lancamento.parcelas.order_by("numero").first()
    vencimento = normalizar_data(primeiro_vencimento) if primeiro_vencimento else primeira_parcela_atual.data_vencimento
    valor_de = f"R$ {lancamento.valor_original} em {lancamento.parcelas.count()}x"

    lancamento.parcelas.all().delete()
    lancamento.valor_original = novo_valor_total
    lancamento.data_vencimento = vencimento
    lancamento.save(update_fields=["valor_original", "data_vencimento", "atualizado_em"])

    valores = gerar_valores_parcelas(novo_valor_total, novas_parcelas_qtd)
    data_parcela = vencimento
    for numero, valor in enumerate(valores, start=1):
        Parcela.objects.create(lancamento=lancamento, numero=numero, valor=valor, data_vencimento=data_parcela)
        data_parcela = somar_periodo(data_parcela, frequencia_parcelas)

    registrar_log(
        operacao=lancamento.operacao, entidade="lancamento", objeto_id=lancamento.id, acao="edicao",
        usuario=usuario, campo="reparcelamento", valor_de=valor_de,
        valor_para=f"R$ {novo_valor_total} em {novas_parcelas_qtd}x",
    )
    return lancamento


@transaction.atomic
def reparcelar_mantendo_parcelas(
    lancamento: LancamentoFinanceiro, *, usuario=None, novo_valor_total, ignorar_baixa=False,
) -> LancamentoFinanceiro:
    """Corrige o valor total de TODAS as parcelas de uma vez SEM apagar
    nenhuma — pedido do dono: "preciso alterar o valor de todas as
    parcelas, mesmo as pagas, e não quero deletar tudo". Mantém a
    quantidade de parcelas atual (não dá pra mudar quantidade sem apagar
    parcela, e parcela com baixa não pode ser apagada — `Baixa.parcela` é
    PROTECT no banco). Redistribui o novo total entre as parcelas na mesma
    proporção que `gerar_valores_parcelas` já usa (igual, com a diferença
    de centavos na última). Reaproveita `editar_parcela` parcela por
    parcela — mesma trava de permissão dela: só ignora baixa quando
    `ignorar_baixa=True` (reservado a superadmin, checado na view)."""
    parcelas = list(
        lancamento.parcelas.exclude(estado_estrutural=ESTADO_CANCELADO).order_by("numero")
    )
    if not parcelas:
        raise ValueError("Este lançamento não tem parcelas em aberto para reparcelar.")
    novo_valor_total = Decimal(novo_valor_total)
    if novo_valor_total <= 0:
        raise ValueError("Valor total deve ser maior que zero.")
    valor_de = lancamento.valor_original
    valores = gerar_valores_parcelas(novo_valor_total, len(parcelas))
    for parcela, novo_valor in zip(parcelas, valores):
        editar_parcela(parcela, usuario=usuario, valor=novo_valor, ignorar_baixa=ignorar_baixa)
    registrar_log(
        operacao=lancamento.operacao, entidade="lancamento", objeto_id=lancamento.id, acao="edicao",
        usuario=usuario, campo="reparcelamento_mantendo_parcelas",
        valor_de=f"R$ {valor_de}", valor_para=f"R$ {novo_valor_total}",
    )
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
def deletar_lancamento(lancamento: LancamentoFinanceiro, *, usuario=None) -> None:
    """Exclusão DEFINITIVA — só para superadmin (checagem de permissão é
    responsabilidade da view). Só permitida quando o lançamento nunca teve
    nenhuma baixa (nem estornada) — se já mexeu no razão financeiro, a
    integridade do audit trail vem na frente: o caminho passa a ser
    `cancelar_lancamento`, não apagar. `Baixa.parcela` é PROTECT no banco,
    então essa regra também seria barrada na marra pelo banco — aqui só
    devolvemos um erro claro em vez de deixar estourar um IntegrityError."""
    if Baixa.objects.filter(parcela__lancamento=lancamento).exists():
        raise ValueError(
            "Este lançamento já teve baixa registrada (mesmo estornada) — não pode ser excluído "
            "definitivamente, só cancelado (preserva o histórico)."
        )
    registrar_log(
        operacao=lancamento.operacao, entidade="lancamento", objeto_id=lancamento.id,
        acao="exclusao", usuario=usuario, valor_de=lancamento.descricao,
    )
    for anexo in lancamento.anexos.all():
        anexo.arquivo.delete(save=False)
    lancamento.delete()


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
