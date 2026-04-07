"""
Liga Quarta Scaff — Sistema de Gerenciamento de Liga de Beach Tennis
Entry point principal: tela de login e configuração inicial.
"""

import streamlit as st
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent))

from src import database as db
from src import auth
from src.utils import fmt_data

_logado = bool(st.session_state.get("logged_in"))

st.set_page_config(
    page_title="Liga Quarta Scaff",
    page_icon="🎾",
    layout="wide",
    initial_sidebar_state="expanded" if _logado else "collapsed",
)

# ── Inicializa banco na primeira execução ──────────────────────────────────────
db.init_db()

# ── CSS customizado ────────────────────────────────────────────────────────────
_css_base = """
<style>
    [data-testid="stSidebarContent"] { background: #1a1a2e; }
    [data-testid="stSidebarContent"] * { color: #e0e0e0 !important; }
    .liga-header { text-align: center; padding: 2rem 0 1rem; }
    .liga-header h1 { color: #f5a623; font-size: 2.5rem; }
    .liga-header p { color: #888; font-size: 1rem; }
    .login-box { max-width: 400px; margin: 0 auto; padding: 2rem;
                 background: #f8f9fa; border-radius: 12px; }
</style>
"""

_css_sem_login = """
<style>
    /* Esconde sidebar e navegação antes do login */
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarNav"] { display: none !important; }
    header [data-testid="stToolbar"] { display: none !important; }
</style>
"""

st.markdown(_css_base, unsafe_allow_html=True)
if not _logado:
    st.markdown(_css_sem_login, unsafe_allow_html=True)

# ── Sidebar com info do usuário logado ─────────────────────────────────────────
auth.render_sidebar_user()

# ── Se não logado: mostra tela de login ───────────────────────────────────────
if not auth.esta_logado():

    # Cria admin padrão se não existir nenhum usuário
    if not db.has_any_user():
        from src.auth import hash_senha
        db.create_user("admin", hash_senha("admin123"), role="admin")

    st.markdown("""
    <div class="liga-header">
        <h1>🎾 Liga Quarta Scaff</h1>
        <p>Sistema de Gerenciamento de Liga de Beach Tennis</p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        with st.container(border=True):
            st.subheader("Entrar")
            username = st.text_input("Usuário", key="login_user")
            senha = st.text_input("Senha", type="password", key="login_pass")

            if st.button("Entrar", use_container_width=True, type="primary"):
                if auth.fazer_login(username, senha):
                    st.success("Login realizado!")
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")


    st.stop()

# ── Usuário logado: mostra dashboard principal ─────────────────────────────────
st.markdown("""
<div class="liga-header">
    <h1>🎾 Liga Quarta Scaff</h1>
    <p>Sistema de Gerenciamento de Liga de Beach Tennis</p>
</div>
""", unsafe_allow_html=True)

temporada = db.get_temporada_ativa()

if temporada:
    rodadas = db.list_rodadas(temporada["id"])
    rodadas_concluidas = [r for r in rodadas if r["status"] == "concluida"]
    jogadores = db.list_jogadores_temporada(temporada["id"])
    proxima = next((r for r in rodadas if r["status"] != "concluida"), None)

    row1_col1, row1_col2 = st.columns(2)
    row2_col1, row2_col2 = st.columns(2)

    with row1_col1:
        with st.container(border=True):
            st.metric("Temporada Ativa", temporada["nome"])

    with row1_col2:
        with st.container(border=True):
            proxima_label = f"#{proxima['numero']} — {fmt_data(proxima['data'])}" if proxima else "—"
            st.metric("Próxima Rodada", proxima_label)

    with row2_col1:
        with st.container(border=True):
            st.metric("Rodadas Concluídas", f"{len(rodadas_concluidas)} / {temporada['n_rodadas']}")

    with row2_col2:
        with st.container(border=True):
            st.metric("Jogadores na Temporada", len(jogadores))

    st.divider()
    st.subheader("Últimas Rodadas")

    if rodadas_concluidas:
        for rodada in reversed(rodadas_concluidas[-3:]):
            pontuacoes = db.get_pontuacao_rodada(rodada["id"])
            lider = pontuacoes[0] if pontuacoes else None
            with st.expander(f"Rodada {rodada['numero']} — {fmt_data(rodada['data'])}"):
                if lider:
                    st.success(f"🏆 Líder da rodada: **{lider['nome']}** com **{lider['pontos']} pts**")
                beers = [p["nome"] for p in pontuacoes if p["tem_beer"]]
                if beers:
                    st.warning(f"🍺 Devem cerveja: {', '.join(beers)}")
    else:
        st.info("Nenhuma rodada concluída ainda.")

else:
    st.warning("Nenhuma temporada ativa. Acesse **Jogadores** para criar uma temporada.")

# ── Navegação rápida ───────────────────────────────────────────────────────────
st.divider()
st.subheader("Navegação Rápida")
c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.page_link("pages/1_Jogadores.py", label="👤 Jogadores", use_container_width=True)
with c2:
    st.page_link("pages/2_Sorteio.py", label="🎲 Sorteio", use_container_width=True)
with c3:
    st.page_link("pages/3_Resultados.py", label="📋 Resultados", use_container_width=True)
with c4:
    st.page_link("pages/4_Ranking.py", label="🏆 Ranking", use_container_width=True)
with c5:
    st.page_link("pages/5_Historico.py", label="📊 Histórico", use_container_width=True)
