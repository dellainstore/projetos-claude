"""View de Histórico de Inclusões — porta da page 8_Historico_Inclusoes.py."""
import json
from datetime import datetime, timedelta, date
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect
from django.contrib import messages
from django.views.decorators.http import require_POST

from apps.core.decorators import login_obrigatorio, papel_required


@login_obrigatorio
def view_historico(request: HttpRequest) -> HttpResponse:
    from apps.produtos.services.db import get_conn
    from apps.produtos.services.business.suppliers import build_supplier_options

    today = datetime.now()
    hoje = date.today()

    # Filtros via GET
    periodo = request.GET.get("periodo", "7dias")
    status_filtro = request.GET.getlist("status") or ["DONE", "PENDING", "ERROR"]
    produto_like = request.GET.get("produto", "").strip()
    supplier_filtro = request.GET.getlist("fornecedor")
    data_inicio_str = request.GET.get("data_inicio", "")
    data_fim_str = request.GET.get("data_fim", "")

    # Calcular intervalo
    if periodo == "hoje":
        start_dt = datetime(hoje.year, hoje.month, hoje.day)
        end_dt = start_dt + timedelta(days=1)
    elif periodo == "ontem":
        ontem = hoje - timedelta(days=1)
        start_dt = datetime(ontem.year, ontem.month, ontem.day)
        end_dt = start_dt + timedelta(days=1)
    elif periodo == "7dias":
        end_dt = datetime(hoje.year, hoje.month, hoje.day) + timedelta(days=1)
        start_dt = end_dt - timedelta(days=7)
    elif periodo == "30dias":
        end_dt = datetime(hoje.year, hoje.month, hoje.day) + timedelta(days=1)
        start_dt = end_dt - timedelta(days=30)
    elif periodo == "60dias":
        end_dt = datetime(hoje.year, hoje.month, hoje.day) + timedelta(days=1)
        start_dt = end_dt - timedelta(days=60)
    elif periodo == "personalizado":
        try:
            start_dt = datetime.strptime(data_inicio_str, "%Y-%m-%d")
        except (ValueError, TypeError):
            start_dt = datetime(hoje.year, hoje.month, 1)
        try:
            end_dt = datetime.strptime(data_fim_str, "%Y-%m-%d") + timedelta(days=1)
        except (ValueError, TypeError):
            end_dt = datetime(hoje.year, hoje.month, hoje.day) + timedelta(days=1)
    else:
        end_dt = datetime(hoje.year, hoje.month, hoje.day) + timedelta(days=1)
        start_dt = end_dt - timedelta(days=7)

    with get_conn() as conn:
        extra_sup = [r[0] for r in conn.execute(
            "SELECT DISTINCT supplier_name FROM stock_moves WHERE supplier_name IS NOT NULL"
        ).fetchall()]
        suppliers = build_supplier_options(extra_sup)

        sql = """
        SELECT sm.move_id,
               COALESCE(sm.requested_at, sm.created_at) as ts,
               COALESCE(NULLIF(sm.sku, ''), vc.sku) as sku,
               sm.supplier_name,
               sm.base_name,
               sm.color_key,
               sm.size_key,
               sm.qty_delta,
               sm.status,
               sm.price_varejo,
               sm.price_custo,
               sm.result_json
        FROM stock_moves sm
        LEFT JOIN variants_cache vc
          ON vc.base_name = sm.base_name
         AND vc.color_key = sm.color_key
         AND vc.size_key = sm.size_key
         AND vc.active = 1
        WHERE COALESCE(sm.requested_at, sm.created_at) >= ?
          AND COALESCE(sm.requested_at, sm.created_at) < ?
        """
        params: list = [int(start_dt.timestamp()), int(end_dt.timestamp())]

        if supplier_filtro:
            sql += f" AND UPPER(COALESCE(sm.supplier_name,'')) IN ({','.join(['?']*len(supplier_filtro))})"
            params.extend([s.upper() for s in supplier_filtro])
        if status_filtro:
            sql += f" AND sm.status IN ({','.join(['?']*len(status_filtro))})"
            params.extend(status_filtro)
        if produto_like:
            sql += " AND UPPER(COALESCE(sm.base_name,'')) LIKE ?"
            params.append(f"%{produto_like.upper()}%")

        sql += " ORDER BY ts DESC LIMIT 5000"
        rows = conn.execute(sql, params).fetchall()

    tabela = []
    for row in rows:
        ts = row["ts"]
        data_str = datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M") if ts else "-"
        erro = ""
        if row["status"] == "ERROR":
            try:
                parsed = json.loads(row["result_json"] or "{}")
                erro = str(parsed.get("error") or row["result_json"] or "")
            except Exception:
                erro = str(row["result_json"] or "")

        tabela.append({
            "move_id": row["move_id"],
            "data": data_str,
            "sku": (row["sku"] or "-").strip() or "-",
            "fornecedor": row["supplier_name"] or "-",
            "produto": row["base_name"] or "-",
            "cor": row["color_key"] or "-",
            "tamanho": row["size_key"] or "-",
            "qty": int(row["qty_delta"] or 0),
            "status": row["status"],
            "varejo": row["price_varejo"],
            "custo": row["price_custo"],
            "erro": erro,
        })

    # Resumo por fornecedor/produto/tamanho
    agg: dict = {}
    for r in tabela:
        k = (r["fornecedor"], r["produto"], r["tamanho"])
        agg[k] = agg.get(k, 0) + r["qty"]
    resumo = sorted(
        [{"fornecedor": k[0], "produto": k[1], "tamanho": k[2], "qty": v} for k, v in agg.items()],
        key=lambda x: (x["fornecedor"], x["produto"], x["tamanho"]),
    )

    return render(request, "produtos/historico.html", {
        "tabela": tabela,
        "resumo": resumo,
        "suppliers": suppliers,
        "filtros": {
            "periodo": periodo,
            "status": status_filtro,
            "produto": produto_like,
            "fornecedor": supplier_filtro,
            "data_inicio": data_inicio_str,
            "data_fim": data_fim_str,
        },
        "status_opcoes": [("DONE", "Concluído"), ("PENDING", "Pendente"), ("ERROR", "Erro")],
        "periodos": [
            ("hoje", "Hoje"),
            ("ontem", "Ontem"),
            ("7dias", "Últimos 7 dias"),
            ("30dias", "Últimos 30 dias"),
            ("60dias", "Últimos 60 dias"),
            ("personalizado", "Personalizado"),
        ],
    })


@papel_required("superadmin", "gestor")
@require_POST
def view_excluir_move(request: HttpRequest, move_id: int) -> HttpResponse:
    from apps.produtos.services.db import get_conn
    with get_conn() as conn:
        deleted = conn.execute(
            "DELETE FROM stock_moves WHERE move_id = ?", (move_id,)
        ).rowcount
        conn.commit()
    if deleted:
        messages.success(request, f"Lançamento #{move_id} removido.")
    else:
        messages.warning(request, f"Lançamento #{move_id} não encontrado.")
    return redirect("produtos:historico")
