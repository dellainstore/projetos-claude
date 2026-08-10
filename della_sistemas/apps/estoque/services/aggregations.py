from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from . import config
from .catalog_bridge import carregar_catalogo
from .db import get_conn
from .metrics import aplicar_metricas_analiticas_sku, calcular_metricas_vendas_por_produto


def carregar_tabelas_analiticas() -> dict[str, pd.DataFrame]:
    """Junta identidade (catálogo do produtos, só leitura) com preço/custo,
    saldo de estoque e vendas (próprios deste módulo)."""
    catalogo = carregar_catalogo()

    conn = get_conn()
    try:
        precos = pd.read_sql_query(
            """
            SELECT produto_id, COALESCE(preco, 0) AS preco_venda, COALESCE(custo, 0) AS custo_unitario
            FROM estoque_precos
            """,
            conn,
        )
        estoque = pd.read_sql_query(
            "SELECT produto_id, COALESCE(quantidade, 0) AS estoque_atual FROM estoque",
            conn,
        )
        vendas = pd.read_sql_query(
            "SELECT produto_id, COALESCE(quantidade, 0) AS quantidade, data, pedido_id, situacao_id FROM vendas",
            conn,
        )
    finally:
        conn.close()

    produtos = catalogo.merge(precos, on="produto_id", how="left")
    produtos["preco_venda"] = pd.to_numeric(produtos["preco_venda"], errors="coerce").fillna(0.0)
    produtos["custo_unitario"] = pd.to_numeric(produtos["custo_unitario"], errors="coerce").fillna(0.0)

    return {"produtos": produtos, "estoque": estoque, "vendas": vendas}


def _normalize_ref_date(reference_date: date | str | None = None) -> date:
    if reference_date is None:
        return date.today()
    if isinstance(reference_date, date):
        return reference_date
    return date.fromisoformat(str(reference_date)[:10])


def _carregar_historico_consolidado_por_sku(
    *,
    reference_date: date,
    start_date: date,
) -> pd.DataFrame:
    path = Path(config.HISTORICO_CONSOLIDADO_XLSX_PATH)
    if not path.exists():
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    try:
        raw = pd.read_excel(path, sheet_name=config.HISTORICO_CONSOLIDADO_SHEET)
    except Exception:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    col_mes = "Mês" if "Mês" in raw.columns else ("Mes" if "Mes" in raw.columns else None)
    col_codigo = "Código" if "Código" in raw.columns else ("Codigo" if "Codigo" in raw.columns else None)
    col_qtd = "Quantidade" if "Quantidade" in raw.columns else None
    if not col_mes or not col_codigo or not col_qtd:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    hist = raw[[col_mes, col_codigo, col_qtd]].copy()
    hist["mes"] = pd.to_datetime(hist[col_mes], errors="coerce").dt.to_period("M")
    hist["sku"] = hist[col_codigo].astype(str).str.strip()
    hist["quantidade"] = pd.to_numeric(hist[col_qtd], errors="coerce").fillna(0.0)
    hist = hist.dropna(subset=["mes"])
    if hist.empty:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    start_period = pd.Period(start_date.strftime("%Y-%m"), freq="M")
    ref_period = pd.Period(reference_date.strftime("%Y-%m"), freq="M")
    hist = hist[(hist["mes"] >= start_period) & (hist["mes"] <= ref_period)]
    if hist.empty:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    # Histórico consolidado é oficial para meses fechados.
    current_period = pd.Period(reference_date.strftime("%Y-%m"), freq="M")
    hist = hist[hist["mes"] < current_period]
    if hist.empty:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    hist = (
        hist.groupby(["mes", "sku"], as_index=False)["quantidade"]
        .sum()
        .assign(
            data=lambda d: d["mes"].dt.to_timestamp(how="end").dt.normalize(),
            fonte="historico_xlsx",
        )
    )
    return hist[["sku", "data", "quantidade", "fonte"]]


def _carregar_incremental_por_sku(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    *,
    reference_date: date,
    start_date: date,
) -> pd.DataFrame:
    if vendas.empty:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    inc = vendas.copy()
    inc["data"] = pd.to_datetime(inc["data"], errors="coerce")
    inc = inc.dropna(subset=["data"])
    if inc.empty:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    sku_map = produtos[["produto_id", "sku"]].copy()
    sku_map["sku"] = sku_map["sku"].astype(str).str.strip()
    inc = inc.merge(sku_map, on="produto_id", how="left")
    inc["sku"] = inc["sku"].astype(str).str.strip()
    inc["quantidade"] = pd.to_numeric(inc["quantidade"], errors="coerce").fillna(0.0)
    inc = inc[(inc["data"].dt.date >= start_date) & (inc["data"].dt.date <= reference_date)]
    inc = inc[inc["sku"].ne("") & inc["sku"].ne("nan")]
    if inc.empty:
        return pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])

    inc["fonte"] = "incremental_sqlite"
    return inc[["sku", "data", "quantidade", "fonte"]]


def _combinar_historico_mais_incremental(
    vendas: pd.DataFrame,
    produtos: pd.DataFrame,
    *,
    reference_date: date,
    start_date: date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    historico = _carregar_historico_consolidado_por_sku(reference_date=reference_date, start_date=start_date)
    incremental = _carregar_incremental_por_sku(vendas, produtos, reference_date=reference_date, start_date=start_date)

    if incremental.empty and historico.empty:
        empty = pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])
        return empty, empty

    if incremental.empty:
        combined = historico.copy()
        recent = pd.DataFrame(columns=["sku", "data", "quantidade", "fonte"])
        return combined, recent

    incremental = incremental.copy()
    incremental["mes"] = incremental["data"].dt.to_period("M")

    # Evita duplicidade: para meses fechados cobertos no XLSX, mantém apenas consolidado.
    hist_months = set(pd.to_datetime(historico["data"], errors="coerce").dt.to_period("M").dropna().tolist())
    current_period = pd.Period(reference_date.strftime("%Y-%m"), freq="M")
    incremental = incremental[(~incremental["mes"].isin(hist_months)) | (incremental["mes"] == current_period)]

    combined = pd.concat(
        [
            historico,
            incremental.drop(columns=["mes"], errors="ignore"),
        ],
        ignore_index=True,
    )
    combined["data"] = pd.to_datetime(combined["data"], errors="coerce")
    combined = combined.dropna(subset=["data"])
    combined["quantidade"] = pd.to_numeric(combined["quantidade"], errors="coerce").fillna(0.0)

    recent = _carregar_incremental_por_sku(vendas, produtos, reference_date=reference_date, start_date=start_date)
    return combined, recent


def construir_visao_sku(*, reference_date: date | str | None = None) -> pd.DataFrame:
    ref = _normalize_ref_date(reference_date)
    hist_start = _normalize_ref_date(config.HISTORICO_BASE_INICIO)
    tables = carregar_tabelas_analiticas()
    produtos = tables["produtos"]
    estoque = tables["estoque"]
    vendas = tables["vendas"]

    base = produtos.merge(estoque, on="produto_id", how="left")
    base["estoque_atual"] = pd.to_numeric(base["estoque_atual"], errors="coerce").fillna(0.0)
    base["sku"] = base["sku"].astype(str).str.strip()

    vendas_acumuladas, vendas_recentes = _combinar_historico_mais_incremental(
        vendas,
        produtos,
        reference_date=ref,
        start_date=hist_start,
    )

    vendas_total = (
        vendas_acumuladas.groupby("sku", as_index=False)["quantidade"]
        .sum()
        .rename(columns={"quantidade": "vendido_total_periodo"})
    )
    base = base.merge(vendas_total, on="sku", how="left")
    base["vendido_total_periodo"] = pd.to_numeric(base["vendido_total_periodo"], errors="coerce").fillna(0.0)
    base["vendido_total"] = base["vendido_total_periodo"]

    vendas_metrics = calcular_metricas_vendas_por_produto(
        vendas_recentes,
        reference_date=ref,
        group_col="sku",
    )
    base = base.merge(vendas_metrics, on="sku", how="left")
    base["vendido_30d"] = pd.to_numeric(base["vendido_30d"], errors="coerce").fillna(0.0)
    base["vendido_30d_anterior"] = pd.to_numeric(base["vendido_30d_anterior"], errors="coerce").fillna(0.0)
    base["vendido_60d"] = pd.to_numeric(base["vendido_60d"], errors="coerce").fillna(0.0)
    base["vendido_90d"] = pd.to_numeric(base["vendido_90d"], errors="coerce").fillna(0.0)

    # Fallback de última venda para SKUs somente no histórico consolidado mensal.
    if not vendas_acumuladas.empty:
        ult_hist = (
            vendas_acumuladas.groupby("sku", as_index=False)["data"]
            .max()
            .rename(columns={"data": "ultima_data_venda_historico"})
        )
        base = base.merge(ult_hist, on="sku", how="left")
        base["ultima_data_venda"] = base["ultima_data_venda"].fillna(base["ultima_data_venda_historico"])

    return aplicar_metricas_analiticas_sku(
        base,
        reference_date=ref,
        historical_start_date=hist_start,
        reposicao_cobertura_alvo_dias=config.REPOSICAO_COBERTURA_ALVO_DIAS,
        reposicao_lote_minimo=config.REPOSICAO_LOTE_MINIMO_SKU,
        reposicao_arredondar_multiplo_lote=config.REPOSICAO_ARREDONDAR_MULTIPLO_LOTE,
    )


def construir_visao_estoque_atual() -> pd.DataFrame:
    tables = carregar_tabelas_analiticas()
    produtos = tables["produtos"].copy()
    estoque = tables["estoque"].copy()

    base = produtos.merge(estoque, on="produto_id", how="left")
    base["sku"] = base["sku"].astype(str).str.strip()
    base["estoque_atual"] = pd.to_numeric(base["estoque_atual"], errors="coerce").fillna(0.0)
    base["situacao_saldo"] = "zerado"
    base.loc[base["estoque_atual"] > 0, "situacao_saldo"] = "positivo"
    base.loc[base["estoque_atual"] < 0, "situacao_saldo"] = "negativo"
    return base[
        [
            "produto_id",
            "sku",
            "nome",
            "modelo",
            "cor",
            "tamanho",
            "estoque_atual",
            "situacao_saldo",
        ]
    ]


def _agrupar_nivel(df_sku: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    grouped = (
        df_sku.groupby(group_cols, dropna=False, as_index=False)
        .agg(
            qtd_skus=("produto_id", "nunique"),
            estoque_atual=("estoque_atual", "sum"),
            valor_total_custo=("valor_total_custo", "sum"),
            valor_total_venda=("valor_total_venda", "sum"),
            vendido_total_periodo=("vendido_total_periodo", "sum"),
            vendido_30d=("vendido_30d", "sum"),
            vendido_30d_anterior=("vendido_30d_anterior", "sum"),
            vendido_60d=("vendido_60d", "sum"),
            vendido_90d=("vendido_90d", "sum"),
            ultima_data_venda=("ultima_data_venda", "max"),
            preco_venda_medio=("preco_venda", "mean"),
            custo_unitario_medio=("custo_unitario", "mean"),
            media_venda_diaria_historica=("media_venda_diaria_historica", "sum"),
            media_venda_mensal_historica=("media_venda_mensal_historica", "sum"),
        )
        .reset_index(drop=True)
    )

    grouped["vendido_total"] = grouped["vendido_total_periodo"]
    grouped["media_venda_diaria_30d"] = grouped["vendido_30d"] / 30.0
    grouped["media_venda_mensal_30d"] = grouped["media_venda_diaria_30d"] * 30.0
    grouped["dias_cobertura_historico"] = grouped.apply(
        lambda r: (
            (r["estoque_atual"] / r["media_venda_diaria_historica"])
            if r["media_venda_diaria_historica"] > 0
            else (9999.0 if r["estoque_atual"] > 0 else 0.0)
        ),
        axis=1,
    )
    grouped["dias_cobertura"] = grouped["dias_cobertura_historico"]
    grouped["variacao_percentual_30d"] = grouped.apply(
        lambda r: (
            ((r["vendido_30d"] - r["vendido_30d_anterior"]) / r["vendido_30d_anterior"]) * 100.0
            if r["vendido_30d_anterior"] > 0
            else (100.0 if r["vendido_30d"] > 0 else 0.0)
        ),
        axis=1,
    )
    grouped["tendencia"] = grouped["variacao_percentual_30d"].apply(
        lambda v: "aumento" if v > 10 else ("queda" if v < -10 else "estavel")
    )
    return grouped


def construir_visao_modelo_cor(*, sku_df: pd.DataFrame | None = None, reference_date: date | str | None = None) -> pd.DataFrame:
    df = sku_df if sku_df is not None else construir_visao_sku(reference_date=reference_date)
    return _agrupar_nivel(df, ["modelo", "cor"])


def construir_visao_modelo(*, sku_df: pd.DataFrame | None = None, reference_date: date | str | None = None) -> pd.DataFrame:
    df = sku_df if sku_df is not None else construir_visao_sku(reference_date=reference_date)
    return _agrupar_nivel(df, ["modelo"])


def top_estoque_parado(*, limit: int = 20, reference_date: date | str | None = None) -> pd.DataFrame:
    df = construir_visao_sku(reference_date=reference_date)
    filtered = df[
        (df["estoque_atual"] > 0)
        & (df["status_estoque"].isin(["parado", "muito_parado", "queima"]))
    ]
    return filtered.sort_values(
        ["dias_sem_venda", "estoque_atual", "valor_total_custo"],
        ascending=[False, False, False],
    ).head(limit)


def top_risco_ruptura(*, limit: int = 20, reference_date: date | str | None = None) -> pd.DataFrame:
    df = construir_visao_sku(reference_date=reference_date)
    out = df.copy()
    out["estoque_atual"] = pd.to_numeric(out["estoque_atual"], errors="coerce").fillna(0.0)
    out["vendido_30d"] = pd.to_numeric(out["vendido_30d"], errors="coerce").fillna(0.0)
    out["media_venda_diaria_30d"] = pd.to_numeric(out["media_venda_diaria_30d"], errors="coerce").fillna(0.0)
    out["dias_cobertura"] = pd.to_numeric(out["dias_cobertura"], errors="coerce").fillna(0.0)
    out["quantidade_sugerida_reposicao"] = pd.to_numeric(
        out["quantidade_sugerida_reposicao"], errors="coerce"
    ).fillna(0.0)
    if "quantidade_sugerida_reposicao_calculada" in out.columns:
        out["quantidade_sugerida_reposicao_calculada"] = pd.to_numeric(
            out["quantidade_sugerida_reposicao_calculada"], errors="coerce"
        ).fillna(0.0)
    if "quantidade_sugerida_reposicao_operacional" in out.columns:
        out["quantidade_sugerida_reposicao_operacional"] = pd.to_numeric(
            out["quantidade_sugerida_reposicao_operacional"], errors="coerce"
        ).fillna(0.0)

    # Cobertura oficial para reposição: sempre base histórica acumulada.
    if "dias_cobertura_historico" in out.columns:
        out["dias_cobertura_historico"] = pd.to_numeric(out["dias_cobertura_historico"], errors="coerce").fillna(0.0)
        out["dias_cobertura_historico"] = out["dias_cobertura_historico"].clip(lower=0.0)
        out.loc[out["estoque_atual"] <= 0, "dias_cobertura_historico"] = 0.0
        out["dias_cobertura"] = out["dias_cobertura_historico"]
    out["dias_cobertura"] = pd.to_numeric(out["dias_cobertura"], errors="coerce").fillna(0.0).clip(lower=0.0)
    out.loc[out["estoque_atual"] <= 0, "dias_cobertura"] = 0.0

    out["status_reposicao"] = "reposicao sugerida"
    out.loc[out["estoque_atual"] < 0, "status_reposicao"] = "saldo negativo"
    out.loc[out["estoque_atual"] == 0, "status_reposicao"] = "sem estoque"
    out.loc[
        (out["estoque_atual"] > 0) & (out["dias_cobertura"] <= 15) & (out["media_venda_diaria_historica"] > 0),
        "status_reposicao",
    ] = "reposicao urgente"

    out["bloco_reposicao"] = "Reposição sugerida"
    out.loc[out["estoque_atual"] < 0, "bloco_reposicao"] = "Saldo negativo / ajuste necessário"
    out.loc[
        ((out["estoque_atual"] == 0) & (out["media_venda_diaria_historica"] > 0))
        | (out["status_reposicao"] == "reposicao urgente"),
        "bloco_reposicao",
    ] = "Reposição urgente"

    demanda_relevante = out["vendido_total_periodo"] > 0
    is_negativo = out["estoque_atual"] < 0
    is_urgente = out["bloco_reposicao"] == "Reposição urgente"
    is_sugerido = (
        (out["bloco_reposicao"] == "Reposição sugerida")
        & (out["media_venda_diaria_historica"] > 0)
        & (out["dias_cobertura"] > 15)
        & (out["dias_cobertura"] <= 30)
    )
    filtered = out[(is_negativo | is_urgente | is_sugerido) & (demanda_relevante | is_negativo)].copy()

    filtered["prioridade_ordem"] = 2
    filtered.loc[filtered["bloco_reposicao"] == "Saldo negativo / ajuste necessário", "prioridade_ordem"] = 0
    filtered.loc[filtered["bloco_reposicao"] == "Reposição urgente", "prioridade_ordem"] = 1

    return filtered.sort_values(
        ["prioridade_ordem", "dias_cobertura", "vendido_total_periodo", "vendido_30d"],
        ascending=[True, True, False, False],
    ).head(limit)


def top_maior_cobertura(*, limit: int = 20, reference_date: date | str | None = None) -> pd.DataFrame:
    df = construir_visao_sku(reference_date=reference_date)
    if "dias_cobertura_historico" in df.columns:
        df = df.copy()
        df["dias_cobertura"] = pd.to_numeric(df["dias_cobertura_historico"], errors="coerce").fillna(0.0)
    filtered = df[(df["estoque_atual"] > 0) & (df["media_venda_diaria_historica"] > 0)]
    return filtered.sort_values(
        ["dias_cobertura", "estoque_atual"],
        ascending=[False, False],
    ).head(limit)


def diagnosticar_divergencia_estoque_atual() -> dict[str, Any]:
    tables = carregar_tabelas_analiticas()
    produtos = tables["produtos"].copy()
    estoque = tables["estoque"].copy()

    produtos["sku"] = produtos["sku"].astype(str).str.strip()
    estoque["estoque_atual"] = pd.to_numeric(estoque["estoque_atual"], errors="coerce").fillna(0.0)

    visao = produtos.merge(estoque, on="produto_id", how="left")
    visao["estoque_atual"] = pd.to_numeric(visao["estoque_atual"], errors="coerce").fillna(0.0)

    duplicate_produto_estoque = int(estoque.duplicated(subset=["produto_id"]).sum())
    duplicate_sku_produtos = int(produtos.duplicated(subset=["sku"]).sum())
    produtos_sem_estoque = int((~produtos["produto_id"].isin(estoque["produto_id"])).sum())
    estoque_orfao = int((~estoque["produto_id"].isin(produtos["produto_id"])).sum())

    return {
        "fonte_estoque_atual": "SQLite tabela estoque (join left com catálogo produtos por produto_id)",
        "regra_consolidacao": "1 linha por produto_id no catálogo; saldo 0 quando não há linha em estoque",
        "contagens": {
            "total_skus_cadastrados": int(visao["produto_id"].nunique()),
            "skus_saldo_positivo": int((visao["estoque_atual"] > 0).sum()),
            "skus_saldo_zerado": int((visao["estoque_atual"] == 0).sum()),
            "skus_saldo_negativo": int((visao["estoque_atual"] < 0).sum()),
            "pecas_positivas_total": float(visao.loc[visao["estoque_atual"] > 0, "estoque_atual"].sum()),
            "pecas_negativas_total_real": float(visao.loc[visao["estoque_atual"] < 0, "estoque_atual"].sum()),
            "pecas_negativas_total_absoluto": float(visao.loc[visao["estoque_atual"] < 0, "estoque_atual"].abs().sum()),
        },
        "possiveis_causas_divergencia": {
            "produto_sem_registro_estoque_assumido_zero": produtos_sem_estoque,
            "linhas_estoque_sem_produto_orfas": estoque_orfao,
            "duplicidade_produto_id_em_estoque": duplicate_produto_estoque,
            "duplicidade_sku_em_produtos": duplicate_sku_produtos,
        },
    }
