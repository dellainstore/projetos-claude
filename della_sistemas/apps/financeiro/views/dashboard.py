import json

from django.http import HttpRequest
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.financeiro.services import relatorio as svc

MESES_ABREV = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def _periodo_label(anos_sel: list[int], meses_sel: list[int]) -> str:
    if not anos_sel:
        return "Sem dados"
    anos_str = ", ".join(str(a) for a in anos_sel)
    if not meses_sel:
        return f"Anos {anos_str}" if len(anos_sel) > 1 else f"Ano {anos_str}"
    meses_str = ", ".join(MESES_ABREV[m - 1] for m in meses_sel)
    return f"{meses_str} / {anos_str}"


def _rotulo_dropdown(prefixo: str, sel: list[int], todas_opcoes_label: str, labels: list[str] | None = None) -> str:
    if not sel:
        return f"{prefixo}: {todas_opcoes_label}"
    textos = [labels[v - 1] for v in sel] if labels else [str(v) for v in sel]
    return f"{prefixo}: " + ", ".join(textos)


def _montar_contexto(request: HttpRequest) -> dict:
    anos_todos = svc.anos_disponiveis()

    anos_raw = request.GET.getlist("anos")
    anos_sel = sorted({int(a) for a in anos_raw if a.isdigit() and int(a) in anos_todos})
    if not anos_sel:
        anos_sel = anos_todos[-1:]

    meses_todos_sel = svc.meses_disponiveis(anos_sel)
    meses_raw = request.GET.getlist("meses")
    meses_sel = sorted({int(m) for m in meses_raw if m.isdigit() and int(m) in meses_todos_sel})

    pedidos = svc.carregar_pedidos(anos_sel, meses_sel or None)
    produtos_df = svc.carregar_vendas_produtos(anos_sel, meses_sel or None)
    cards = svc.resumo_cards(pedidos, produtos_df)
    ranking_valor = svc.ranking_produtos(produtos_df, "valor")
    ranking_qtd = svc.ranking_produtos(produtos_df, "quantidade")
    loja = svc.vendas_por_loja(pedidos)

    ano_grafico = max(anos_sel) if anos_sel else None
    meses_grafico = svc.meses_disponiveis([ano_grafico]) if ano_grafico else []

    labels_corte: list[str] = []
    valores_corte: list[float] = []
    valores_ant_corte: list[float] = []
    tem_ano_anterior = False
    if ano_grafico and meses_grafico:
        mensal = svc.faturamento_mensal(ano_grafico)
        mensal_anterior = svc.faturamento_mensal(ano_grafico - 1)
        idxs = [m - 1 for m in meses_grafico]
        labels_corte = [mensal["labels"][i] for i in idxs]
        valores_corte = [mensal["valores"][i] for i in idxs]
        valores_ant_corte = [mensal_anterior["valores"][i] for i in idxs]
        tem_ano_anterior = any(v > 0 for v in valores_ant_corte)

    grafico_json = json.dumps({
        "labels": labels_corte,
        "valores": valores_corte,
        "valoresAnoAnterior": valores_ant_corte if tem_ano_anterior else None,
        "anoAnterior": (ano_grafico - 1) if ano_grafico else None,
        "anoGrafico": ano_grafico,
        "mesesDisponiveis": meses_grafico,
        "anosSelecionados": anos_sel,
        "mesesSelecionados": meses_sel,
        "lojaLabels": [item["canal"] for item in loja],
        "lojaValores": [item["valor"] for item in loja],
    })

    return {
        "anos_todos": anos_todos,
        "anos_sel": anos_sel,
        "meses_opcoes": [(m, MESES_ABREV[m - 1]) for m in meses_todos_sel],
        "meses_sel": meses_sel,
        "ano_botao_label": _rotulo_dropdown("Ano", anos_sel, "—"),
        "mes_botao_label": _rotulo_dropdown("Mês", meses_sel, "Todos", MESES_ABREV),
        "periodo_label": _periodo_label(anos_sel, meses_sel),
        "cards": cards,
        "ranking_valor": ranking_valor,
        "ranking_qtd": ranking_qtd,
        "loja": loja,
        "grafico_json": grafico_json,
    }


@perm_required("financeiro.ver")
def view_dashboard_faturamento(request: HttpRequest):
    ctx = _montar_contexto(request)
    return render(request, "financeiro/dashboard_faturamento.html", ctx)


@perm_required("financeiro.ver")
def htmx_dashboard_dados(request: HttpRequest):
    ctx = _montar_contexto(request)
    return render(request, "financeiro/_dashboard_conteudo.html", ctx)
