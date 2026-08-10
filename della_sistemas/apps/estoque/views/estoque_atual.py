from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.estoque.services.aggregations import construir_visao_estoque_atual

from ._common import paginar


@perm_required("estoque_analise.ver")
def view_estoque_atual(request):
    df = construir_visao_estoque_atual()

    total_skus = int(df["sku"].nunique())
    skus_positivos = int((df["estoque_atual"] > 0).sum())
    pecas_positivas = float(df.loc[df["estoque_atual"] > 0, "estoque_atual"].sum())
    skus_zerados = int((df["estoque_atual"] == 0).sum())
    skus_negativos = int((df["estoque_atual"] < 0).sum())
    pecas_negativas_abs = float(df.loc[df["estoque_atual"] < 0, "estoque_atual"].abs().sum())

    filtro = request.GET.get("filtro", "todos")
    view = df.copy()
    if filtro == "positivos":
        view = view[view["estoque_atual"] > 0]
    elif filtro == "zerados":
        view = view[view["estoque_atual"] == 0]
    elif filtro == "negativos":
        view = view[view["estoque_atual"] < 0]

    view = view.sort_values(["estoque_atual", "sku"], ascending=[True, True])
    pagina = paginar(request, view.to_dict("records"))

    return render(request, "estoque/estoque_atual.html", {
        "total_skus": total_skus,
        "skus_positivos": skus_positivos,
        "pecas_positivas": pecas_positivas,
        "skus_zerados": skus_zerados,
        "skus_negativos": skus_negativos,
        "pecas_negativas_abs": pecas_negativas_abs,
        "filtro": filtro,
        "pagina": pagina,
    })
