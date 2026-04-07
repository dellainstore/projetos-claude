"""
Cálculo de ranking da Liga Quarta Scaff.

Regras:
- 8 rodadas por temporada
- Descarta as N piores rodadas de cada jogador (apenas das que participou)
- Jogadores ausentes na rodada ficam com 0 pontos
- Ranking ordenado por total de pontos
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import database as db


def calcular_ranking(temporada_id: int) -> list[dict]:
    """
    Calcula o ranking completo de uma temporada.

    Retorna lista ordenada de dicts:
    {
        jogador_id, nome,
        pontos_por_rodada: {rodada_num: pontos},
        rodadas_descartadas: set de numeros de rodadas descartadas,
        total: pontos somados (sem as descartadas),
        posicao: int,
        variacao: int (positivo = subiu, negativo = caiu, 0 = igual, None = estreante)
    }
    """
    temporada = db.get_temporada(temporada_id)
    if not temporada:
        return []

    n_descartadas = temporada["n_descartadas"]
    rodadas = db.list_rodadas(temporada_id)
    rodadas_concluidas = [r for r in rodadas if r["status"] == "concluida"]

    if not rodadas_concluidas:
        return []

    # Coleta todas as pontuações
    todas_pontuacoes = db.get_pontuacoes_temporada(temporada_id)

    # Agrupa por jogador
    pontuacoes_por_jogador: dict[int, dict] = {}
    for p in todas_pontuacoes:
        jid = p["jogador_id"]
        if jid not in pontuacoes_por_jogador:
            pontuacoes_por_jogador[jid] = {
                "nome": p["nome"],
                "pontos_por_rodada": {},
            }
        pontuacoes_por_jogador[jid]["pontos_por_rodada"][p["rodada_numero"]] = p["pontos"]

    # Apenas jogadores que participaram de pelo menos 1 rodada aparecem no ranking
    ranking: list[dict] = []
    for jid, dados in pontuacoes_por_jogador.items():
        pts_rodadas = dados["pontos_por_rodada"]
        rodadas_jogadas = list(pts_rodadas.keys())

        # Descarta as N piores rodadas que o jogador PARTICIPOU
        descartadas: set[int] = set()
        if n_descartadas > 0 and len(rodadas_jogadas) > n_descartadas:
            ordenadas_por_pts = sorted(rodadas_jogadas, key=lambda r: pts_rodadas[r])
            descartadas = set(ordenadas_por_pts[:n_descartadas])

        total = sum(
            pts for r, pts in pts_rodadas.items()
            if r not in descartadas
        )

        ranking.append({
            "jogador_id": jid,
            "nome": dados["nome"],
            "pontos_por_rodada": pts_rodadas,
            "rodadas_descartadas": descartadas,
            "total": total,
            "posicao": 0,
            "variacao": None,
        })

    # Ordena por total desc, depois nome asc como desempate
    ranking.sort(key=lambda x: (-x["total"], x["nome"]))
    for idx, entry in enumerate(ranking):
        entry["posicao"] = idx + 1

    # Calcula variação: compara com ranking sem a última rodada concluída
    if len(rodadas_concluidas) >= 2:
        ranking_anterior = _calcular_ranking_sem_ultima(temporada_id, rodadas_concluidas, n_descartadas)
        pos_anterior = {r["jogador_id"]: r["posicao"] for r in ranking_anterior}
        for entry in ranking:
            pos_ant = pos_anterior.get(entry["jogador_id"])
            if pos_ant is not None:
                entry["variacao"] = pos_ant - entry["posicao"]  # positivo = subiu
            else:
                entry["variacao"] = None  # estreante

    return ranking


def _calcular_ranking_sem_ultima(
    temporada_id: int,
    rodadas_concluidas: list,
    n_descartadas: int,
) -> list[dict]:
    """Calcula ranking sem a última rodada (para calcular variação)."""
    if len(rodadas_concluidas) < 2:
        return []

    rodadas_anteriores = rodadas_concluidas[:-1]
    nums_anteriores = {r["numero"] for r in rodadas_anteriores}

    todas = db.get_pontuacoes_temporada(temporada_id)
    por_jogador: dict[int, dict] = {}
    for p in todas:
        if p["rodada_numero"] not in nums_anteriores:
            continue
        jid = p["jogador_id"]
        if jid not in por_jogador:
            por_jogador[jid] = {"nome": p["nome"], "pts": {}}
        por_jogador[jid]["pts"][p["rodada_numero"]] = p["pontos"]

    resultado = []
    for jid, dados in por_jogador.items():
        pts = dados["pts"]
        rodadas_jogadas = list(pts.keys())
        descartadas: set[int] = set()
        if n_descartadas > 0 and len(rodadas_jogadas) > n_descartadas:
            ordenadas = sorted(rodadas_jogadas, key=lambda r: pts[r])
            descartadas = set(ordenadas[:n_descartadas])
        total = sum(v for r, v in pts.items() if r not in descartadas)
        resultado.append({"jogador_id": jid, "total": total, "posicao": 0})

    resultado.sort(key=lambda x: -x["total"])
    for idx, r in enumerate(resultado):
        r["posicao"] = idx + 1
    return resultado


def formatar_variacao(variacao) -> str:
    """Retorna string formatada para exibição da variação de posição."""
    if variacao is None:
        return "★"  # estreante
    if variacao > 0:
        return f"▲{variacao}"
    if variacao < 0:
        return f"▼{abs(variacao)}"
    return "—"
