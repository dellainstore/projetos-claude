from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.estoque.services.aggregations import construir_visao_sku


@perm_required("estoque_analise.ver")
def view_previsao(request):
    df = construir_visao_sku()

    relevante = df[(df["estoque_atual"] > 0) & (df["vendido_total_periodo"] > 0)]
    relevante = relevante[(relevante["vendido_30d"] > 0) | (relevante["vendido_30d_anterior"] > 0)]

    if relevante.empty:
        return render(request, "estoque/previsao.html", {"vazio": True})

    subiram = int((relevante["tendencia"] == "aumento").sum())
    cairam = int((relevante["tendencia"] == "queda").sum())
    estaveis = int((relevante["tendencia"] == "estavel").sum())

    up_df = relevante[relevante["tendencia"] == "aumento"].sort_values(
        ["variacao_percentual_30d", "vendido_total_periodo"], ascending=[False, False]
    ).head(30)
    down_df = relevante[relevante["tendencia"] == "queda"].sort_values(
        ["variacao_percentual_30d", "vendido_total_periodo"], ascending=[True, False]
    ).head(30)

    return render(request, "estoque/previsao.html", {
        "vazio": False,
        "subiram": subiram,
        "cairam": cairam,
        "estaveis": estaveis,
        "linhas_subiram": up_df.to_dict("records"),
        "linhas_cairam": down_df.to_dict("records"),
    })
