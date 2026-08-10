"""Consulta rápida de produto por SKU (lido via câmera ou digitado)."""

from __future__ import annotations

from apps.produtos.services.db import get_conn
from apps.produtos.services.precos import _fetch_precos_bling, _fetch_ultimos_atacados_local


def buscar_produto_por_sku(sku: str) -> dict | None:
    sku = (sku or "").strip()
    if not sku:
        return None

    conn = get_conn()
    row = conn.execute(
        """
        SELECT sku, base_name, color_key, size_key, bling_product_id
        FROM variants_cache
        WHERE UPPER(sku) = UPPER(?)
          AND active = 1
        LIMIT 1
        """,
        (sku,),
    ).fetchone()
    conn.close()

    if not row:
        return None

    sku_real, base_name, color_key, size_key, bling_id = row
    precos = _fetch_precos_bling(int(bling_id))
    atacado = precos.get("atacado") or _fetch_ultimos_atacados_local([sku_real]).get(sku_real.upper())

    return {
        "sku": sku_real,
        "base_name": base_name,
        "color_key": color_key,
        "size_key": size_key,
        "varejo": precos.get("varejo"),
        "atacado": atacado,
    }
