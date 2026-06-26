from apps.produtos.services.db import get_conn

def find_template_product_id(base_name: str) -> int | None:
    """
    Pega um idProduto existente no Bling para servir de modelo (template)
    para copiar campos ao criar novas variações.
    """
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("""
        SELECT bling_product_id
        FROM variants_cache
        WHERE base_name = ?
        ORDER BY updated_at DESC
        LIMIT 1
    """, (base_name,)).fetchone()
    conn.close()
    return int(row[0]) if row else None

def variant_exists(base_name: str, color: str, size: str) -> bool:
    conn = get_conn()
    cur = conn.cursor()
    row = cur.execute("""
        SELECT 1
        FROM variants_cache
        WHERE base_name = ?
          AND color_key = ?
          AND size_key = ?
        LIMIT 1
    """, (base_name, str(color).strip().upper(), str(size).strip().upper())).fetchone()
    conn.close()
    return bool(row)
