from datetime import date

import pandas as pd
from django.shortcuts import render

from apps.core.decorators import perm_required
from apps.produtos.services.business.lookup import _sort_size_key as sort_size_key
from apps.estoque.services import config
from apps.estoque.services.aggregations import construir_visao_sku
from apps.estoque.services.rules import (
    arredondar_quantidade_operacional,
    calcular_quantidade_sugerida_reposicao,
    distribuir_quantidade_por_tamanho,
)


@perm_required("estoque_analise.ver")
def view_reposicao(request):
    limit = int(request.GET.get("limite", 200))
    df = construir_visao_sku()

    sku_df = df.copy()
    base_inicio = pd.to_datetime(config.HISTORICO_BASE_INICIO, errors="coerce")
    if pd.isna(base_inicio):
        base_inicio = pd.Timestamp("2025-01-01")
    dias_base = max(1, (pd.Timestamp(date.today()) - base_inicio.normalize()).days + 1)

    sku_df["media_venda_diaria_historica_base"] = (
        pd.to_numeric(sku_df["vendido_total_periodo"], errors="coerce").fillna(0.0) / float(dias_base)
    )

    sku_df["dias_cobertura"] = pd.to_numeric(
        sku_df["estoque_atual"] / sku_df["media_venda_diaria_historica_base"].replace(0.0, pd.NA),
        errors="coerce",
    ).fillna(0.0)
    sku_df["dias_cobertura"] = sku_df["dias_cobertura"].clip(lower=0.0)
    sku_df.loc[sku_df["estoque_atual"] <= 0, "dias_cobertura"] = 0.0

    sku_df["quantidade_sugerida_reposicao_calculada"] = [
        calcular_quantidade_sugerida_reposicao(
            estoque, media_hist, dias_alvo_cobertura=config.REPOSICAO_COBERTURA_ALVO_DIAS
        )
        for estoque, media_hist in zip(sku_df["estoque_atual"], sku_df["media_venda_diaria_historica_base"])
    ]
    sku_df["quantidade_sugerida_reposicao_operacional"] = [
        arredondar_quantidade_operacional(
            qtd,
            lote_minimo=config.REPOSICAO_LOTE_MINIMO_SKU,
            arredondar_multiplo=config.REPOSICAO_ARREDONDAR_MULTIPLO_LOTE,
        )
        for qtd in sku_df["quantidade_sugerida_reposicao_calculada"]
    ]

    demanda_hist = (sku_df["vendido_total_periodo"] > 0) | (sku_df["media_venda_diaria_historica_base"] > 0)
    necessidade_oper = (sku_df["quantidade_sugerida_reposicao_operacional"] > 0) | (sku_df["estoque_atual"] < 0)
    sku_df = sku_df[(demanda_hist & necessidade_oper) | (sku_df["estoque_atual"] < 0)].copy()

    if sku_df.empty:
        return render(request, "estoque/reposicao.html", {"vazio": True})

    cond_neg = sku_df["estoque_atual"] < 0
    cond_critica = (sku_df["estoque_atual"] <= 0) | (sku_df["dias_cobertura"] <= 15)
    cond_recente = cond_critica & (sku_df["vendido_30d"] > 0)
    cond_antigo = cond_critica & (sku_df["vendido_30d"] <= 0) & (sku_df["vendido_total_periodo"] > 0)

    sku_df["status_reposicao"] = "sugerido"
    sku_df.loc[cond_recente, "status_reposicao"] = "urgente com venda recente"
    sku_df.loc[cond_antigo, "status_reposicao"] = "urgente por histórico antigo"
    sku_df.loc[cond_neg, "status_reposicao"] = "saldo negativo"

    sku_df["bloco_reposicao"] = "Reposição sugerida"
    sku_df.loc[sku_df["status_reposicao"] == "urgente por histórico antigo", "bloco_reposicao"] = "Urgente por histórico antigo"
    sku_df.loc[sku_df["status_reposicao"] == "urgente com venda recente", "bloco_reposicao"] = "Urgente com venda recente"
    sku_df.loc[cond_neg, "bloco_reposicao"] = "Saldo negativo / ajuste necessário"

    mc_df = (
        sku_df.groupby(["modelo", "cor"], as_index=False)
        .agg(
            estoque_total=("estoque_atual", "sum"),
            vendido_30d=("vendido_30d", "sum"),
            vendido_historico=("vendido_total_periodo", "sum"),
            media_venda_diaria_historica=("media_venda_diaria_historica_base", "sum"),
            skus=("sku", "count"),
        )
    )
    mc_df["dias_cobertura"] = mc_df.apply(
        lambda r: (r["estoque_total"] / r["media_venda_diaria_historica"])
        if r["media_venda_diaria_historica"] > 0
        else (0.0 if r["estoque_total"] <= 0 else 9999.0),
        axis=1,
    )
    mc_df["dias_cobertura"] = pd.to_numeric(mc_df["dias_cobertura"], errors="coerce").fillna(0.0).clip(lower=0.0)
    mc_df.loc[mc_df["estoque_total"] <= 0, "dias_cobertura"] = 0.0

    mc_df["quantidade_sugerida_producao_calculada"] = [
        calcular_quantidade_sugerida_reposicao(est, media, dias_alvo_cobertura=config.REPOSICAO_COBERTURA_ALVO_DIAS)
        for est, media in zip(mc_df["estoque_total"], mc_df["media_venda_diaria_historica"])
    ]
    mc_df["quantidade_sugerida_producao"] = [
        arredondar_quantidade_operacional(
            qtd,
            lote_minimo=config.REPOSICAO_LOTE_MINIMO_MODELO_COR,
            arredondar_multiplo=config.REPOSICAO_ARREDONDAR_MULTIPLO_LOTE,
        )
        for qtd in mc_df["quantidade_sugerida_producao_calculada"]
    ]

    mc_df["situacao"] = "Reposição sugerida"
    mc_df.loc[mc_df["estoque_total"] < 0, "situacao"] = "Saldo negativo / ajuste necessário"
    mc_df.loc[
        (((mc_df["estoque_total"] <= 0) | (mc_df["dias_cobertura"] <= 15)) & (mc_df["vendido_30d"] > 0)),
        "situacao",
    ] = "Urgente com venda recente"
    mc_df.loc[
        (
            ((mc_df["estoque_total"] <= 0) | (mc_df["dias_cobertura"] <= 15))
            & (mc_df["vendido_30d"] <= 0)
            & (mc_df["vendido_historico"] > 0)
        ),
        "situacao",
    ] = "Urgente por histórico antigo"

    mc_df = mc_df[
        (mc_df["vendido_historico"] > 0)
        & ((mc_df["quantidade_sugerida_producao"] > 0) | (mc_df["estoque_total"] < 0))
    ].copy()

    mc_df["prioridade"] = 3
    mc_df.loc[mc_df["situacao"] == "Saldo negativo / ajuste necessário", "prioridade"] = 0
    mc_df.loc[mc_df["situacao"] == "Urgente com venda recente", "prioridade"] = 1
    mc_df.loc[mc_df["situacao"] == "Urgente por histórico antigo", "prioridade"] = 2
    mc_df = mc_df.sort_values(["prioridade", "dias_cobertura", "vendido_historico"], ascending=[True, True, False]).reset_index(drop=True)

    skus_neg = int((sku_df["estoque_atual"] < 0).sum())
    pecas_neg_abs = float(sku_df.loc[sku_df["estoque_atual"] < 0, "estoque_atual"].abs().sum())
    skus_urg_rec = int((sku_df["bloco_reposicao"] == "Urgente com venda recente").sum())
    skus_urg_hist = int((sku_df["bloco_reposicao"] == "Urgente por histórico antigo").sum())
    skus_sug = int((sku_df["bloco_reposicao"] == "Reposição sugerida").sum())
    pecas_sugeridas = float(
        sku_df.loc[sku_df["quantidade_sugerida_reposicao_operacional"] > 0, "quantidade_sugerida_reposicao_operacional"].sum()
    )

    # Drilldown modelo+cor (camada 2 — distribuição por tamanho)
    termo = request.GET.get("busca", "").strip().lower()
    mc_view = mc_df
    if termo:
        mask = (mc_df["modelo"] + " " + mc_df["cor"]).str.lower().str.contains(termo)
        mc_view = mc_df[mask]

    tamanho_rows = None
    mc_index_raw = request.GET.get("mc")
    if mc_index_raw is not None and not mc_view.empty:
        try:
            mc_idx = int(mc_index_raw)
        except ValueError:
            mc_idx = 0
        mc_idx = max(0, min(mc_idx, len(mc_view) - 1))
        chosen = mc_view.iloc[mc_idx]

        size_df = sku_df[(sku_df["modelo"] == chosen["modelo"]) & (sku_df["cor"] == chosen["cor"])]
        size_df = (
            size_df.groupby(["tamanho"], as_index=False)
            .agg(
                estoque_atual=("estoque_atual", "sum"),
                vendido_historico=("vendido_total_periodo", "sum"),
                vendido_30d=("vendido_30d", "sum"),
            )
        )
        total_hist = float(size_df["vendido_historico"].sum())
        total_produzir = int(chosen["quantidade_sugerida_producao"])

        dist = distribuir_quantidade_por_tamanho(
            size_df,
            total_produzir=total_produzir,
            mix_base=config.REPOSICAO_MIX_BASE_TAMANHO,
            peso_historico=config.REPOSICAO_PESO_HISTORICO_TAMANHO,
            peso_estoque=config.REPOSICAO_PESO_ESTOQUE_TAMANHO,
            peso_mix=config.REPOSICAO_PESO_MIX_BASE_TAMANHO,
        )
        size_df["sugestao_tamanho"] = dist.values if len(dist) == len(size_df) else 0
        size_df["participacao_vendas"] = (
            size_df["vendido_historico"] / total_hist if total_hist > 0 else 0.0
        )
        size_df = size_df.sort_values(by="tamanho", key=lambda col: col.map(sort_size_key))
        tamanho_rows = {
            "modelo": chosen["modelo"],
            "cor": chosen["cor"],
            "situacao": chosen["situacao"],
            "quantidade_sugerida_producao": int(chosen["quantidade_sugerida_producao"]),
            "linhas": size_df.to_dict("records"),
        }
        mc_idx_atual = mc_idx
    else:
        mc_idx_atual = None

    def bloco(nome: str) -> list[dict]:
        work = sku_df[sku_df["bloco_reposicao"] == nome].sort_values(
            ["dias_cobertura", "vendido_total_periodo"], ascending=[True, False]
        ).head(limit)
        return work.to_dict("records")

    return render(request, "estoque/reposicao.html", {
        "vazio": False,
        "limit": limit,
        "skus_neg": skus_neg,
        "pecas_neg_abs": pecas_neg_abs,
        "skus_urg_rec": skus_urg_rec,
        "skus_urg_hist": skus_urg_hist,
        "skus_sug": skus_sug,
        "pecas_sugeridas": pecas_sugeridas,
        "mc_df": mc_df.to_dict("records"),
        "mc_view": list(enumerate(mc_view.to_dict("records"))),
        "busca": termo,
        "mc_idx_atual": mc_idx_atual,
        "tamanho": tamanho_rows,
        "bloco_saldo_negativo": bloco("Saldo negativo / ajuste necessário"),
        "bloco_urgente_recente": bloco("Urgente com venda recente"),
        "bloco_urgente_historico": bloco("Urgente por histórico antigo"),
        "bloco_sugerida": bloco("Reposição sugerida"),
        "config": {
            "cobertura_alvo": config.REPOSICAO_COBERTURA_ALVO_DIAS,
            "lote_minimo_mc": config.REPOSICAO_LOTE_MINIMO_MODELO_COR,
            "lote_minimo_sku": config.REPOSICAO_LOTE_MINIMO_SKU,
        },
    })
