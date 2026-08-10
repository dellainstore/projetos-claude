from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.produtos.services.consulta_rapida import buscar_produto_por_sku


@perm_required("consulta_rapida.ver")
def view_consulta_rapida(request: HttpRequest) -> HttpResponse:
    return render(request, "produtos/consulta_rapida.html")


@perm_required("consulta_rapida.ver")
def htmx_consulta_buscar(request: HttpRequest) -> HttpResponse:
    sku = (request.POST.get("sku") or request.GET.get("sku") or "").strip()
    produto = buscar_produto_por_sku(sku) if sku else None
    return render(request, "produtos/_consulta_resultado.html", {
        "sku_buscado": sku,
        "produto": produto,
    })
