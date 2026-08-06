"""
Cálculo de ranking da Liga Quarta Scaff.

Regras de descarte (dinâmicas por número de rodadas concluídas):
- até 2 rodadas: sem descarte — exibe soma total
- 3 rodadas    : 1 descarte — o menor valor de cada jogador
- 4+ rodadas   : 2 descartes — os 2 menores valores de cada jogador

Ausências (rodadas não disputadas) valem 0 ponto e entram no cálculo de descarte.
Todos os jogadores exibem suas rodadas descartadas na tabela.

Critério de desempate (quando o total COM descarte empata):
1º) maior soma total SEM descarte (todas as rodadas, sem descartar nada)
2º) maior número de jogos ganhos durante a temporada (rodadas concluídas)
3º) nome em ordem alfabética
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import database as db


def _n_descartes_efetivo(n_rodadas_concluidas: int) -> int:
    """Retorna quantos descartes aplicar baseado nas rodadas concluídas."""
    if n_rodadas_concluidas <= 2:
        return 0
    if n_rodadas_concluidas == 3:
        return 1
    return 2


def calcular_ranking(temporada_id: int) -> list[dict]:
    """
    Calcula o ranking completo de uma temporada.

    Retorna lista ordenada de dicts:
    {
        jogador_id, nome,
        pontos_por_rodada: {rodada_num: pontos},  # apenas rodadas disputadas
        rodadas_descartadas: set de numeros de rodadas descartadas,
        total: pontos somados (sem as descartadas),
        total_sem_descarte: pontos somados de TODAS as rodadas (critério de desempate),
        jogos_ganhos_temporada: total de jogos ganhos na temporada (critério de desempate),
        posicao: int,
        variacao: int (positivo = subiu, negativo = caiu, 0 = igual, None = estreante)
    }
    """
    rodadas = db.list_rodadas(temporada_id)
    rodadas_concluidas = [r for r in rodadas if r["status"] == "concluida"]

    if not rodadas_concluidas:
        return []

    n_desc = _n_descartes_efetivo(len(rodadas_concluidas))
    nums_concluidas = {r["numero"] for r in rodadas_concluidas}

    # Coleta todas as pontuações (apenas rodadas disputadas)
    todas_pontuacoes = db.get_pontuacoes_temporada(temporada_id)

    # Agrupa por jogador
    pontuacoes_por_jogador: dict[int, dict] = {}
    for p in todas_pontuacoes:
        jid = p["jogador_id"]
        if jid not in pontuacoes_por_jogador:
            pontuacoes_por_jogador[jid] = {
                "nome": p["nome"],
                "pontos_por_rodada": {},
                "jogos_ganhos_por_rodada": {},
            }
        pontuacoes_por_jogador[jid]["pontos_por_rodada"][p["rodada_numero"]] = p["pontos"]
        pontuacoes_por_jogador[jid]["jogos_ganhos_por_rodada"][p["rodada_numero"]] = p["jogos_ganhos"]

    ranking: list[dict] = []
    for jid, dados in pontuacoes_por_jogador.items():
        pts_disputadas = dados["pontos_por_rodada"]

        # Mapa completo incluindo 0 para ausências (usado no cálculo de descarte)
        pts_completo = {rn: pts_disputadas.get(rn, 0) for rn in nums_concluidas}

        # Descarta os N piores (incluindo zeros de ausência)
        descartadas: set[int] = set()
        if n_desc > 0:
            ordenadas = sorted(pts_completo.keys(), key=lambda r: pts_completo[r])
            descartadas = set(ordenadas[:n_desc])

        total = sum(pts for r, pts in pts_completo.items() if r not in descartadas)
        total_sem_descarte = sum(pts_completo.values())
        jogos_ganhos_temporada = sum(
            dados["jogos_ganhos_por_rodada"].get(rn, 0) for rn in nums_concluidas
        )

        ranking.append({
            "jogador_id": jid,
            "nome": dados["nome"],
            "pontos_por_rodada": pts_disputadas,   # apenas rodadas disputadas (para exibir —)
            "rodadas_descartadas": descartadas,
            "total": total,
            "total_sem_descarte": total_sem_descarte,
            "jogos_ganhos_temporada": jogos_ganhos_temporada,
            "posicao": 0,
            "variacao": None,
        })

    # Ordena por total (com descarte) desc; empate: total sem descarte desc;
    # empate: jogos ganhos na temporada desc; empate: nome asc
    ranking.sort(key=lambda x: (
        -x["total"], -x["total_sem_descarte"], -x["jogos_ganhos_temporada"], x["nome"],
    ))
    for idx, entry in enumerate(ranking):
        entry["posicao"] = idx + 1

    # Calcula variação: compara com ranking sem a última rodada concluída
    if len(rodadas_concluidas) >= 2:
        ranking_anterior = _calcular_ranking_sem_ultima(temporada_id, rodadas_concluidas)
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
) -> list[dict]:
    """Calcula ranking sem a última rodada (para calcular variação)."""
    if len(rodadas_concluidas) < 2:
        return []

    rodadas_anteriores = rodadas_concluidas[:-1]
    nums_anteriores = {r["numero"] for r in rodadas_anteriores}
    n_desc = _n_descartes_efetivo(len(rodadas_anteriores))

    todas = db.get_pontuacoes_temporada(temporada_id)
    por_jogador: dict[int, dict] = {}
    for p in todas:
        if p["rodada_numero"] not in nums_anteriores:
            continue
        jid = p["jogador_id"]
        if jid not in por_jogador:
            por_jogador[jid] = {"nome": p["nome"], "pts": {}, "jogos_ganhos": {}}
        por_jogador[jid]["pts"][p["rodada_numero"]] = p["pontos"]
        por_jogador[jid]["jogos_ganhos"][p["rodada_numero"]] = p["jogos_ganhos"]

    resultado = []
    for jid, dados in por_jogador.items():
        pts_disputadas = dados["pts"]
        # Inclui 0 para ausências nas rodadas anteriores
        pts_completo = {rn: pts_disputadas.get(rn, 0) for rn in nums_anteriores}

        descartadas: set[int] = set()
        if n_desc > 0:
            ordenadas = sorted(pts_completo.keys(), key=lambda r: pts_completo[r])
            descartadas = set(ordenadas[:n_desc])

        total = sum(v for r, v in pts_completo.items() if r not in descartadas)
        total_sem_descarte = sum(pts_completo.values())
        jogos_ganhos_temporada = sum(
            dados["jogos_ganhos"].get(rn, 0) for rn in nums_anteriores
        )
        resultado.append({
            "jogador_id": jid,
            "total": total,
            "total_sem_descarte": total_sem_descarte,
            "jogos_ganhos_temporada": jogos_ganhos_temporada,
            "posicao": 0,
        })

    resultado.sort(key=lambda x: (
        -x["total"], -x["total_sem_descarte"], -x["jogos_ganhos_temporada"],
    ))
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
