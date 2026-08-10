from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.estoque.services.aggregations import (
    construir_visao_sku,
    top_estoque_parado,
    top_maior_cobertura,
)


@perm_required("estoque_analise.ver")
def view_saude(request):
    df = construir_visao_sku()
    df["dias_cobertura_historico"] = df["dias_cobertura_historico"].clip(lower=0)

    total_skus = int(df["produto_id"].nunique())
    estoque_total_custo = float(df["valor_total_custo"].sum())
    estoque_total_venda = float(df["valor_total_venda"].sum())
    estoque_positivo = int((df["estoque_atual"] > 0).sum())

    alto_baixo_giro = df[
        (df["estoque_atual"] > 0)
        & (df["media_venda_diaria_historica"] > 0)
        & (df["dias_cobertura_historico"] >= 120)
    ]
    negativo_ativo = df[(df["estoque_atual"] < 0) & (df["vendido_30d"] > 0)]
    curto_bom_giro = df[
        (df["estoque_atual"] >= 0)
        & (df["dias_cobertura_historico"] <= 15)
        & (df["vendido_30d"] > 0)
    ]

    main_df = df.copy()
    main_df["prioridade"] = 3
    main_df.loc[(df["estoque_atual"] < 0) & (df["vendido_30d"] > 0), "prioridade"] = 0
    main_df.loc[(df["dias_cobertura_historico"] <= 15) & (df["vendido_30d"] > 0), "prioridade"] = 1
    main_df.loc[(df["dias_cobertura_historico"] >= 120) & (df["estoque_atual"] > 0), "prioridade"] = 2
    main_df = main_df.sort_values(
        ["prioridade", "dias_cobertura_historico", "vendido_total_periodo"],
        ascending=[True, True, False],
    ).head(120)

    top_parado = top_estoque_parado(limit=10)
    top_cob = top_maior_cobertura(limit=10)

    return render(request, "estoque/saude.html", {
        "total_skus": total_skus,
        "estoque_total_custo": estoque_total_custo,
        "estoque_total_venda": estoque_total_venda,
        "estoque_positivo": estoque_positivo,
        "qtd_cobertura_excessiva": len(alto_baixo_giro),
        "qtd_negativo_ativo": len(negativo_ativo),
        "qtd_curto_bom_giro": len(curto_bom_giro),
        "linhas": main_df.to_dict("records"),
        "top_parado": top_parado.to_dict("records"),
        "top_cobertura": top_cob.to_dict("records"),
    })
