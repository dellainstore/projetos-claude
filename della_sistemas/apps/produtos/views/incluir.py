"""View para Incluir Estoque — porta da page 1_Incluir_Estoque.py do Streamlit."""
import json
import time
from datetime import datetime
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from apps.core.decorators import login_obrigatorio


def _get_suppliers(conn) -> list[str]:
    from apps.produtos.services.business.suppliers import build_supplier_options
    extra = [r[0] for r in conn.execute(
        "SELECT DISTINCT supplier_name FROM stock_moves WHERE supplier_name IS NOT NULL"
    ).fetchall()]
    return build_supplier_options(extra)


def _get_pendentes_usuario(conn, username: str) -> list[dict]:
    rows = conn.execute(
        """SELECT request_id, payload_json, created_at
           FROM requests
           WHERE created_by = ? AND status = 'PENDING'
           ORDER BY request_id DESC LIMIT 30""",
        (username,),
    ).fetchall()
    result = []
    for row in rows:
        payload = json.loads(row["payload_json"] or "{}")
        result.append({
            "request_id": row["request_id"],
            "base": (payload.get("base") or "").strip().upper(),
            "items": payload.get("items", []),
            "created_at_str": datetime.fromtimestamp(row["created_at"]).strftime("%d/%m %H:%M"),
        })
    return result


@login_obrigatorio
def view_incluir(request: HttpRequest) -> HttpResponse:
    if not request.user.pode_incluir:
        messages.error(request, "Sem permissão para incluir estoque.")
        return redirect("core:home")

    from apps.produtos.services.db import get_conn
    with get_conn() as conn:
        suppliers = _get_suppliers(conn)
        pendentes = _get_pendentes_usuario(conn, request.user.username)

    ctx = {
        "suppliers": suppliers,
        "flash": request.session.pop("incluir_flash", None),
        "pendentes": pendentes,
    }
    return render(request, "produtos/incluir.html", ctx)


@login_obrigatorio
def htmx_buscar_bases(request: HttpRequest) -> HttpResponse:
    """HTMX: retorna opções de modelos para o autocomplete."""
    from apps.produtos.services.business.lookup import search_base_names
    q = request.GET.get("q", "").strip()
    bases = search_base_names(q, limit=30) if len(q) >= 2 else []
    return render(request, "produtos/_bases_options.html", {"bases": bases, "q": q})


@login_obrigatorio
def htmx_buscar_cores(request: HttpRequest) -> HttpResponse:
    """HTMX: retorna cores disponíveis para um modelo."""
    from apps.produtos.services.business.lookup import get_colors
    base = request.GET.get("base", "").strip().upper()
    cores = get_colors(base) if base else []
    return render(request, "produtos/_cores_options.html", {"cores": cores, "base": base})


@login_obrigatorio
def htmx_buscar_tamanhos(request: HttpRequest) -> HttpResponse:
    """HTMX: retorna tamanhos e preços para base+cor."""
    from apps.produtos.services.business.lookup import get_sizes, get_sku
    from apps.produtos.services.business.pricing import get_product_prices_by_id, get_variant_product_id
    from apps.produtos.services.db import get_conn
    base = request.GET.get("base", "").strip().upper()
    cor = request.GET.get("cor", "").strip().upper()
    tamanhos = get_sizes(base, cor) if base and cor else []
    if not tamanhos:
        tamanhos = ["PP", "P", "M", "G", "GG"]

    # Buscar preços do primeiro tamanho encontrado no Bling
    preco_varejo = preco_custo = None
    for tam in tamanhos:
        pid = get_variant_product_id(base, cor, tam)
        if pid:
            prices = get_product_prices_by_id(int(pid))
            preco_varejo = prices.get("price_varejo")
            preco_custo = prices.get("price_custo")
            break

    # Buscar preço de atacado do price_history local
    preco_atacado = None
    try:
        conn = get_conn()
        row = conn.execute("""
            SELECT valor_novo FROM price_history
            WHERE UPPER(base_name) = ? AND UPPER(color_key) = ?
              AND tipo IN ('atacado', 'atacado_local')
            ORDER BY alterado_em DESC LIMIT 1
        """, (base, cor)).fetchone()
        conn.close()
        if row:
            preco_atacado = row[0]
    except Exception:
        pass

    return render(request, "produtos/_tamanhos_form.html", {
        "tamanhos": tamanhos,
        "preco_varejo": preco_varejo,
        "preco_custo": preco_custo,
        "preco_atacado": preco_atacado,
        "base": base,
        "cor": cor,
    })


@login_obrigatorio
def htmx_buscar_templates(request: HttpRequest) -> HttpResponse:
    """HTMX: retorna templates de produto para seleção (deduplica por cor, sem tamanho)."""
    from apps.produtos.services.business.template_picker import search_templates, format_template_label
    q = request.GET.get("q", "").strip()
    templates = search_templates(q, limit=20, group_mode="base_color") if len(q) >= 2 else []
    for tpl in templates:
        tpl["label"] = format_template_label(tpl)
    return render(request, "produtos/_templates_options.html", {"templates": templates})


@login_obrigatorio
@require_POST
def view_incluir_submit(request: HttpRequest) -> HttpResponse:
    """POST: processa submissão de inclusão de estoque."""
    if not request.user.pode_incluir:
        messages.error(request, "Sem permissão para incluir estoque.")
        return redirect("core:home")

    from apps.produtos.services.db import get_conn
    from apps.produtos.services.business.lookup import (
        get_sku, upsert_pending_variant_request
    )
    from apps.produtos.services.business.product_map import get_id_produto_by_sku
    from apps.produtos.services.business.process_stock_moves import processar_stock_moves

    supplier_name = request.POST.get("supplier_name", "").strip().upper()
    if not supplier_name:
        messages.error(request, "Informe o fornecedor.")
        return redirect("produtos:incluir")

    modo = request.POST.get("modo", "existente")
    base = request.POST.get("base", "").strip().upper()
    cor = request.POST.get("cor", "").strip().upper()
    template_id_raw = request.POST.get("template_id", "")
    template_id = int(template_id_raw) if template_id_raw.strip().isdigit() else None

    if not base or not cor:
        messages.error(request, "Informe o modelo e a cor.")
        return redirect("produtos:incluir")

    # Coletar quantidades (campos qty_TAM)
    qtd_items = {}
    for key, val in request.POST.items():
        if key.startswith("qty_") and key != "qty_":
            tam = key[4:].upper()
            try:
                q = int(val)
                if q > 0:
                    qtd_items[tam] = q
            except ValueError:
                pass

    if not qtd_items:
        messages.warning(request, "Informe ao menos um tamanho com quantidade maior que zero.")
        return redirect("produtos:incluir")

    username = request.user.username
    now = int(time.time())
    move_ids: list[int] = []
    approval_count = 0

    with get_conn() as conn:
        for tam, q in qtd_items.items():
            sku = get_sku(base, cor, tam)
            needs_approval = (modo == "novo") or not sku

            if not needs_approval and sku:
                bling_product_id = get_id_produto_by_sku(sku)
                conn.execute(
                    """
                    INSERT INTO stock_moves
                    (sku, qty_delta, status, created_by, created_at, result_json,
                     base_name, color_key, size_key, supplier_name, requested_at, bling_product_id)
                    VALUES (?, ?, 'PENDING', ?, ?, NULL, ?, ?, ?, ?, ?, ?)
                    """,
                    (sku, q, username, now, base, cor, tam, supplier_name, now, bling_product_id),
                )
                move_ids.append(conn.execute("SELECT last_insert_rowid()").fetchone()[0])
            else:
                upsert_pending_variant_request(
                    base=base,
                    color=cor,
                    size=tam,
                    qty=q,
                    supplier_name=supplier_name,
                    request_type="UPSERT_VARIANT",
                    template_product_id=template_id,
                    created_by=username,
                    conn=conn,
                )
                approval_count += 1

        conn.commit()

    if move_ids:
        processar_stock_moves(created_by=username, move_ids=move_ids)

    msg = (
        f"Incluído! Direto no estoque: {len(move_ids)} item(s). "
        f"Aguardando aprovação: {approval_count} item(s)."
    )
    messages.success(request, msg)
    return redirect("produtos:incluir")


@login_obrigatorio
@require_POST
def view_cancelar_request(request: HttpRequest, request_id: int) -> HttpResponse:
    if not request.user.pode_incluir:
        messages.error(request, "Sem permissão.")
        return redirect("core:home")

    from apps.produtos.services.db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT created_by, status FROM requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row or row["created_by"] != request.user.username or row["status"] != "PENDING":
            messages.error(request, "Solicitação não encontrada ou não pode ser cancelada.")
            return redirect("produtos:incluir")
        conn.execute("DELETE FROM requests WHERE request_id=?", (request_id,))
        conn.commit()

    messages.success(request, f"Solicitação #{request_id} cancelada.")
    return redirect("produtos:incluir")


@login_obrigatorio
@require_POST
def view_editar_request(request: HttpRequest, request_id: int) -> HttpResponse:
    if not request.user.pode_incluir:
        messages.error(request, "Sem permissão.")
        return redirect("core:home")

    from apps.produtos.services.db import get_conn
    with get_conn() as conn:
        row = conn.execute(
            "SELECT created_by, status, payload_json FROM requests WHERE request_id=?", (request_id,)
        ).fetchone()
        if not row or row["created_by"] != request.user.username or row["status"] != "PENDING":
            messages.error(request, "Solicitação não encontrada ou não pode ser editada.")
            return redirect("produtos:incluir")

        payload = json.loads(row["payload_json"] or "{}")
        items = payload.get("items", [])

        new_items = []
        for i, item in enumerate(items):
            val = request.POST.get(f"qty_{i}", "")
            try:
                q = int(val)
                if q > 0:
                    new_items.append({**item, "qty": q})
            except (ValueError, TypeError):
                new_items.append(item)

        if not new_items:
            messages.error(request, "Pelo menos um item deve ter quantidade maior que zero.")
            return redirect("produtos:incluir")

        payload["items"] = new_items
        conn.execute(
            "UPDATE requests SET payload_json=?, updated_at=? WHERE request_id=?",
            (json.dumps(payload), int(time.time()), request_id),
        )
        conn.commit()

    messages.success(request, f"Solicitação #{request_id} atualizada.")
    return redirect("produtos:incluir")
