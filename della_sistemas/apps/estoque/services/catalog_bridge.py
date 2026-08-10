"""Ponte somente-leitura para o catálogo já sincronizado pelo apps.produtos.

Evita re-buscar produtos no Bling e re-implementar o split de SKU
(modelo/cor/tamanho): reaproveita `products_cache`/`variants_cache` do
`inclusoes.db`, mantidos pelo cron diário `sync_catalog` do módulo produtos.
Não escreve nada nessas tabelas.
"""
from __future__ import annotations

import pandas as pd

from apps.produtos.services.db import get_conn as get_produtos_conn


def carregar_catalogo() -> pd.DataFrame:
    """Retorna produto_id/sku/nome/modelo/cor/tamanho/situacao/ativo."""
    conn = get_produtos_conn()
    try:
        df = pd.read_sql_query(
            """
            SELECT
                p.bling_product_id AS produto_id,
                p.code             AS sku,
                p.name             AS nome,
                p.situation        AS situacao,
                COALESCE(v.base_name, '')  AS modelo,
                COALESCE(v.color_key, '')  AS cor,
                COALESCE(v.size_key, '')   AS tamanho,
                COALESCE(v.active, 1)      AS ativo
            FROM products_cache p
            LEFT JOIN variants_cache v ON v.bling_product_id = p.bling_product_id
            """,
            conn,
        )
    finally:
        conn.close()

    df["produto_id"] = pd.to_numeric(df["produto_id"], errors="coerce").fillna(0).astype(int)
    df["sku"] = df["sku"].astype(str).str.strip()
    df["nome"] = df["nome"].astype(str).str.strip()
    df["modelo"] = df["modelo"].astype(str).str.strip()
    df["cor"] = df["cor"].astype(str).str.strip()
    df["tamanho"] = df["tamanho"].astype(str).str.strip()
    return df[df["produto_id"] > 0].drop_duplicates(subset=["produto_id"])
