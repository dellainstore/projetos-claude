from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from .bling_client import (
    MAX_SAFE_DETAIL_WORKERS,
    get_estoque_atual,
    get_produtos_precos,
    get_vendas,
)
from .catalog_bridge import carregar_catalogo
from .config import LOG_DIR
from .db import get_conn, init_db


def _build_logger() -> logging.Logger:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOG_DIR / "sync_estoque.log"

    logger = logging.getLogger("estoque_analise_sync")
    logger.setLevel(logging.INFO)

    if not logger.handlers:
        handler = logging.FileHandler(log_file, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        logger.addHandler(handler)

    return logger


LOGGER = _build_logger()


def sync_produtos() -> dict[str, Any]:
    """Atualiza preço/custo/fornecedor por produto (a única parte do
    catálogo que não vem do sync do produtos)."""
    LOGGER.info("Iniciando sync_produtos (precos/custo/fornecedor)")
    catalogo_ids = set(carregar_catalogo()["produto_id"].tolist())
    rows = get_produtos_precos()

    init_db()
    conn = get_conn()
    try:
        upserts = 0
        ignorados_fora_catalogo = 0
        for item in rows:
            produto_id = int(item["id"])
            if produto_id not in catalogo_ids:
                # produto ainda não sincronizado pelo catálogo do produtos — ignora por ora
                ignorados_fora_catalogo += 1
                continue

            conn.execute(
                """
                INSERT INTO estoque_precos (produto_id, preco, custo, fornecedor, estoque_consolidado)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(produto_id) DO UPDATE SET
                    preco=excluded.preco,
                    custo=excluded.custo,
                    fornecedor=excluded.fornecedor,
                    estoque_consolidado=excluded.estoque_consolidado;
                """,
                (
                    produto_id,
                    float(item.get("preco") or 0),
                    float(item.get("precoCusto") or 0),
                    str(item.get("fornecedor") or "").strip(),
                    float(item.get("estoque") or 0),
                ),
            )
            upserts += 1
        conn.commit()
    finally:
        conn.close()

    LOGGER.info(
        "sync_produtos concluido | total=%s | ignorados_fora_catalogo=%s",
        upserts,
        ignorados_fora_catalogo,
    )
    return {"ok": True, "synced": upserts, "ignorados_fora_catalogo": ignorados_fora_catalogo}


def sync_estoque() -> dict[str, Any]:
    LOGGER.info("Iniciando sync_estoque")
    LOGGER.info("Fonte oficial: /estoques/saldos com idsProdutos[] em lotes de 100.")
    rows_api = get_estoque_atual()
    saldo_por_produto: dict[int, float] = {}
    for row in rows_api:
        produto_id = int(row.get("produto_id") or 0)
        if produto_id <= 0:
            continue
        quantidade = float(row.get("quantidade") or 0.0)
        saldo_por_produto[produto_id] = float(saldo_por_produto.get(produto_id, 0.0) + quantidade)

    catalogo_ids = carregar_catalogo()["produto_id"].tolist()

    init_db()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM estoque")
        inserts = 0
        for produto_id in catalogo_ids:
            quantidade = float(saldo_por_produto.get(int(produto_id), 0.0))
            conn.execute(
                "INSERT OR REPLACE INTO estoque (produto_id, quantidade) VALUES (?, ?)",
                (int(produto_id), quantidade),
            )
            inserts += 1
        conn.commit()
    finally:
        conn.close()

    LOGGER.info(
        "sync_estoque concluido | total_produtos=%s | produtos_com_saldo_api=%s",
        inserts,
        len(saldo_por_produto),
    )
    return {"ok": True, "synced": inserts, "saldo_api_produtos": len(saldo_por_produto)}


def sync_vendas(
    periodo_inicio: str | None = None,
    periodo_fim: str | None = None,
    *,
    detail_workers: int = 5,
) -> dict[str, Any]:
    fim = periodo_fim or date.today().isoformat()
    inicio = periodo_inicio or (date.today() - timedelta(days=30)).isoformat()

    effective_workers = max(1, min(int(detail_workers or 5), MAX_SAFE_DETAIL_WORKERS))
    LOGGER.info(
        "Iniciando sync_vendas | inicio=%s fim=%s | workers_efetivos=%s",
        inicio,
        fim,
        effective_workers,
    )
    rows = get_vendas(inicio, fim, detail_workers=effective_workers)
    unique_orders = len({int(r.get("idPedido") or 0) for r in rows if int(r.get("idPedido") or 0) > 0})

    produtos_existentes = set(carregar_catalogo()["produto_id"].tolist())

    init_db()
    conn = get_conn()
    try:
        conn.execute("DELETE FROM vendas WHERE data BETWEEN ? AND ?", (inicio, fim))

        inserts = 0
        orfaos_ignorados = 0
        for item in rows:
            produto_id = int(item["idProduto"])
            if produto_id not in produtos_existentes:
                orfaos_ignorados += 1
                continue

            conn.execute(
                """
                INSERT INTO vendas (produto_id, quantidade, data, pedido_id, situacao_id, valor)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    produto_id,
                    float(item.get("quantidade") or 0),
                    str(item.get("dataPedido") or ""),
                    int(item.get("idPedido") or 0) or None,
                    int(item.get("situacaoId") or 0) or None,
                    float(item.get("valor") or 0),
                ),
            )
            inserts += 1
        conn.commit()
    finally:
        conn.close()

    if orfaos_ignorados > 0:
        LOGGER.warning("sync_vendas orfaos_ignorados | total=%s", orfaos_ignorados)

    LOGGER.info("sync_vendas concluido | total=%s", inserts)
    return {
        "ok": True,
        "synced": inserts,
        "pedidos_unicos": unique_orders,
        "orfaos_ignorados": orfaos_ignorados,
        "inicio": inicio,
        "fim": fim,
    }


def _iter_janelas_mensais(inicio: str, fim: str) -> list[tuple[str, str]]:
    start = date.fromisoformat(str(inicio)[:10])
    end = date.fromisoformat(str(fim)[:10])
    if start > end:
        start, end = end, start

    janelas: list[tuple[str, str]] = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        if cursor.month == 12:
            prox = date(cursor.year + 1, 1, 1)
        else:
            prox = date(cursor.year, cursor.month + 1, 1)

        janela_inicio = max(cursor, start)
        janela_fim = min(prox - timedelta(days=1), end)
        janelas.append((janela_inicio.isoformat(), janela_fim.isoformat()))
        cursor = prox

    return janelas


def sync_vendas_historico_mensal(
    periodo_inicio: str,
    periodo_fim: str,
    *,
    detail_workers: int = 5,
) -> dict[str, Any]:
    """Executa carga historica de vendas em blocos mensais."""
    janelas = _iter_janelas_mensais(periodo_inicio, periodo_fim)
    LOGGER.info(
        "Iniciando sync_vendas_historico_mensal | inicio=%s fim=%s janelas=%s",
        periodo_inicio,
        periodo_fim,
        len(janelas),
    )

    total_itens = 0
    total_pedidos = 0
    detalhes_janelas: list[dict[str, Any]] = []
    for idx, (ini, fim) in enumerate(janelas, start=1):
        LOGGER.info("Janela %s/%s | inicio=%s fim=%s", idx, len(janelas), ini, fim)
        result = sync_vendas(ini, fim, detail_workers=detail_workers)
        total_itens += int(result.get("synced") or 0)
        total_pedidos += int(result.get("pedidos_unicos") or 0)
        detalhes_janelas.append(result)

    LOGGER.info(
        "sync_vendas_historico_mensal concluido | janelas=%s itens=%s pedidos=%s",
        len(janelas),
        total_itens,
        total_pedidos,
    )
    return {
        "ok": True,
        "mode": "historico_mensal",
        "janelas": len(janelas),
        "synced_itens": total_itens,
        "pedidos_unicos_total": total_pedidos,
        "inicio": periodo_inicio,
        "fim": periodo_fim,
        "detalhes_janelas": detalhes_janelas,
    }


def run_manual_refresh(*, sales_days: int = 2, workers: int = 3) -> dict[str, Any]:
    fim = date.today().isoformat()
    inicio = (date.today() - timedelta(days=max(1, int(sales_days)))).isoformat()
    return {
        "inicio": inicio,
        "fim": fim,
        "sync_produtos": sync_produtos(),
        "sync_estoque": sync_estoque(),
        "sync_vendas": sync_vendas(periodo_inicio=inicio, periodo_fim=fim, detail_workers=workers),
    }
