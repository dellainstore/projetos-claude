"""
Página de histórico da Liga Quarta Scaff.
Visualiza todas as rodadas concluídas, resultados e estatísticas.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth
from src.utils import fmt_data

auth.require_login()

st.title("📊 Histórico")

# ── Seleção de temporada ──────────────────────────────────────────────────────
temporadas = db.list_temporadas()
if not temporadas:
    st.warning("Nenhuma temporada cadastrada.")
    st.stop()

temporada = st.selectbox(
    "Temporada",
    options=temporadas,
    format_func=lambda t: t["nome"],
    index=next((i for i, t in enumerate(temporadas) if t["ativa"]), 0),
)
tid = temporada["id"]

rodadas = db.list_rodadas(tid)
rodadas_concluidas = [r for r in rodadas if r["status"] == "concluida"]

if not rodadas_concluidas:
    st.info("Nenhuma rodada concluída nesta temporada.")
    st.stop()

import pandas as pd
todos_jogadores = db.list_jogadores(apenas_ativos=False)
nomes_map = {j["id"]: j["nome"] for j in todos_jogadores}

# ── Resumo por temporada ──────────────────────────────────────────────────────
st.subheader(f"Resumo — {temporada['nome']}")

todas_pontuacoes = db.get_pontuacoes_temporada(tid)

if todas_pontuacoes:
    # Agrega por jogador
    por_jogador: dict[str, dict] = {}
    for p in todas_pontuacoes:
        nome = p["nome"]
        if nome not in por_jogador:
            por_jogador[nome] = {"pontos_total": 0, "ganhos": 0, "perdidos": 0, "rodadas": 0}
        por_jogador[nome]["pontos_total"] += p["pontos"]
        por_jogador[nome]["ganhos"] += p["jogos_ganhos"]
        por_jogador[nome]["perdidos"] += p["jogos_perdidos"]
        por_jogador[nome]["rodadas"] += 1

    dados_resumo = [
        {
            "Jogador": nome,
            "Rodadas": d["rodadas"],
            "Jogos Ganhos": d["ganhos"],
            "Jogos Perdidos": d["perdidos"],
            "% Vitórias": f"{d['ganhos'] / max(d['ganhos'] + d['perdidos'], 1) * 100:.0f}%",
            "Pontos Acumulados": d["pontos_total"],
        }
        for nome, d in sorted(por_jogador.items(), key=lambda x: x[1]["pontos_total"], reverse=True)
    ]
    st.dataframe(pd.DataFrame(dados_resumo), use_container_width=True, hide_index=True)

final = db.get_final(tid)
if final:
    jogos_final = db.get_jogos_final(final["id"])
    jogos_map = {(j["serie"], j["fase"]): j for j in jogos_final}

    def _dupla_nome(jogo: dict, vencedor: int | None) -> str:
        if not jogo or vencedor not in (1, 2):
            return "—"
        if vencedor == 1:
            return f"{nomes_map.get(jogo['dupla1_p1'], '?')} / {nomes_map.get(jogo['dupla1_p2'], '?')}"
        return f"{nomes_map.get(jogo['dupla2_p1'], '?')} / {nomes_map.get(jogo['dupla2_p2'], '?')}"

    def _vice_nome(jogo: dict, vencedor: int | None) -> str:
        if not jogo or vencedor not in (1, 2):
            return "—"
        if vencedor == 2:
            return f"{nomes_map.get(jogo['dupla1_p1'], '?')} / {nomes_map.get(jogo['dupla1_p2'], '?')}"
        return f"{nomes_map.get(jogo['dupla2_p1'], '?')} / {nomes_map.get(jogo['dupla2_p2'], '?')}"

    resumo_final = []
    for serie in ("ouro", "prata"):
        jf = jogos_map.get((serie, "final"))
        resumo_final.append({
            "Série": "Ouro" if serie == "ouro" else "Prata",
            "Campeão": _dupla_nome(jf, jf["vencedor"] if jf else None),
            "Vice": _vice_nome(jf, jf["vencedor"] if jf else None),
            "Placar Final": (f"{jf['games_d1']} × {jf['games_d2']}" if jf and jf["games_d1"] is not None else "—"),
        })

    st.divider()
    st.subheader("Final da Temporada")
    st.dataframe(pd.DataFrame(resumo_final), use_container_width=True, hide_index=True)

# ── Histórico por rodada ──────────────────────────────────────────────────────
st.divider()
st.subheader("Rodadas Concluídas")

def nome_jogo(jogo: dict, slot: str) -> str:
    jid = jogo.get(slot)
    if jid is not None:
        return nomes_map.get(jid, str(jid))
    nome_vis = jogo.get(f"{slot}_nome")
    return nome_vis if nome_vis else "?"

for rodada in reversed(rodadas_concluidas):
    with st.expander(f"Rodada {rodada['numero']} — {fmt_data(rodada['data'])}  ({rodada['n_jogadores']} jogadores)"):
        jogos = db.list_jogos_rodada(rodada["id"])
        resultados_map = {r["jogo_id"]: r for r in db.list_resultados_rodada(rodada["id"])}

        if not jogos:
            st.caption("Nenhum jogo encontrado.")
            continue

        # Tabela de resultados
        rodadas_internas = sorted({j["rodada_interna"] for j in jogos})
        quadras = sorted({j["quadra"] for j in jogos})
        lookup = {(j["rodada_interna"], j["quadra"]): j for j in jogos}

        linhas_jogos = []
        for ri in rodadas_internas:
            for q in quadras:
                jogo = lookup.get((ri, q))
                if not jogo:
                    continue
                res = resultados_map.get(jogo["id"])
                if res:
                    g1, g2 = res["games_dupla1"], res["games_dupla2"]
                    vencedor = (
                        f"{nome_jogo(jogo,'dupla1_j1')}/{nome_jogo(jogo,'dupla1_j2')}"
                        if g1 > g2 else
                        f"{nome_jogo(jogo,'dupla2_j1')}/{nome_jogo(jogo,'dupla2_j2')}"
                    )
                    placar = f"{g1} × {g2}"
                else:
                    vencedor = "—"
                    placar = "—"

                linhas_jogos.append({
                    "Jogo": ri,
                    "Quadra": q,
                    "Dupla 1": f"{nome_jogo(jogo,'dupla1_j1')} / {nome_jogo(jogo,'dupla1_j2')}",
                    "Dupla 2": f"{nome_jogo(jogo,'dupla2_j1')} / {nome_jogo(jogo,'dupla2_j2')}",
                    "Placar": placar,
                    "Vencedor": vencedor,
                })

        if linhas_jogos:
            st.dataframe(pd.DataFrame(linhas_jogos), use_container_width=True, hide_index=True)

        # Pontuação da rodada
        pontuacoes = db.get_pontuacao_rodada(rodada["id"])
        beer_r = [p["nome"] for p in pontuacoes if p["tem_beer"]]

        if pontuacoes:
            st.write("**Pontuação da rodada:**")
            dados_pts = [
                {
                    "Pos": i + 1,
                    "Jogador": p["nome"],
                    "Pontos": p["pontos"],
                    "Ganhos": p["jogos_ganhos"],
                    "Perdidos": p["jogos_perdidos"],
                }
                for i, p in enumerate(pontuacoes)
            ]
            st.dataframe(pd.DataFrame(dados_pts), use_container_width=True, hide_index=True)

        if beer_r:
            st.warning(f"🍺 Cerveja: {', '.join(beer_r)}")
        else:
            st.success("✅ Ninguém devia cerveja nessa rodada.")
