import json
import time
from typing import Any

from apps.produtos.services.bling.products import atualizar_produto_patch, get_produto
from apps.produtos.services.db import get_conn
from apps.produtos.services.business.pricing import extract_prices


def _build_patch_from_template(template_data: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "preco",
        "precoCusto",
        "precoCompra",
        "formato",
        "unidade",
        "tipo",
        "condicao",
        "fornecedor",
        "fornecedores",
        "tributacao",
        "camposCustomizados",
        "categoria",
        "marca",
        "descricaoComplementar",
    ]
    return {k: template_data.get(k) for k in fields if template_data.get(k) is not None}

def _build_price_enforcement_patch(
    template_data: dict[str, Any],
    *,
    price_varejo: float | None,
    price_custo: float | None,
) -> dict[str, Any]:
    p: dict[str, Any] = {}
    if price_varejo is not None:
        p["preco"] = float(price_varejo)
    if price_custo is not None:
        p["precoCusto"] = float(price_custo)
        p["precoCompra"] = float(price_custo)
        supplier_patch = _build_suppliers_patch(template_data, price_custo=float(price_custo))
        p.update(supplier_patch)
    return p


def _build_suppliers_patch(
    template_data: dict[str, Any],
    *,
    price_custo: float | None = None,
) -> dict[str, Any]:
    suppliers: list[dict[str, Any]] = []

    fornecedores_src = template_data.get("fornecedores")
    if isinstance(fornecedores_src, list):
        for row in fornecedores_src:
            if isinstance(row, dict):
                suppliers.append(dict(row))

    fornecedor_src = template_data.get("fornecedor")
    if isinstance(fornecedor_src, dict):
        suppliers.append(dict(fornecedor_src))
    elif isinstance(fornecedor_src, list):
        for row in fornecedor_src:
            if isinstance(row, dict):
                suppliers.append(dict(row))

    dedup: list[dict[str, Any]] = []
    seen: set[tuple[Any, Any, str]] = set()
    for row in suppliers:
        contato = row.get("contato") if isinstance(row.get("contato"), dict) else {}
        key = (row.get("id"), contato.get("id"), str(row.get("codigo") or "").strip().upper())
        if key in seen:
            continue
        seen.add(key)
        if price_custo is not None:
            row["precoCusto"] = float(price_custo)
            row["precoCompra"] = float(price_custo)
        dedup.append(row)

    if not dedup:
        return {}

    patch: dict[str, Any] = {"fornecedores": dedup}
    if len(dedup) == 1:
        patch["fornecedor"] = dedup[0]
    return patch


def reaplicar_template_nos_produtos_criados(*, hours_back: int = 72, limit_requests: int = 200) -> dict[str, Any]:
    """
    Reaplica campos do template (incluindo custo/preço) nos produtos criados no pipeline.
    Usa requests IMPLEMENTED do tipo UPSERT_VARIANT e percorre o bloco result_json['created'].
    """
    conn = get_conn()
    cur = conn.cursor()

    now = int(time.time())
    min_ts = now - max(1, int(hours_back)) * 3600

    rows = cur.execute(
        """
        SELECT request_id, template_product_id, result_json, COALESCE(updated_at, created_at) AS ts
        FROM requests
        WHERE status='IMPLEMENTED'
          AND type='UPSERT_VARIANT'
          AND template_product_id IS NOT NULL
          AND COALESCE(updated_at, created_at) >= ?
        ORDER BY request_id DESC
        LIMIT ?
        """,
        (min_ts, max(1, int(limit_requests))),
    ).fetchall()

    stats: dict[str, Any] = {
        "requests_lidas": len(rows),
        "produtos_alvo": 0,
        "produtos_atualizados": 0,
        "produtos_falha": 0,
        "stock_moves_atualizados": 0,
        "erros": [],
    }

    template_cache: dict[int, dict[str, Any]] = {}

    for request_id, template_id, result_json, _ts in rows:
        try:
            tid = int(template_id)
            if tid not in template_cache:
                template_data = get_produto(tid).get("data", {}) or {}
                if not template_data:
                    raise RuntimeError(f"Template {tid} sem dados no Bling.")
                template_cache[tid] = {
                    "template": template_data,
                    "patch": _build_patch_from_template(template_data),
                    "prices": extract_prices(template_data),
                }

            template_data = template_cache[tid]["template"]
            patch = template_cache[tid]["patch"]
            prices = template_cache[tid]["prices"]
            reinforce = _build_price_enforcement_patch(
                template_data,
                price_varejo=prices.get("price_varejo"),
                price_custo=prices.get("price_custo"),
            )
            if not patch and not reinforce:
                continue

            data = json.loads(result_json or "{}")
            created = data.get("created") or []
            if not isinstance(created, list):
                continue

            for item in created:
                pid = None
                if isinstance(item, dict):
                    pid = item.get("bling_product_id")
                if not pid:
                    continue
                stats["produtos_alvo"] += 1
                pid = int(pid)
                try:
                    if patch:
                        atualizar_produto_patch(pid, patch)
                    if reinforce:
                        atualizar_produto_patch(pid, reinforce)
                    stats["produtos_atualizados"] += 1

                    rc = cur.execute(
                        """
                        UPDATE stock_moves
                        SET price_varejo = COALESCE(price_varejo, ?),
                            price_custo = COALESCE(price_custo, ?),
                            price_atacado = COALESCE(price_atacado, ?)
                        WHERE bling_product_id = ?
                        """,
                        (
                            prices.get("price_varejo"),
                            prices.get("price_custo"),
                            prices.get("price_atacado"),
                            pid,
                        ),
                    ).rowcount
                    stats["stock_moves_atualizados"] += int(rc or 0)

                except Exception as pe:
                    stats["produtos_falha"] += 1
                    stats["erros"].append(
                        {"request_id": int(request_id), "bling_product_id": pid, "erro": str(pe)}
                    )

        except Exception as e:
            stats["erros"].append({"request_id": int(request_id), "erro": str(e)})

    conn.commit()
    conn.close()
    return stats
