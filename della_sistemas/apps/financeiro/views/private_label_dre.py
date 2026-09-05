"""DRE gerencial (Fase 1C) — ver `services/private_label/dre.py`."""
import csv
from datetime import date

from django.http import HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.core.templatetags.core_extras import brl
from apps.financeiro.services.private_label.dre import (
    LABEL_NATUREZA,
    NATUREZAS_DRE,
    calcular_dre_ano,
    calcular_dre_mes,
)
from apps.financeiro.services.private_label.operacao import obter_operacao_padrao

MESES_PT = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

LINHAS_RESUMO = [
    ("receita_bruta", "Receita Bruta", 0),
    ("deducoes", "(-) Deduções", 1),
    ("receita_liquida", "(=) Receita Líquida", 0),
    ("custos", "(-) Custos", 1),
    ("lucro_bruto", "(=) Lucro Bruto", 0),
    ("despesas_operacionais", "(-) Despesas Operacionais", 1),
    ("resultado_operacional", "(=) Resultado Operacional", 0),
    ("receitas_financeiras", "(+) Receitas Financeiras", 1),
    ("despesas_financeiras", "(-) Despesas Financeiras", 1),
    ("resultado_liquido", "(=) Resultado Líquido", 0),
]


@perm_required("private_label.ver_dre")
def pl_dre(request):
    operacao = obter_operacao_padrao()
    hoje = date.today()
    ano = int(request.GET.get("ano") or hoje.year)
    mes_raw = request.GET.get("mes")
    mes = int(mes_raw) if mes_raw else None

    contexto = {
        "ano": ano, "mes": mes, "anos_disponiveis": range(hoje.year - 2, hoje.year + 1),
        "meses": list(enumerate(MESES_PT, start=1)),
        "linhas_resumo": LINHAS_RESUMO, "naturezas_dre": NATUREZAS_DRE, "label_natureza": LABEL_NATUREZA,
    }
    if mes:
        contexto["dre"] = calcular_dre_mes(operacao, ano, mes)
    else:
        contexto["dre_ano"] = calcular_dre_ano(operacao, ano)
    return render(request, "financeiro/private_label/dre.html", contexto)


@perm_required("private_label.ver_dre")
def pl_dre_exportar_csv(request):
    operacao = obter_operacao_padrao()
    hoje = date.today()
    ano = int(request.GET.get("ano") or hoje.year)
    mes_raw = request.GET.get("mes")
    mes = int(mes_raw) if mes_raw else None

    resposta = HttpResponse(content_type="text/csv")
    sufixo = f"{ano}-{mes:02d}" if mes else f"{ano}"
    resposta["Content-Disposition"] = f'attachment; filename="dre_private_label_{sufixo}.csv"'
    writer = csv.writer(resposta, delimiter=";")

    if mes:
        dre = calcular_dre_mes(operacao, ano, mes)
        writer.writerow(["DRE Private Label", f"{mes:02d}/{ano}"])
        writer.writerow([])
        for chave, rotulo, _ in LINHAS_RESUMO:
            writer.writerow([rotulo, brl(dre[chave])])
        writer.writerow([])
        writer.writerow(["Detalhe por categoria"])
        for chave, label in NATUREZAS_DRE:
            for nome_categoria, valor in dre["por_categoria"][chave].items():
                writer.writerow([LABEL_NATUREZA[chave], nome_categoria, brl(valor)])
    else:
        dre_ano = calcular_dre_ano(operacao, ano)
        cabecalho = ["Linha"] + [f"{m:02d}/{ano}" for m in range(1, 13)] + ["Total"]
        writer.writerow(cabecalho)
        for chave, rotulo, _ in LINHAS_RESUMO:
            linha = [rotulo] + [brl(mes_dre[chave]) for mes_dre in dre_ano["meses"]] + [brl(dre_ano["total"][chave])]
            writer.writerow(linha)

    return resposta
