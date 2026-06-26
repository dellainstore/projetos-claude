from datetime import date

from django.shortcuts import render

from apps.core.decorators import login_obrigatorio


@login_obrigatorio
def view_resumo_produtos(request):
    stats = _get_stats()
    ultimas = _get_ultimas_inclusoes()
    return render(request, "produtos/resumo.html", {
        "stats": stats,
        "ultimas_inclusoes": ultimas,
    })


def _get_stats() -> dict:
    try:
        from apps.produtos.services.db import get_conn
        hoje = date.today().strftime("%Y-%m-%d")
        ano_mes = date.today().strftime("%Y-%m")
        with get_conn() as conn:
            pendentes = conn.execute(
                "SELECT COUNT(*) FROM requests WHERE status = 'PENDING'"
            ).fetchone()[0]
            incluidos_hoje = conn.execute(
                "SELECT COUNT(*) FROM stock_moves WHERE date(requested_at,'unixepoch') = ?",
                (hoje,),
            ).fetchone()[0]
            aprovados_mes = conn.execute(
                "SELECT COUNT(*) FROM requests WHERE status = 'IMPLEMENTED'"
                " AND strftime('%Y-%m', datetime(updated_at,'unixepoch')) = ?",
                (ano_mes,),
            ).fetchone()[0]
            total_produtos = conn.execute(
                "SELECT COUNT(*) FROM variants_cache WHERE active = 1"
            ).fetchone()[0]
    except Exception:
        pendentes = incluidos_hoje = aprovados_mes = total_produtos = 0

    return {
        "pendentes": pendentes,
        "incluidos_hoje": incluidos_hoje,
        "aprovados_mes": aprovados_mes,
        "total_produtos": total_produtos,
    }


def _get_ultimas_inclusoes(limit: int = 8) -> list[dict]:
    try:
        import datetime
        import json
        from apps.produtos.services.db import get_conn
        conn = get_conn()
        rows = conn.execute(
            "SELECT request_id, created_by, status, created_at, payload_json "
            "FROM requests ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        result = []
        for row in rows:
            payload = json.loads(row[4]) if row[4] else {}
            nome = payload.get("base") or payload.get("produto_nome") or payload.get("base_nome") or "—"
            items = payload.get("items") or []
            qtd = sum(i.get("qty", 0) for i in items) if items else (payload.get("quantidade") or "—")
            ts = row[3]
            dt = datetime.datetime.fromtimestamp(ts) if isinstance(ts, (int, float)) else datetime.datetime.fromisoformat(str(ts))
            result.append({
                "request_id": row[0],
                "created_by": row[1],
                "status": row[2],
                "produto_nome": nome,
                "qtd": qtd,
                "data": dt.strftime("%d/%m/%Y %H:%M"),
            })
        return result
    except Exception:
        return []
