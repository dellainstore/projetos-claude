"""View de Aprovações Admin — porta da page 3_Aprovacoes_Admin.py."""
import json
import time
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from apps.core.decorators import papel_required


@papel_required("superadmin", "gestor")
def view_aprovacoes(request: HttpRequest) -> HttpResponse:
    from apps.produtos.services.db import get_conn
    from apps.produtos.services.business.suppliers import build_supplier_options

    with get_conn() as conn:
        extra_sup = [r[0] for r in conn.execute(
            "SELECT DISTINCT supplier_name FROM stock_moves WHERE supplier_name IS NOT NULL"
        ).fetchall()]
        suppliers = build_supplier_options(extra_sup)

        pendentes = conn.execute(
            """
            SELECT request_id, payload_json, status, created_at, type, template_product_id, created_by
            FROM requests
            WHERE status = 'PENDING'
            ORDER BY request_id DESC
            LIMIT 100
            """
        ).fetchall()

    from apps.produtos.services.business.template_picker import get_default_template_for_base, format_template_label

    requests_list = []
    for row in pendentes:
        payload = json.loads(row["payload_json"] or "{}")
        base = (payload.get("base") or "").strip().upper()

        template_product_id = row["template_product_id"]
        default_tpl = get_default_template_for_base(base) if not template_product_id else None

        resolved_id = template_product_id or (default_tpl["id"] if default_tpl else None)
        resolved_label = ""
        if template_product_id:
            resolved_label = f"ID {template_product_id}"
        elif default_tpl:
            resolved_label = format_template_label(default_tpl)

        requests_list.append({
            "request_id": row["request_id"],
            "type": row["type"],
            "status": row["status"],
            "created_at": row["created_at"],
            "created_by": row["created_by"],
            "template_product_id": resolved_id,
            "template_label": resolved_label,
            "tem_template": bool(resolved_id),
            "base": base,
            "items": payload.get("items", []),
            "payload": payload,
        })

    return render(request, "produtos/aprovacoes.html", {
        "requests_list": requests_list,
        "suppliers": suppliers,
    })


@papel_required("superadmin", "gestor")
@require_POST
def view_aprovar(request: HttpRequest, request_id: int) -> HttpResponse:
    from apps.produtos.services.db import get_conn
    from apps.produtos.services.business.process_approved_requests import processar_aprovacao

    acao = request.POST.get("acao", "")  # "aprovar" ou "rejeitar"

    if acao == "rejeitar":
        with get_conn() as conn:
            conn.execute(
                "UPDATE requests SET status='REJECTED', approved_by=?, updated_at=? WHERE request_id=?",
                (request.user.username, int(time.time()), request_id),
            )
            conn.commit()
        messages.success(request, f"Solicitação #{request_id} rejeitada.")
        return redirect("produtos:aprovacoes")

    # Coletar campos editáveis individualmente
    base_override = request.POST.get("base_override", "").strip().upper() or None

    item_count = 0
    try:
        item_count = int(request.POST.get("item_count", "0"))
    except (ValueError, TypeError):
        pass

    items_editados = []
    for i in range(item_count):
        color = request.POST.get(f"item_color_{i}", "").strip().upper()
        size = request.POST.get(f"item_size_{i}", "").strip().upper()
        supplier = request.POST.get(f"item_supplier_{i}", "").strip().upper()
        try:
            qty = int(request.POST.get(f"item_qty_{i}", "0"))
        except (ValueError, TypeError):
            qty = 0
        if qty > 0 and color and size:
            items_editados.append({"color": color, "size": size, "qty": qty, "supplier_name": supplier})

    items_override = items_editados if items_editados else None

    template_id_override = None
    try:
        raw = request.POST.get("template_product_id_override", "").strip()
        if raw.isdigit():
            template_id_override = int(raw)
    except (ValueError, TypeError):
        pass

    try:
        from apps.produtos.services.business.process_stock_moves import processar_stock_moves

        resultado = processar_aprovacao(
            request_id=request_id,
            approved_by=request.user.username,
            items_override=items_override,
            base_override=base_override,
            template_id_override=template_id_override,
        )

        # Processa imediatamente os stock_moves gerados
        r2 = processar_stock_moves(limit=50)

        ok = resultado.get("ok", 0)
        erros = resultado.get("error", 0)
        moves_ok = r2.get("ok", 0)
        moves_err = r2.get("error", 0)

        if erros or moves_err:
            messages.warning(
                request,
                f"Aprovado #{request_id}: {ok} produto(s), {moves_ok} lançamento(s) de estoque. "
                f"{erros + moves_err} erro(s)."
            )
        else:
            messages.success(
                request,
                f"Aprovado #{request_id}: {ok} produto(s) criado(s), {moves_ok} lançamento(s) aplicado(s)."
            )
    except Exception as exc:
        messages.error(request, f"Erro ao aprovar #{request_id}: {exc}")

    return redirect("produtos:aprovacoes")
