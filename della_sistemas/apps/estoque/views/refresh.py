from django.contrib import messages
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from apps.core.decorators import perm_required
from apps.estoque.services.sync import run_manual_refresh


@perm_required("estoque_analise.ver")
@require_POST
def view_atualizar_dados(request):
    destino = request.POST.get("next") or "estoque:estoque_atual"
    try:
        resultado = run_manual_refresh(sales_days=2, workers=3)
    except Exception as exc:
        messages.error(request, f"Falha ao atualizar dados: {exc}")
        return redirect(destino)

    produtos = int(resultado.get("sync_produtos", {}).get("synced", 0))
    estoque = int(resultado.get("sync_estoque", {}).get("synced", 0))
    vendas = int(resultado.get("sync_vendas", {}).get("synced", 0))
    messages.success(
        request,
        f"Atualização concluída — Produtos: {produtos} | Estoque: {estoque} | Vendas recentes: {vendas}",
    )
    return redirect(destino)
