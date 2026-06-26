"""View de Manutenção Admin — porta da page 9_Admin_Manutencao.py."""
import time
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from apps.core.decorators import papel_required


@papel_required("superadmin")
def view_manutencao(request: HttpRequest) -> HttpResponse:
    from apps.produtos.services.db import get_conn
    with get_conn() as conn:
        req_total = conn.execute("SELECT COUNT(*) FROM requests").fetchone()[0]
        mov_total = conn.execute("SELECT COUNT(*) FROM stock_moves").fetchone()[0]
        req_pending = conn.execute("SELECT COUNT(*) FROM requests WHERE status='PENDING'").fetchone()[0]
        req_approved = conn.execute("SELECT COUNT(*) FROM requests WHERE status='APPROVED'").fetchone()[0]
        mov_pending = conn.execute("SELECT COUNT(*) FROM stock_moves WHERE status='PENDING'").fetchone()[0]

    return render(request, "produtos/manutencao.html", {
        "req_total": req_total,
        "mov_total": mov_total,
        "req_pending": req_pending,
        "req_approved": req_approved,
        "mov_pending": mov_pending,
    })


@papel_required("superadmin")
@require_POST
def view_processar_pipeline(request: HttpRequest) -> HttpResponse:
    from apps.produtos.services.business.process_approved_requests import processar_requests_aprovados
    from apps.produtos.services.business.process_stock_moves import processar_stock_moves
    try:
        r1 = processar_requests_aprovados(limit=20)
        r2 = processar_stock_moves(limit=50)
        criados = r1.get("created_products", 0)
        moves_ok = r2.get("ok", 0)
        erros = len(r1.get("errors", [])) + r2.get("error", 0)
        msg = f"Pipeline: {criados} produto(s) criado(s), {moves_ok} estoque(s) lançado(s)"
        if erros:
            messages.warning(request, f"{msg} — {erros} erro(s).")
        else:
            messages.success(request, f"{msg}.")
    except Exception as exc:
        messages.error(request, f"Erro no pipeline: {exc}")
    return redirect("produtos:manutencao")


@papel_required("superadmin")
@require_POST
def view_sync_catalogo(request: HttpRequest) -> HttpResponse:
    from apps.produtos.services.bling.sync import sync_products
    from apps.produtos.services.business.catalog import rebuild_variants_from_products
    try:
        limit = int(request.POST.get("limit", 50))
        sync_result = sync_products(limit_per_page=limit)
        rebuild_result = rebuild_variants_from_products()
        messages.success(
            request,
            f"Sincronização concluída. Sync: {sync_result.get('total', 0)} produtos. "
            f"Rebuild: {rebuild_result.get('total', 0)} variantes."
        )
    except Exception as exc:
        messages.error(request, f"Erro na sincronização: {exc}")
    return redirect("produtos:manutencao")


@papel_required("superadmin")
@require_POST
def view_rebuild_variacoes(request: HttpRequest) -> HttpResponse:
    from apps.produtos.services.business.catalog import rebuild_variants_from_products
    try:
        result = rebuild_variants_from_products()
        messages.success(request, f"Rebuild concluído: {result.get('total', 0)} variantes reconstruídas.")
    except Exception as exc:
        messages.error(request, f"Erro no rebuild: {exc}")
    return redirect("produtos:manutencao")


@papel_required("superadmin")
@require_POST
def view_limpeza(request: HttpRequest) -> HttpResponse:
    from apps.produtos.services.db import get_conn
    modo = request.POST.get("modo", "")
    confirmado = request.POST.get("confirmar") == "1"

    if not confirmado:
        messages.warning(request, "Marque a confirmação para executar a limpeza.")
        return redirect("produtos:manutencao")

    with get_conn() as conn:
        if modo == "pendentes_erro":
            dr = conn.execute("DELETE FROM requests WHERE status IN ('PENDING','ERROR','REJECTED')").rowcount
            dm = conn.execute("DELETE FROM stock_moves WHERE status IN ('PENDING','ERROR','REJECTED')").rowcount
            conn.commit()
            messages.success(request, f"Limpeza concluída. Requests: {dr} | Moves: {dm}")

        elif modo == "reset_total":
            dr = conn.execute("DELETE FROM requests").rowcount
            dm = conn.execute("DELETE FROM stock_moves").rowcount
            conn.execute("DELETE FROM sqlite_sequence WHERE name IN ('requests','stock_moves')")
            conn.commit()
            messages.warning(request, f"Reset total concluído. Requests: {dr} | Moves: {dm}")

        elif modo == "periodo":
            horas = int(request.POST.get("horas", 24))
            cutoff = int(time.time()) - (horas * 3600)
            dr = conn.execute(
                "DELETE FROM requests WHERE COALESCE(created_at, 0) >= ?", (cutoff,)
            ).rowcount
            dm = conn.execute(
                "DELETE FROM stock_moves WHERE COALESCE(created_at, 0) >= ?", (cutoff,)
            ).rowcount
            conn.commit()
            messages.success(
                request,
                f"Limpeza das últimas {horas}h concluída. Requests: {dr} | Moves: {dm}"
            )
        else:
            messages.error(request, "Modo de limpeza inválido.")

    return redirect("produtos:manutencao")
