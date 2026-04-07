"""
Cálculo de pontos e regras da Liga Quarta Scaff.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src import database as db


def calcular_pontos_jogo(games_vencedor: int, games_perdedor: int) -> tuple[int, int]:
    """
    Retorna (pontos_vencedor, pontos_perdedor) para um jogo.

    Regras:
    - Vitória normal: 10 x (games do perdedor)
    - Vitória 6x0: 12 x (-5)
    - Tiebreak (7x6): 10 x 6
    """
    if games_vencedor > games_perdedor:
        if games_vencedor == 6 and games_perdedor == 0:
            return 12, -5
        return 10, games_perdedor
    # Nunca deve chegar aqui se chamar corretamente
    return games_vencedor, 10


def eh_vitoria_dupla1(games_d1: int, games_d2: int) -> bool:
    return games_d1 > games_d2


def validar_placar(games_d1: int, games_d2: int) -> tuple[bool, str]:
    """Valida se o placar é válido nas regras de beach tennis."""
    if games_d1 == games_d2:
        return False, "Placar não pode ser empate (exceto 6x6 que vira 7x6 no tiebreak)."
    # Resultados válidos: 6x0–6x4, 7x5 (empate em 5x5 → continua), 7x6 (tiebreak)
    vencedor = max(games_d1, games_d2)
    perdedor = min(games_d1, games_d2)
    if vencedor == 7 and perdedor in (5, 6):
        return True, ""  # 7x5 ou 7x6 (tiebreak)
    if vencedor == 6 and 0 <= perdedor <= 4:
        return True, ""
    return False, f"Placar inválido: {games_d1}x{games_d2}. Válidos: 6-0 a 6-4, 7-5 ou 7-6."


def calcular_pontuacao_rodada(rodada_id: int) -> dict[int, dict]:
    """
    Calcula e persiste a pontuação de todos os jogadores de uma rodada.

    Retorna dict: {jogador_id: {pontos, jogos_ganhos, jogos_perdidos, tem_beer}}
    """
    jogos = db.list_jogos_rodada(rodada_id)
    resultados = {r["jogo_id"]: r for r in db.list_resultados_rodada(rodada_id)}

    # Acumula pontos por jogador
    pontuacao: dict[int, dict] = {}

    def get_ou_criar(jid: int) -> dict:
        if jid not in pontuacao:
            pontuacao[jid] = {
                "pontos": 0,
                "jogos_ganhos": 0,
                "jogos_perdidos": 0,
                "levou_6x0": False,
            }
        return pontuacao[jid]

    for jogo in jogos:
        res = resultados.get(jogo["id"])
        if res is None:
            continue  # resultado não lançado

        g1, g2 = res["games_dupla1"], res["games_dupla2"]
        d1_ganhou = g1 > g2
        pts_d1, pts_d2 = (
            calcular_pontos_jogo(g1, g2) if d1_ganhou else calcular_pontos_jogo(g2, g1)[::-1]
        )

        dupla1 = [jogo["dupla1_j1"], jogo["dupla1_j2"]]
        dupla2 = [jogo["dupla2_j1"], jogo["dupla2_j2"]]

        for jid in dupla1:
            if jid is None:
                continue
            p = get_ou_criar(jid)
            p["pontos"] += pts_d1
            if d1_ganhou:
                p["jogos_ganhos"] += 1
                if g1 == 6 and g2 == 0:
                    pass  # venceu 6x0, não precisa marcar para cerveja
            else:
                p["jogos_perdidos"] += 1
                if g2 == 6 and g1 == 0:
                    p["levou_6x0"] = True

        for jid in dupla2:
            if jid is None:
                continue
            p = get_ou_criar(jid)
            p["pontos"] += pts_d2
            if not d1_ganhou:
                p["jogos_ganhos"] += 1
                if g2 == 6 and g1 == 0:
                    pass
            else:
                p["jogos_perdidos"] += 1
                if g1 == 6 and g2 == 0:
                    p["levou_6x0"] = True

    # Determina quem deve cerveja e persiste
    for jid, dados in pontuacao.items():
        deve_beer = int(dados["levou_6x0"] or dados["jogos_ganhos"] == 0)
        db.upsert_pontuacao(
            jogador_id=jid,
            rodada_id=rodada_id,
            pontos=dados["pontos"],
            jogos_ganhos=dados["jogos_ganhos"],
            jogos_perdidos=dados["jogos_perdidos"],
            tem_beer=deve_beer,
        )
        pontuacao[jid]["tem_beer"] = deve_beer

    return pontuacao


def calcular_detalhe_por_jogo(rodada_id: int) -> list[dict]:
    """
    Retorna pontuação detalhada por jogador e por jogo interno da rodada.
    Cada dict: {jogador_id, nome, j1, j2, j3, j4, total, tem_beer}
    """
    jogos = db.list_jogos_rodada(rodada_id)
    resultados = {r["jogo_id"]: r for r in db.list_resultados_rodada(rodada_id)}
    pontuacoes = {p["jogador_id"]: p for p in db.get_pontuacao_rodada(rodada_id)}
    todos_j = {j["id"]: j["nome"] for j in db.list_jogadores(apenas_ativos=False)}

    por_jogador: dict[int, dict] = {}

    def _get(jid: int) -> dict:
        if jid not in por_jogador:
            por_jogador[jid] = {"nome": todos_j.get(jid, "?"), "jogos": {}}
        return por_jogador[jid]

    for jogo in jogos:
        res = resultados.get(jogo["id"])
        if res is None:
            continue
        g1, g2 = res["games_dupla1"], res["games_dupla2"]
        d1_ganhou = g1 > g2
        pts_d1, pts_d2 = (
            calcular_pontos_jogo(g1, g2) if d1_ganhou else calcular_pontos_jogo(g2, g1)[::-1]
        )
        ri = jogo["rodada_interna"]
        for jid in [jogo["dupla1_j1"], jogo["dupla1_j2"]]:
            if jid is not None:
                _get(jid)["jogos"][ri] = pts_d1
        for jid in [jogo["dupla2_j1"], jogo["dupla2_j2"]]:
            if jid is not None:
                _get(jid)["jogos"][ri] = pts_d2

    result = []
    for jid, dados in por_jogador.items():
        pts_obj = pontuacoes.get(jid) or {}
        result.append({
            "jogador_id": jid,
            "nome": dados["nome"],
            "j1": dados["jogos"].get(1),
            "j2": dados["jogos"].get(2),
            "j3": dados["jogos"].get(3),
            "j4": dados["jogos"].get(4),
            "total": pts_obj.get("pontos", sum(dados["jogos"].values())),
            "tem_beer": bool(pts_obj.get("tem_beer", 0)),
        })
    return sorted(result, key=lambda x: (-x["total"], x["nome"]))


def get_beer_list(rodada_id: int) -> list[str]:
    """Retorna nomes dos jogadores que devem cerveja na rodada."""
    pontuacoes = db.get_pontuacao_rodada(rodada_id)
    return [p["nome"] for p in pontuacoes if p["tem_beer"]]
