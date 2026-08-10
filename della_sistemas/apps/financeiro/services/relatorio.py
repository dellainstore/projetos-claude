"""Agregações do Dashboard Faturamento.

Faturamento, quantidade de pedidos e faturamento por loja/canal vêm da MESMA
fonte que o módulo Metas usa (`apps.metas.services.relatorio`, que lê o CSV
`vendas_atendidas_<ano>.csv`) — não duplica sync: esse CSV já é atualizado
pelos crons de `vendas_atendidas` (4x/dia) e revisado mensalmente (mês atual +
2 anteriores) para capturar cancelamento/troca de situação no Bling. Por isso
os totais aqui sempre batem com os do Metas.

Ranking de produtos por modelo precisa de detalhe por item (produto_id), que
não existe nesse CSV (lá é 1 linha por pedido). Para isso lemos a tabela
`vendas` do `apps.estoque`, sincronizada por um cron próprio (2x/dia, janela
= mês corrente inteiro, mais backfill mensal dos últimos meses) — mesma
janela "mês inteiro" usada no CSV, para não ficar incoerente com o
faturamento.
"""
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from apps.estoque.services.catalog_bridge import carregar_catalogo
from apps.estoque.services.db import get_conn
from apps.metas.services import relatorio as metas_svc

ANO_MINIMO = 2026

MESES_LABEL = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]


def anos_disponiveis() -> list[int]:
    """Anos com CSV de vendas atendidas (mesma fonte do Metas)."""
    return sorted({ano for ano, _mes, _label in metas_svc.meses_disponiveis() if ano >= ANO_MINIMO})


def meses_disponiveis(anos: list[int]) -> list[int]:
    """Meses (1-12) com dado no CSV, dentro dos anos informados."""
    if not anos:
        return []
    anos_set = set(anos)
    return sorted({mes for ano, mes, _label in metas_svc.meses_disponiveis() if ano in anos_set})


def carregar_pedidos(anos: list[int], meses: list[int] | None = None) -> list[dict]:
    """Pedidos (nível CSV: 1 linha por pedido) — mesma fonte do Metas."""
    pedidos: list[dict] = []
    for ano in anos:
        pedidos.extend(metas_svc.carregar_vendas_periodo(ano, 1, ano, 12))
    if not meses:
        return pedidos
    meses_set = set(meses)
    return [p for p in pedidos if int(p["data"][5:7]) in meses_set]


def _carregar_vendas_produtos_anos(anos: list[int]) -> pd.DataFrame:
    """Vendas por item/produto (tabela `vendas` do apps.estoque) — só usada
    para o ranking por modelo, que precisa de produto_id."""
    if not anos:
        return pd.DataFrame()

    conn = get_conn()
    try:
        placeholders = ",".join("?" * len(anos))
        df = pd.read_sql_query(
            f"""
            SELECT produto_id, quantidade, data, pedido_id, situacao_id, valor
            FROM vendas
            WHERE substr(data, 1, 4) IN ({placeholders})
            """,
            conn,
            params=[str(a) for a in anos],
        )
    finally:
        conn.close()

    if df.empty:
        return df

    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").fillna(0.0)
    df["quantidade"] = pd.to_numeric(df["quantidade"], errors="coerce").fillna(0.0)
    df["mes"] = df["data"].str.slice(5, 7).astype(int)

    catalogo = carregar_catalogo()
    df = df.merge(catalogo[["produto_id", "nome", "modelo"]], on="produto_id", how="left")
    df["modelo"] = df["modelo"].astype(str).str.strip()
    df["nome"] = df["nome"].astype(str).str.strip()
    sem_modelo = df["modelo"] == ""
    df.loc[sem_modelo, "modelo"] = df.loc[sem_modelo, "nome"]
    sem_nome = df["modelo"] == ""
    df.loc[sem_nome, "modelo"] = "Produto #" + df.loc[sem_nome, "produto_id"].astype(str)
    return df


def carregar_vendas_produtos(anos: list[int], meses: list[int] | None = None) -> pd.DataFrame:
    """DataFrame de itens vendidos (nível produto) — só para ranking por modelo."""
    df = _carregar_vendas_produtos_anos(anos)
    if df.empty or not meses:
        return df
    return df[df["mes"].isin(meses)]


def resumo_cards(pedidos: list[dict], produtos_df: pd.DataFrame) -> dict:
    faturamento = float(sum((p["total"] for p in pedidos), Decimal("0")))
    qtd_produtos = float(sum(p["qtd_itens"] for p in pedidos))

    produto_top_qtd = None
    produto_top_valor = None
    if not produtos_df.empty:
        por_modelo_qtd = produtos_df.groupby("modelo")["quantidade"].sum().sort_values(ascending=False)
        por_modelo_valor = produtos_df.groupby("modelo")["valor"].sum().sort_values(ascending=False)
        if not por_modelo_qtd.empty:
            produto_top_qtd = {"nome": por_modelo_qtd.index[0], "valor": float(por_modelo_qtd.iloc[0])}
        if not por_modelo_valor.empty:
            produto_top_valor = {"nome": por_modelo_valor.index[0], "valor": float(por_modelo_valor.iloc[0])}

    return {
        "faturamento": faturamento,
        "qtd_produtos": qtd_produtos,
        "produto_top_qtd": produto_top_qtd,
        "produto_top_valor": produto_top_valor,
    }


def ranking_produtos(df: pd.DataFrame, criterio: str, limit: int | None = None) -> list[dict]:
    """Ranking completo por padrão (limit=None) — a UI rola a lista, não corta em 10."""
    if df.empty:
        return []
    coluna = "valor" if criterio == "valor" else "quantidade"
    agrupado = df.groupby("modelo").agg(valor=("valor", "sum"), quantidade=("quantidade", "sum")).sort_values(
        coluna, ascending=False
    )
    if limit:
        agrupado = agrupado.head(limit)
    return [
        {"nome": nome, "valor": float(row["valor"]), "quantidade": float(row["quantidade"])}
        for nome, row in agrupado.iterrows()
    ]


def faturamento_mensal(ano: int) -> dict:
    """Sempre retorna os 12 meses (quem decide o recorte de meses com dado é a view)."""
    pedidos = metas_svc.carregar_vendas_periodo(ano, 1, ano, 12)
    valores = [0.0] * 12
    quantidades = [0.0] * 12
    for p in pedidos:
        idx = int(p["data"][5:7]) - 1
        if 0 <= idx < 12:
            valores[idx] += float(p["total"])
            quantidades[idx] += float(p["qtd_itens"])
    return {"labels": MESES_LABEL, "valores": valores, "quantidades": quantidades}


def vendas_por_loja(pedidos: list[dict]) -> list[dict]:
    linhas = metas_svc.calcular_lojas(pedidos)
    return [{"canal": linha["label"], "valor": float(linha["total"])} for linha in linhas if linha["total"] > 0]
