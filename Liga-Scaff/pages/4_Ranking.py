"""
Página de ranking da Liga Quarta Scaff.
Exibe ranking completo com variação de posição, rodadas descartadas e beer list.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth
from src.utils import fmt_data
from src.ranking import calcular_ranking, formatar_variacao

st.set_page_config(page_title="Ranking — Liga Scaff", page_icon="🏆", layout="wide")
auth.render_sidebar_user()
auth.require_login()

st.title("🏆 Ranking")

# ── Seleção de temporada ──────────────────────────────────────────────────────
temporadas = db.list_temporadas()
if not temporadas:
    st.warning("Crie uma temporada em **Jogadores** primeiro.")
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
    st.info("Nenhuma rodada concluída nesta temporada. Lance os resultados em **Resultados**.")
    st.stop()

# ── Cálculo do ranking ────────────────────────────────────────────────────────
with st.spinner("Calculando ranking..."):
    ranking = calcular_ranking(tid)

if not ranking:
    st.info("Sem dados de ranking.")
    st.stop()

rodadas_numeros = sorted([r["numero"] for r in rodadas_concluidas])
ultima_rodada = rodadas_concluidas[-1]

# ── Cabeçalho ─────────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)
with col1:
    with st.container(border=True):
        st.metric("Rodadas Concluídas", f"{len(rodadas_concluidas)} / {temporada['n_rodadas']}")
with col2:
    with st.container(border=True):
        lider = ranking[0] if ranking else None
        st.metric("Líder Geral", lider["nome"] if lider else "—", f"{lider['total']} pts" if lider else "")
with col3:
    with st.container(border=True):
        st.metric("Jogadores", len(ranking))

# ── Séries Ouro e Prata ───────────────────────────────────────────────────────
st.divider()
ouro = [r for r in ranking if r["posicao"] <= 8]
prata = [r for r in ranking if 9 <= r["posicao"] <= 16]

col_o, col_p = st.columns(2)
with col_o:
    with st.container(border=True):
        st.markdown("### 🥇 Série Ouro — Top 8")
        if ouro:
            st.metric("Líder", ouro[0]["nome"], f"{ouro[0]['total']} pts")
            nomes_ouro = " · ".join(f"{r['posicao']}º {r['nome']}" for r in ouro)
            st.caption(nomes_ouro)
        else:
            st.caption("Sem dados ainda.")
with col_p:
    with st.container(border=True):
        st.markdown("### 🥈 Série Prata — 9º ao 16º")
        if prata:
            st.metric("Líder", prata[0]["nome"], f"{prata[0]['total']} pts")
            nomes_prata = " · ".join(f"{r['posicao']}º {r['nome']}" for r in prata)
            st.caption(nomes_prata)
        else:
            st.caption("Sem dados ainda.")

# ── Tabela completa ───────────────────────────────────────────────────────────
st.divider()
st.subheader("Classificação Completa")
st.caption(
    f"Temporada {temporada['nome']} · "
    f"Descartando {temporada['n_descartadas']} piores rodadas por jogador"
)

# Monta dados para a tabela
import pandas as pd


def cor_variacao(v) -> str:
    var = formatar_variacao(v)
    if v is None or v == 0:
        return var
    if v > 0:
        return f"🟢 {var}"
    return f"🔴 {var}"


linhas = []
for entry in ranking:
    pos = entry["posicao"]
    serie = "🥇 Ouro" if pos <= 8 else ("🥈 Prata" if pos <= 16 else "")
    linha = {
        "Série": serie,
        "Pos": pos,
        "▲▼": cor_variacao(entry["variacao"]),
        "Jogador": entry["nome"],
    }
    for rn in rodadas_numeros:
        pts = entry["pontos_por_rodada"].get(rn)
        if pts is None:
            linha[f"R{rn}"] = "—"
        elif rn in entry["rodadas_descartadas"]:
            linha[f"R{rn}"] = f"({pts})"  # descartada
        else:
            linha[f"R{rn}"] = str(pts)
    linha["Total"] = entry["total"]
    linhas.append(linha)

df = pd.DataFrame(linhas)

# Estilização: destaca top 3, mostra descartadas em cinza
def highlight_row(row):
    pos = row["Pos"]
    if pos <= 8:
        return ["background-color: #3a2e00; color: #ffd700"] * len(row)
    if pos <= 16:
        return ["background-color: #1a1e2a; color: #b0b8c8"] * len(row)
    return [""] * len(row)


styled = df.style.apply(highlight_row, axis=1)
st.dataframe(styled, use_container_width=True, hide_index=True)

st.caption("Valores entre parênteses = rodadas descartadas do ranking.")

# ── Detalhes por rodada ───────────────────────────────────────────────────────
st.divider()
with st.expander("📊 Pontuação por Rodada (detalhado)"):
    for r in rodadas_concluidas:
        pontuacoes = db.get_pontuacao_rodada(r["id"])
        beer_r = [p["nome"] for p in pontuacoes if p["tem_beer"]]
        with st.container(border=True):
            st.write(f"**Rodada {r['numero']} — {fmt_data(r['data'])}**")
            dados_r = [
                {
                    "Pos": i + 1,
                    "Jogador": p["nome"],
                    "Pontos": p["pontos"],
                    "Ganhos": p["jogos_ganhos"],
                    "Perdidos": p["jogos_perdidos"],
                    "🍺": "Sim" if p["tem_beer"] else "—",
                }
                for i, p in enumerate(pontuacoes)
            ]
            st.dataframe(pd.DataFrame(dados_r), use_container_width=True, hide_index=True)
            if beer_r:
                st.caption(f"🍺 Cerveja: {', '.join(beer_r)}")

# ── Gerenciamento de usuários (apenas admin) ──────────────────────────────────
if auth.is_admin():
    st.divider()
    with st.expander("⚙️ Gerenciar Usuários do Sistema"):
        usuarios = db.list_users()
        for u in usuarios:
            with st.container(border=True):
                c1, c2, c3 = st.columns([3, 2, 1])
                with c1:
                    st.write(f"**{u['username']}**")
                    st.caption(auth.ROLE_LABELS.get(u["role"], u["role"]))
                with c2:
                    novo_role = st.selectbox(
                        "Role",
                        options=auth.ROLES,
                        index=auth.ROLES.index(u["role"]) if u["role"] in auth.ROLES else 0,
                        key=f"role_{u['id']}",
                        label_visibility="collapsed",
                    )
                with c3:
                    if st.button("Salvar role", key=f"upd_{u['id']}", use_container_width=True):
                        db.update_user_role(u["id"], novo_role)
                        st.success("Role atualizado!")
                        st.rerun()

                with st.form(key=f"form_senha_{u['id']}", clear_on_submit=True):
                    sa, sb, sc = st.columns([3, 3, 1])
                    with sa:
                        nova = st.text_input("Nova senha", type="password",
                                             placeholder="Nova senha", label_visibility="collapsed")
                    with sb:
                        conf = st.text_input("Confirmar senha", type="password",
                                             placeholder="Confirmar senha", label_visibility="collapsed")
                    with sc:
                        if st.form_submit_button("🔑 Alterar", use_container_width=True):
                            if not nova.strip():
                                st.error("Digite a nova senha.")
                            elif nova != conf:
                                st.error("As senhas não coincidem.")
                            else:
                                db.update_user_password(u["id"], auth.hash_senha(nova))
                                st.success("Senha alterada!")

        st.divider()
        st.write("**Criar novo usuário**")
        with st.form("form_new_user", clear_on_submit=True):
            nu = st.text_input("Usuário")
            np = st.text_input("Senha", type="password")
            nc = st.text_input("Confirmar senha", type="password")
            nr = st.selectbox("Role", options=auth.ROLES)
            if st.form_submit_button("Criar", use_container_width=True):
                if not nu.strip() or not np.strip():
                    st.error("Usuário e senha são obrigatórios.")
                elif np != nc:
                    st.error("As senhas não coincidem.")
                else:
                    db.create_user(nu.strip(), auth.hash_senha(np), nr)
                    st.success(f"Usuário '{nu}' criado!")
                    st.rerun()
