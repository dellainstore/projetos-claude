"""
Liga Quarta Scaff — Entry point principal.
Gerencia login, navegação condicional por papel e dashboard inicial.
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
    [data-testid="stSidebar"] { display: none !important; }
    [data-testid="stSidebarNav"] { display: none !important; }
    header [data-testid="stToolbar"] { display: none !important; }
</style>
"""

st.markdown(_css_base, unsafe_allow_html=True)
if not _logado:
    st.markdown(_css_sem_login, unsafe_allow_html=True)


# ── Tela de login ─────────────────────────────────────────────────────────────
def _pagina_login():
    if not db.has_any_user():
        from src.auth import hash_senha
        db.create_user("admin", hash_senha("admin123"), role="admin")

    col1, col2, col3 = st.columns([1, 1.2, 1])
    with col2:
        st.markdown("""
        <div class="liga-header">
            <h1>🎾 Liga Quarta Scaff</h1>
            <p>Sistema de Gerenciamento de Liga de Beach Tennis</p>
        </div>
        """, unsafe_allow_html=True)
        with st.container(border=True):
            st.subheader("Entrar")
            username = st.text_input("Usuário", key="login_user")
            senha = st.text_input("Senha", type="password", key="login_pass")

            tentativas = st.session_state.get("login_tentativas", 0)
            bloqueado = tentativas >= 5

            if bloqueado:
                st.error("Muitas tentativas incorretas. Atualize a página para tentar novamente.")
            elif st.button("Entrar", use_container_width=True, type="primary"):
                if auth.fazer_login(username, senha):
                    st.session_state["login_tentativas"] = 0
                    st.success("Login realizado!")
                    st.rerun()
                else:
                    st.session_state["login_tentativas"] = tentativas + 1
                    restantes = max(0, 5 - st.session_state["login_tentativas"])
                    if restantes > 0:
                        st.error(f"Usuário ou senha incorretos. {restantes} tentativa(s) restante(s).")
                    else:
                        st.error("Muitas tentativas incorretas. Atualize a página para tentar novamente.")


# ── Dashboard principal ────────────────────────────────────────────────────────
def _dashboard():
    role = auth.get_role()

    st.markdown("""
<div class="liga-header">
    <h1>🎾 Liga Quarta Scaff</h1>
    <p>Sistema de Gerenciamento de Liga de Beach Tennis</p>
</div>
""", unsafe_allow_html=True)

    # Aviso de segurança: lembra o admin de trocar a senha padrão
    if role == "admin" and st.session_state.get("username") == "admin":
        st.warning(
            "**Aviso de segurança:** Você está usando a conta `admin` padrão. "
            "Altere a senha imediatamente em **Ranking → Gerenciar Usuários**.",
            icon="⚠️",
        )

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

    # Navegação rápida — apenas para páginas que o papel tem acesso
    st.divider()
    st.subheader("Navegação Rápida")

    links = []
    if role == "admin":
        links = [
            ("pages/1_Jogadores.py", "👤 Jogadores"),
            ("pages/2_Sorteio.py", "🎲 Sorteio"),
            ("pages/3_Resultados.py", "📋 Resultados"),
            ("pages/4_Ranking.py", "🏆 Ranking"),
            ("pages/5_Historico.py", "📊 Histórico"),
        ]
    elif role == "organizer":
        links = [
            ("pages/2_Sorteio.py", "🎲 Sorteio"),
            ("pages/3_Resultados.py", "📋 Resultados"),
            ("pages/4_Ranking.py", "🏆 Ranking"),
            ("pages/5_Historico.py", "📊 Histórico"),
        ]
    else:  # viewer
        links = [
            ("pages/4_Ranking.py", "🏆 Ranking"),
            ("pages/5_Historico.py", "📊 Histórico"),
        ]

    cols = st.columns(len(links))
    for col, (page, label) in zip(cols, links):
        with col:
            st.page_link(page, label=label, use_container_width=True)


# ── Navegação condicional por papel ───────────────────────────────────────────
if not _logado:
    pg = st.navigation([st.Page(_pagina_login, title="Login", url_path="login")])
else:
    auth.render_sidebar_user()
    role = auth.get_role()

    pg_inicial = st.Page(_dashboard, title="Inicial", icon="🏠", default=True)
    pg_jogadores = st.Page("pages/1_Jogadores.py", title="Jogadores", icon="👤")
    pg_sorteio = st.Page("pages/2_Sorteio.py", title="Sorteio", icon="🎲")
    pg_resultados = st.Page("pages/3_Resultados.py", title="Resultados", icon="📋")
    pg_ranking = st.Page("pages/4_Ranking.py", title="Ranking", icon="🏆")
    pg_historico = st.Page("pages/5_Historico.py", title="Histórico", icon="📊")
    pg_final = st.Page("pages/6_Final.py", title="Final", icon="🏆")

    if role == "admin":
        pages = [pg_inicial, pg_jogadores, pg_sorteio, pg_resultados, pg_ranking, pg_historico, pg_final]
    elif role == "organizer":
        pages = [pg_inicial, pg_sorteio, pg_resultados, pg_ranking, pg_historico]
    else:  # viewer
        pages = [pg_inicial, pg_ranking, pg_historico]

    pg = st.navigation(pages)

pg.run()
