"""
Página de Final da Liga Quarta Scaff.
Semifinais e finais das séries Ouro e Prata.
Disponível após as 8 rodadas da temporada serem concluídas.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth
from src.ranking import calcular_ranking
from src.scoring import validar_placar

auth.require_organizer()

st.title("🏆 Final da Temporada")

# ── Seleção de temporada ──────────────────────────────────────────────────────
temporadas = db.list_temporadas()
if not temporadas:
    st.warning("Crie uma temporada primeiro.")
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
n_necessarias = temporada["n_rodadas"]

if len(rodadas_concluidas) < n_necessarias:
    faltam = n_necessarias - len(rodadas_concluidas)
    st.info(
        f"A final só pode ser gerada após as **{n_necessarias}** rodadas da temporada. "
        f"Faltam **{faltam}** rodada(s) concluída(s)."
    )
    st.stop()

# ── Ranking base ──────────────────────────────────────────────────────────────
ranking = calcular_ranking(tid)
nomes_map = {r["jogador_id"]: r["nome"] for r in ranking}


def nomes_dupla(p1_id, p2_id) -> str:
    return f"{nomes_map.get(p1_id, '?')} / {nomes_map.get(p2_id, '?')}"


# ── Final existente? ──────────────────────────────────────────────────────────
final = db.get_final(tid)

if not final:
    st.info("Todas as rodadas concluídas! Gere o chaveamento da final.")
    ouro = [r for r in ranking if r["posicao"] <= 8]
    prata = [r for r in ranking if 9 <= r["posicao"] <= 16]

    if len(ouro) < 8 or len(prata) < 8:
        st.warning("São necessários pelo menos 8 jogadores em cada série para gerar a final.")
    else:
        col_o, col_p = st.columns(2)
        with col_o:
            st.markdown("**Série Ouro**")
            st.write(f"SF1: ({ouro[0]['nome']} / {ouro[1]['nome']}) × ({ouro[6]['nome']} / {ouro[7]['nome']})")
            st.write(f"SF2: ({ouro[2]['nome']} / {ouro[3]['nome']}) × ({ouro[4]['nome']} / {ouro[5]['nome']})")
        with col_p:
            st.markdown("**Série Prata**")
            st.write(f"SF1: ({prata[0]['nome']} / {prata[1]['nome']}) × ({prata[6]['nome']} / {prata[7]['nome']})")
            st.write(f"SF2: ({prata[2]['nome']} / {prata[3]['nome']}) × ({prata[4]['nome']} / {prata[5]['nome']})")

        if auth.is_admin() or auth.is_organizer():
            if st.button("🏆 Gerar Chaveamento Final", type="primary", use_container_width=True):
                db.create_final(tid, ranking)
                st.success("Chaveamento gerado!")
                st.rerun()
    st.stop()

# ── Exibe chaveamento ─────────────────────────────────────────────────────────
final_id = final["id"]
jogos_final = db.get_jogos_final(final_id)

# Organiza por serie e fase
def jogos_por(serie, fase):
    return next((j for j in jogos_final if j["serie"] == serie and j["fase"] == fase), None)


def _render_jogo_final(jogo_f, label: str, pode_editar: bool):
    """Renderiza um jogo da final com placar."""
    if jogo_f is None:
        st.info(f"{label}: aguardando semis...")
        return

    d1 = nomes_dupla(jogo_f["dupla1_p1"], jogo_f["dupla1_p2"])
    d2 = nomes_dupla(jogo_f["dupla2_p1"], jogo_f["dupla2_p2"])
    vencedor = jogo_f["vencedor"]
    g1 = jogo_f["games_d1"]
    g2 = jogo_f["games_d2"]

    with st.container(border=True):
        st.markdown(f"**{label}**")

        if pode_editar and vencedor is None:
            ca, cb, cc = st.columns([4, 4, 2])
            with ca:
                st.write(f"🔵 {d1}")
            with cb:
                st.write(f"🔴 {d2}")
            with cc:
                pass

            edit_g1, edit_g2 = st.columns(2)
            with edit_g1:
                ng1 = st.selectbox("Placar D1", options=list(range(8)), index=0,
                                   key=f"fg1_{jogo_f['id']}", label_visibility="collapsed")
            with edit_g2:
                ng2 = st.selectbox("Placar D2", options=list(range(8)), index=0,
                                   key=f"fg2_{jogo_f['id']}", label_visibility="collapsed")

            valido_f, erro_f = validar_placar(ng1, ng2)
            if not valido_f:
                st.warning(erro_f, icon="⚠️")
            elif st.button(f"💾 Salvar resultado", key=f"fsave_{jogo_f['id']}", type="primary", use_container_width=True):
                db.upsert_resultado_final(jogo_f["id"], ng1, ng2)
                # Tenta gerar a fase final após as semis
                db.gerar_fase_final(final_id, jogo_f["serie"])
                st.rerun()
        else:
            icon1 = "🏆 " if vencedor == 1 else ""
            icon2 = "🏆 " if vencedor == 2 else ""
            ca, cb = st.columns([5, 2])
            with ca:
                st.write(f"🔵 {icon1}{d1}")
                st.markdown("<div style='text-align:center;font-weight:bold'>×</div>", unsafe_allow_html=True)
                st.write(f"🔴 {icon2}{d2}")
            with cb:
                if g1 is not None:
                    st.metric("", f"{g1} × {g2}")


pode_editar = auth.is_admin() or auth.is_organizer()

for serie_nome, serie_key, emoji in [("Ouro", "ouro", "🥇"), ("Prata", "prata", "🥈")]:
    st.divider()
    st.subheader(f"{emoji} Série {serie_nome}")

    sf1 = jogos_por(serie_key, "semi1")
    sf2 = jogos_por(serie_key, "semi2")
    final_j = jogos_por(serie_key, "final")

    col1, col2, col3 = st.columns(3)
    with col1:
        _render_jogo_final(sf1, "Semifinal 1", pode_editar)
    with col2:
        _render_jogo_final(sf2, "Semifinal 2", pode_editar)
    with col3:
        _render_jogo_final(final_j, "🏆 FINAL", pode_editar)

# ── Resetar final (admin) ─────────────────────────────────────────────────────
if auth.is_admin():
    st.divider()
    with st.expander("⚙️ Administração da Final"):
        st.warning("Excluir o chaveamento apaga todos os resultados da final.")
        if st.button("🗑️ Excluir chaveamento e recomeçar", type="primary"):
            db.delete_final(final_id)
            st.success("Chaveamento excluído.")
            st.rerun()
