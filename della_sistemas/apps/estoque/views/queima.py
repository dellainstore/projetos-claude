from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.estoque.services.aggregations import construir_visao_sku


@perm_required("estoque_analise.ver")
def view_queima(request):
    df = construir_visao_sku()

    queima_df = df[df["estoque_atual"] > 0]
    queima_df = queima_df[queima_df["dias_sem_venda"] >= 30]

    if queima_df.empty:
        return render(request, "estoque/queima.html", {"vazio": True})

    valor_parado = float(queima_df["valor_total_custo"].sum())
    qtd_90 = int((queima_df["dias_sem_venda"] >= 90).sum())
    qtd_180 = int((queima_df["dias_sem_venda"] > 180).sum())

    acao_df = queima_df.copy()
    acao_df["acao_sugerida"] = "manter"
    acao_df.loc[(acao_df["dias_sem_venda"] > 90) & (acao_df["media_venda_mensal_historica"] <= 1), "acao_sugerida"] = "liquidar"
    acao_df.loc[(acao_df["dias_sem_venda"] > 60) & (acao_df["vendido_total_periodo"] >= 20), "acao_sugerida"] = "avaliar reposição futura"

    display_df = acao_df.sort_values(["dias_sem_venda", "valor_total_custo"], ascending=[False, False]).head(150)

    return render(request, "estoque/queima.html", {
        "vazio": False,
        "valor_parado": valor_parado,
        "qtd_90": qtd_90,
        "qtd_180": qtd_180,
        "linhas": display_df.to_dict("records"),
    })
