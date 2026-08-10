"""Regras de negocio para motor analitico de estoque."""

from __future__ import annotations

import math
from typing import Dict

import pandas as pd


def calcular_status_estoque(dias_sem_venda: int) -> str:
    if dias_sem_venda >= 90:
        return "queima"
    if dias_sem_venda >= 60:
        return "muito_parado"
    if dias_sem_venda >= 30:
        return "parado"
    return "normal"


def calcular_risco_ruptura(media_diaria_30d: float, dias_cobertura: float) -> bool:
    return media_diaria_30d > 0 and dias_cobertura < 15


def calcular_quantidade_sugerida_reposicao(
    estoque_atual: float,
    media_diaria_30d: float,
    *,
    dias_alvo_cobertura: int = 30,
) -> float:
    """Sugestao inicial simples para reposicao.

    Regra MVP:
    - calcula estoque alvo para dias_alvo_cobertura
    - sugestao = max(0, alvo - estoque_atual)
    """
    if media_diaria_30d <= 0:
        return 0.0
    alvo = media_diaria_30d * max(1, int(dias_alvo_cobertura))
    return float(max(0, math.ceil(alvo - max(0.0, float(estoque_atual)))))


def arredondar_quantidade_operacional(
    quantidade_calculada: float,
    *,
    lote_minimo: int = 6,
    arredondar_multiplo: bool = True,
) -> float:
    qtd = float(max(0.0, quantidade_calculada))
    lote = max(1, int(lote_minimo))
    if qtd <= 0:
        return 0.0
    if qtd <= lote:
        return float(lote)
    if arredondar_multiplo:
        return float(int(math.ceil(qtd / lote)) * lote)
    return float(max(lote, math.ceil(qtd)))


def calcular_mix_distribuicao_tamanho(
    df_tamanho: pd.DataFrame,
    *,
    mix_base: Dict[str, float],
    peso_historico: float,
    peso_estoque: float,
    peso_mix: float,
) -> pd.Series:
    """Gera pesos de distribuicao por tamanho combinando historico, estoque e mix base.

    - historico: participacao de vendas historicas por tamanho
    - estoque: favorece tamanhos com menor saldo atual (ruptura/baixa cobertura)
    - mix base: guia de modelagem para reduzir vies em janelas com ruptura
    """
    if df_tamanho.empty:
        return pd.Series(dtype=float)

    work = df_tamanho.copy()
    work["vendido_historico"] = pd.to_numeric(work["vendido_historico"], errors="coerce").fillna(0.0)
    work["estoque_atual"] = pd.to_numeric(work["estoque_atual"], errors="coerce").fillna(0.0)
    work["tamanho"] = work["tamanho"].astype(str).str.upper()

    hist_raw = work["vendido_historico"].clip(lower=0.0)
    hist_share = hist_raw / max(float(hist_raw.sum()), 1.0)

    estoque_pos = work["estoque_atual"].clip(lower=0.0)
    estoque_inv = 1.0 / (estoque_pos + 1.0)
    estoque_share = estoque_inv / max(float(estoque_inv.sum()), 1.0)

    mix_raw = work["tamanho"].map(lambda t: float(mix_base.get(str(t).upper(), 0.0)))
    if float(mix_raw.sum()) <= 0:
        mix_raw = pd.Series([1.0] * len(work), index=work.index)
    mix_share = mix_raw / max(float(mix_raw.sum()), 1.0)

    w_hist = max(0.0, float(peso_historico))
    w_stock = max(0.0, float(peso_estoque))
    w_mix = max(0.0, float(peso_mix))
    w_total = w_hist + w_stock + w_mix
    if w_total <= 0:
        w_hist, w_stock, w_mix, w_total = 0.5, 0.3, 0.2, 1.0

    score = ((w_hist * hist_share) + (w_stock * estoque_share) + (w_mix * mix_share)) / w_total
    score = score / max(float(score.sum()), 1.0)
    return score


def distribuir_quantidade_por_tamanho(
    df_tamanho: pd.DataFrame,
    *,
    total_produzir: int,
    mix_base: Dict[str, float],
    peso_historico: float,
    peso_estoque: float,
    peso_mix: float,
) -> pd.Series:
    """Distribui total de producao por tamanho com ajuste inteiro por maior resto."""
    if df_tamanho.empty or int(total_produzir) <= 0:
        return pd.Series([0] * len(df_tamanho), index=df_tamanho.index, dtype=int)

    pesos = calcular_mix_distribuicao_tamanho(
        df_tamanho,
        mix_base=mix_base,
        peso_historico=peso_historico,
        peso_estoque=peso_estoque,
        peso_mix=peso_mix,
    )

    bruto = pesos * float(int(total_produzir))
    base = bruto.apply(math.floor).astype(int)
    resto = int(total_produzir) - int(base.sum())
    frac = (bruto - base).sort_values(ascending=False)

    add = pd.Series(0, index=df_tamanho.index, dtype=int)
    if resto > 0:
        add.loc[frac.index[:resto]] = 1
    return (base + add).astype(int)


def calcular_tendencia(vendas_30d: float, vendas_30d_anteriores: float) -> str:
    if vendas_30d <= 0 and vendas_30d_anteriores <= 0:
        return "estavel"
    if vendas_30d_anteriores <= 0 and vendas_30d > 0:
        return "aumento"

    variacao = calcular_variacao_percentual(vendas_30d, vendas_30d_anteriores)
    if variacao > 10:
        return "aumento"
    if variacao < -10:
        return "queda"
    return "estavel"


def calcular_variacao_percentual(vendas_30d: float, vendas_30d_anteriores: float) -> float:
    if vendas_30d_anteriores <= 0:
        if vendas_30d > 0:
            return 100.0
        return 0.0
    return ((vendas_30d - vendas_30d_anteriores) / vendas_30d_anteriores) * 100.0
