"""DRE gerencial (Fase 1C) — regime de COMPETÊNCIA, não de caixa: reconhece
o valor cheio na `data_competencia` (lançamentos) ou `data_compra` (compras
no cartão), independente de quando foi/será baixado. Transferência,
aplicação/resgate, ajuste de saldo e pagamento de fatura NUNCA entram — a
despesa do cartão já foi reconhecida na compra, não de novo no pagamento.

Juros/multa de `Baixa` não têm competência própria (só existem no
instante da baixa) — entram no mês da PRÓPRIA BAIXA, classificados como
receita_financeira (lançamento tipo receita) ou despesa_financeira
(tipo despesa). Desconto concedido/obtido não entra no DRE nesta fase —
ver plano, seção 16."""
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Sum

from apps.financeiro.models import (
    Baixa,
    CompraCartao,
    ESTADO_CANCELADO,
    InvestimentoTransacao,
    LancamentoFinanceiro,
    NATUREZA_CHOICES,
    TIPOS_ENTRADA,
)

NATUREZAS_DRE = [n for n in NATUREZA_CHOICES if n[0] != "fora_do_dre"]
LABEL_NATUREZA = dict(NATUREZA_CHOICES)


def _dre_vazio():
    return {chave: Decimal("0.00") for chave, _ in NATUREZAS_DRE}


def calcular_dre_mes(operacao, ano: int, mes: int) -> dict:
    """DRE de 1 mês: totais por natureza + detalhe por categoria dentro de
    cada natureza (linha extra "Juros/multa de baixas" quando houver)."""
    totais = _dre_vazio()
    por_categoria: dict[str, "OrderedDict[str, Decimal]"] = {chave: OrderedDict() for chave, _ in NATUREZAS_DRE}

    lancamentos = (
        LancamentoFinanceiro.objects.filter(
            operacao=operacao, data_competencia__year=ano, data_competencia__month=mes,
        )
        .exclude(estado_estrutural=ESTADO_CANCELADO)
        .exclude(categoria__natureza="fora_do_dre")
        .values("categoria__nome", "categoria__natureza")
        .annotate(total=Sum("valor_original"))
    )
    for linha in lancamentos:
        natureza = linha["categoria__natureza"]
        totais[natureza] += linha["total"]
        nome = linha["categoria__nome"]
        por_categoria[natureza][nome] = por_categoria[natureza].get(nome, Decimal("0.00")) + linha["total"]

    compras_cartao = (
        CompraCartao.objects.filter(operacao=operacao, data_compra__year=ano, data_compra__month=mes, cancelada=False)
        .exclude(categoria__natureza="fora_do_dre")
        .values("categoria__nome", "categoria__natureza")
        .annotate(total=Sum("valor_total"))
    )
    for linha in compras_cartao:
        natureza = linha["categoria__natureza"]
        totais[natureza] += linha["total"]
        nome = linha["categoria__nome"]
        por_categoria[natureza][nome] = por_categoria[natureza].get(nome, Decimal("0.00")) + linha["total"]

    # Juros/multa de baixas do mês — sem competência própria (ver docstring).
    baixas = Baixa.objects.filter(
        parcela__lancamento__operacao=operacao, data__year=ano, data__month=mes, estornada=False,
    ).select_related("parcela__lancamento")
    juros_multa_receita = Decimal("0.00")
    juros_multa_despesa = Decimal("0.00")
    for baixa in baixas:
        extra = baixa.juros + baixa.multa
        if extra <= 0:
            continue
        if baixa.parcela.lancamento.tipo in TIPOS_ENTRADA:
            juros_multa_receita += extra
        else:
            juros_multa_despesa += extra
    if juros_multa_receita:
        totais["receita_financeira"] += juros_multa_receita
        por_categoria["receita_financeira"]["Juros/multa recebidos em baixas"] = juros_multa_receita
    if juros_multa_despesa:
        totais["despesa_financeira"] += juros_multa_despesa
        por_categoria["despesa_financeira"]["Juros/multa pagos em baixas"] = juros_multa_despesa

    # Rendimento/taxa de investimentos (Fase 2) — únicas transações de
    # investimento que entram no DRE (aplicação/resgate são remanejamento
    # de patrimônio, ficam fora — ver `services/private_label/investimentos.py`).
    transacoes_investimento = (
        InvestimentoTransacao.objects.filter(
            operacao=operacao, tipo__in=["rendimento", "taxa"], estornada=False,
            data__year=ano, data__month=mes,
        )
        .exclude(categoria__natureza="fora_do_dre")
        .values("categoria__nome", "categoria__natureza")
        .annotate(total=Sum("valor"))
    )
    for linha in transacoes_investimento:
        natureza = linha["categoria__natureza"]
        totais[natureza] += linha["total"]
        nome = linha["categoria__nome"]
        por_categoria[natureza][nome] = por_categoria[natureza].get(nome, Decimal("0.00")) + linha["total"]

    return _montar_resultado(totais, por_categoria)


def _montar_resultado(totais: dict, por_categoria: dict) -> dict:
    receita_bruta = totais["receita"]
    deducoes = totais["deducao"]
    receita_liquida = receita_bruta - deducoes
    custos = totais["custo"]
    lucro_bruto = receita_liquida - custos
    despesas_operacionais = totais["despesa_operacional"]
    resultado_operacional = lucro_bruto - despesas_operacionais
    receitas_financeiras = totais["receita_financeira"]
    despesas_financeiras = totais["despesa_financeira"]
    resultado_liquido = resultado_operacional + receitas_financeiras - despesas_financeiras

    return {
        "totais": totais,
        "por_categoria": por_categoria,
        "receita_bruta": receita_bruta,
        "deducoes": deducoes,
        "receita_liquida": receita_liquida,
        "custos": custos,
        "lucro_bruto": lucro_bruto,
        "despesas_operacionais": despesas_operacionais,
        "resultado_operacional": resultado_operacional,
        "receitas_financeiras": receitas_financeiras,
        "despesas_financeiras": despesas_financeiras,
        "resultado_liquido": resultado_liquido,
    }


def calcular_dre_ano(operacao, ano: int) -> dict:
    """DRE anual = 1 coluna por mês (comparação lado a lado) + coluna Total.
    Reaproveita `calcular_dre_mes` 12x — o volume de dados do Private Label
    não justifica uma query agregada mais esperta ainda."""
    meses = [calcular_dre_mes(operacao, ano, mes) for mes in range(1, 13)]
    linhas_chave = [
        "receita_bruta", "deducoes", "receita_liquida", "custos", "lucro_bruto",
        "despesas_operacionais", "resultado_operacional", "receitas_financeiras",
        "despesas_financeiras", "resultado_liquido",
    ]
    total = {chave: sum((m[chave] for m in meses), Decimal("0.00")) for chave in linhas_chave}
    return {"meses": meses, "total": total, "linhas_chave": linhas_chave}
