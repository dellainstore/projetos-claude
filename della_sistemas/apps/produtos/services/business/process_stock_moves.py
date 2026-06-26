import json
import time
from datetime import datetime

from apps.produtos.services.bling.stock import salvar_lancamento_estoque
from apps.produtos.services.db import get_conn
from apps.produtos.services.business.product_map import get_id_produto_by_sku


def _fmt_dt(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M")


def processar_stock_moves(
    limit: int = 20,
    created_by: str | None = None,
    move_ids: list[int] | None = None,
) -> dict:
    conn = get_conn()
    cur = conn.cursor()

    ids = [int(x) for x in (move_ids or []) if int(x) > 0]

    sql = """
        SELECT move_id, sku, qty_delta, bling_product_id, base_name, color_key, size_key, supplier_name,
               price_varejo, price_custo, price_atacado,
               COALESCE(requested_at, created_at) as req_ts
        FROM stock_moves
        WHERE status = 'PENDING'
    """
    params: list[object] = []
    if created_by:
        sql += " AND created_by = ?"
        params.append(created_by)
    if ids:
        placeholders = ",".join(["?"] * len(ids))
        sql += f" AND move_id IN ({placeholders})"
        params.extend(ids)
    sql += " ORDER BY move_id"
    if not ids:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = cur.execute(sql, tuple(params)).fetchall()

    ok = 0
    erro = 0
    done_moves = []
    error_moves = []

    for move_id, sku, qty_delta, bling_product_id, base_name, color_key, size_key, supplier_name, price_varejo, price_custo, price_atacado, req_ts in rows:
        try:
            id_produto = int(bling_product_id) if bling_product_id else None
            if not id_produto and sku:
                id_produto = get_id_produto_by_sku(sku)
            if not id_produto:
                raise RuntimeError(
                    f"Produto não identificado (move_id={move_id}, sku={sku}). "
                    "Rode Sync/Rebuild para atualizar o cache."
                )

            if int(qty_delta) >= 0:
                tipo = "E"
                quantidade = int(qty_delta)
            else:
                tipo = "S"
                quantidade = abs(int(qty_delta))

            obs = f"Inclusão Automática - {_fmt_dt(int(req_ts))}"

            result = salvar_lancamento_estoque(
                id_produto=id_produto,
                quantidade=quantidade,
                tipo_operacao=tipo,
                observacoes=obs,
            )

            bling_id = None
            try:
                bling_id = (result or {}).get("data", {}).get("id")
            except Exception:
                bling_id = None

            applied_at = int(time.time())

            cur.execute(
                """
                UPDATE stock_moves
                SET status='DONE',
                    result_json=?,
                    applied_at=?,
                    bling_stock_id=?
                WHERE move_id=?
                """,
                (json.dumps(result, ensure_ascii=False), applied_at, bling_id, move_id),
            )
            ok += 1
            done_moves.append(
                {
                    "move_id": move_id,
                    "sku": sku,
                    "qty_delta": int(qty_delta),
                    "base": base_name,
                    "color": color_key,
                    "size": size_key,
                    "bling_product_id": id_produto,
                    "bling_stock_id": bling_id,
                    "supplier_name": supplier_name,
                    "price_varejo": price_varejo,
                    "price_custo": price_custo,
                    "price_atacado": price_atacado,
                }
            )

        except Exception as e:
            cur.execute(
                """
                UPDATE stock_moves
                SET status='ERROR', result_json=?
                WHERE move_id=?
                """,
                (json.dumps({"error": str(e)}, ensure_ascii=False), move_id),
            )
            erro += 1
            error_moves.append(
                {
                    "move_id": move_id,
                    "sku": sku,
                    "qty_delta": int(qty_delta),
                    "base": base_name,
                    "color": color_key,
                    "size": size_key,
                    "supplier_name": supplier_name,
                    "price_varejo": price_varejo,
                    "price_custo": price_custo,
                    "price_atacado": price_atacado,
                    "error": str(e),
                }
            )

        conn.commit()
        time.sleep(0.35)

    conn.close()
    return {
        "processed": len(rows),
        "ok": ok,
        "error": erro,
        "filter_created_by": created_by,
        "filter_move_ids": ids or None,
        "done_moves": done_moves,
        "error_moves": error_moves,
    }
