from apps.produtos.services.db import get_conn

def get_id_produto_by_sku(sku: str) -> int | None:
    """
    Usa o cache local: variants_cache.sku -> variants_cache.bling_product_id
    """
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("""
        SELECT bling_product_id
        FROM variants_cache
        WHERE sku = ?
        LIMIT 1
    """, (str(sku).strip(),)).fetchone()
    conn.close()
    return int(row[0]) if row else None
