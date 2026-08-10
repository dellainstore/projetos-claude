from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import pandas as pd

from .rules import (
    arredondar_quantidade_operacional,
    calcular_quantidade_sugerida_reposicao,
    calcular_risco_ruptura,
    calcular_status_estoque,
    calcular_tendencia,
    calcular_variacao_percentual,
)


def _normalize_ref_date(reference_date: date | str | None = None) -> date:
    if reference_date is None:
        return date.today()
    if isinstance(reference_date, date):
        return reference_date
    return date.fromisoformat(str(reference_date)[:10])


def calcular_metricas_vendas_por_produto(
    vendas_df: pd.DataFrame,
    *,
    reference_date: date | str | None = None,
    group_col: str = "produto_id",
) -> pd.DataFrame:
    """Calcula ultima venda e janelas de 30/60/90 dias por entidade."""
    ref = _normalize_ref_date(reference_date)
    inicio_30 = ref - timedelta(days=30)
    inicio_60 = ref - timedelta(days=60)
    inicio_90 = ref - timedelta(days=90)

    if vendas_df.empty:
        return pd.DataFrame(
            columns=[
                group_col,
                "ultima_data_venda",
                "vendido_30d",
                "vendido_30d_anterior",
                "vendido_60d",
                "vendido_90d",
            ]
        )

    df = vendas_df.copy()
    df["data"] = pd.to_datetime(df["data"], errors="coerce")
    df = df.dropna(subset=["data"])
    if df.empty or group_col not in df.columns:
        return pd.DataFrame(
            columns=[
                group_col,
                "ultima_data_venda",
                "vendido_30d",
                "vendido_30d_anterior",
                "vendido_60d",
                "vendido_90d",
            ]
        )

    df["data_day"] = df["data"].dt.date
    if group_col == "produto_id":
        df[group_col] = pd.to_numeric(df[group_col], errors="coerce").fillna(0).astype(int)
    else:
        df[group_col] = df[group_col].astype(str).str.strip()
    df["quantidade"] = pd.to_numeric(df["quantidade"], errors="coerce").fillna(0.0)

    ultimas = (
        df.groupby(group_col, as_index=False)["data_day"]
        .max()
        .rename(columns={"data_day": "ultima_data_venda"})
    )

    vendido_30 = (
        df[(df["data_day"] >= inicio_30) & (df["data_day"] <= ref)]
        .groupby(group_col, as_index=False)["quantidade"]
        .sum()
        .rename(columns={"quantidade": "vendido_30d"})
    )

    vendido_30_ant = (
        df[(df["data_day"] >= inicio_60) & (df["data_day"] < inicio_30)]
        .groupby(group_col, as_index=False)["quantidade"]
        .sum()
        .rename(columns={"quantidade": "vendido_30d_anterior"})
    )

    vendido_60 = (
        df[(df["data_day"] >= inicio_60) & (df["data_day"] <= ref)]
        .groupby(group_col, as_index=False)["quantidade"]
        .sum()
        .rename(columns={"quantidade": "vendido_60d"})
    )
    vendido_90 = (
        df[(df["data_day"] >= inicio_90) & (df["data_day"] <= ref)]
        .groupby(group_col, as_index=False)["quantidade"]
        .sum()
        .rename(columns={"quantidade": "vendido_90d"})
    )

    out = (
        ultimas.merge(vendido_30, on=group_col, how="outer")
        .merge(vendido_30_ant, on=group_col, how="outer")
        .merge(vendido_60, on=group_col, how="outer")
        .merge(vendido_90, on=group_col, how="outer")
    )
    out["vendido_30d"] = out["vendido_30d"].fillna(0.0)
    out["vendido_30d_anterior"] = out["vendido_30d_anterior"].fillna(0.0)
    out["vendido_60d"] = out["vendido_60d"].fillna(0.0)
    out["vendido_90d"] = out["vendido_90d"].fillna(0.0)
    return out


def faixa_dias_sem_venda(value: Any) -> str:
    if value is None or pd.isna(value):
        return "sem historico"
    days = int(value)
    if days <= 30:
        return "ate 30 dias"
    if days <= 60:
        return "31 a 60 dias"
    if days <= 90:
        return "61 a 90 dias"
    if days <= 180:
        return "+90 dias"
    return "+180 dias"


def aplicar_metricas_analiticas_sku(
    sku_df: pd.DataFrame,
    *,
    reference_date: date | str | None = None,
    historical_start_date: date | str | None = None,
    reposicao_cobertura_alvo_dias: int = 30,
    reposicao_lote_minimo: int = 6,
    reposicao_arredondar_multiplo_lote: bool = True,
) -> pd.DataFrame:
    """Aplica métricas analíticas em dataframe nível SKU."""
    ref = _normalize_ref_date(reference_date)
    hist_start = _normalize_ref_date(historical_start_date) if historical_start_date else date(2025, 1, 1)
    periodo_dias = max(1, (ref - hist_start).days + 1)
    df = sku_df.copy()

    df["estoque_atual"] = pd.to_numeric(df.get("estoque_atual", 0), errors="coerce").fillna(0.0)
    df["custo_unitario"] = pd.to_numeric(df.get("custo_unitario", 0), errors="coerce").fillna(0.0)
    df["preco_venda"] = pd.to_numeric(df.get("preco_venda", 0), errors="coerce").fillna(0.0)
    df["vendido_total_periodo"] = pd.to_numeric(df.get("vendido_total_periodo", 0), errors="coerce").fillna(0.0)
    df["vendido_total"] = pd.to_numeric(df.get("vendido_total", df["vendido_total_periodo"]), errors="coerce").fillna(0.0)
    df["vendido_30d"] = pd.to_numeric(df.get("vendido_30d", 0), errors="coerce").fillna(0.0)
    df["vendido_30d_anterior"] = pd.to_numeric(
        df.get("vendido_30d_anterior", 0), errors="coerce"
    ).fillna(0.0)
    df["vendido_60d"] = pd.to_numeric(df.get("vendido_60d", 0), errors="coerce").fillna(0.0)
    df["vendido_90d"] = pd.to_numeric(df.get("vendido_90d", 0), errors="coerce").fillna(0.0)

    df["valor_total_custo"] = df["estoque_atual"] * df["custo_unitario"]
    df["valor_total_venda"] = df["estoque_atual"] * df["preco_venda"]

    # Base principal de decisão: histórico acumulado desde data inicial.
    df["media_venda_diaria_historica"] = df["vendido_total_periodo"] / float(periodo_dias)
    df["media_venda_mensal_historica"] = df["media_venda_diaria_historica"] * 30.0

    cobertura_hist = []
    for estoque, media in zip(df["estoque_atual"], df["media_venda_diaria_historica"]):
        if media > 0:
            cobertura_hist.append(float(estoque) / float(media))
        elif estoque > 0:
            cobertura_hist.append(9999.0)
        else:
            cobertura_hist.append(0.0)
    df["dias_cobertura_historico"] = cobertura_hist
    df["dias_cobertura"] = df["dias_cobertura_historico"]

    # Janelas recentes ficam como contexto complementar.
    df["media_venda_diaria_30d"] = df["vendido_30d"] / 30.0
    df["media_venda_mensal_30d"] = df["media_venda_diaria_30d"] * 30.0

    if "ultima_data_venda" in df.columns:
        datas = pd.to_datetime(df["ultima_data_venda"], errors="coerce")
        diff = (pd.Timestamp(ref) - datas).dt.days
        df["dias_sem_venda"] = diff.fillna(9999).clip(lower=0).astype(int)
    else:
        df["dias_sem_venda"] = 9999
    df["faixa_dias_sem_venda"] = df["dias_sem_venda"].apply(faixa_dias_sem_venda)

    df["status_estoque"] = df["dias_sem_venda"].apply(calcular_status_estoque)
    df["variacao_percentual_30d"] = [
        calcular_variacao_percentual(v1, v0)
        for v1, v0 in zip(df["vendido_30d"], df["vendido_30d_anterior"])
    ]
    df["tendencia"] = [
        calcular_tendencia(v1, v0)
        for v1, v0 in zip(df["vendido_30d"], df["vendido_30d_anterior"])
    ]
    df["risco_ruptura"] = [
        calcular_risco_ruptura(media, dias) for media, dias in zip(df["media_venda_diaria_historica"], df["dias_cobertura_historico"])
    ]
    df["quantidade_sugerida_reposicao_calculada"] = [
        calcular_quantidade_sugerida_reposicao(
            estoque,
            media,
            dias_alvo_cobertura=reposicao_cobertura_alvo_dias,
        )
        for estoque, media in zip(df["estoque_atual"], df["media_venda_diaria_historica"])
    ]
    df["quantidade_sugerida_reposicao_calculada"] = pd.to_numeric(
        df["quantidade_sugerida_reposicao_calculada"], errors="coerce"
    ).fillna(0.0)
    # Regra operacional: mínimo por SKU + arredondamento em múltiplos de lote.
    df["quantidade_sugerida_reposicao_operacional"] = [
        arredondar_quantidade_operacional(
            qtd,
            lote_minimo=reposicao_lote_minimo,
            arredondar_multiplo=reposicao_arredondar_multiplo_lote,
        )
        for qtd in df["quantidade_sugerida_reposicao_calculada"]
    ]
    # Compatibilidade: coluna principal de interface passa a refletir a regra operacional.
    df["quantidade_sugerida_reposicao"] = df["quantidade_sugerida_reposicao_operacional"]

    return df
