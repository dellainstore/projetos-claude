"""
Módulo de autenticação da Liga Quarta Scaff.
Login com bcrypt, controle de roles, sessão Streamlit.
"""

import bcrypt
import streamlit as st
import streamlit.components.v1 as components

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db

ROLES = ["admin", "organizer", "viewer"]
ROLE_LABELS = {"admin": "Administrador", "organizer": "Organizador", "viewer": "Visualizador"}


def hash_senha(senha: str) -> str:
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    return bcrypt.checkpw(senha.encode(), hash_armazenado.encode())


def fazer_login(username: str, senha: str) -> bool:
    user = db.get_user(username)
    if user and verificar_senha(senha, user["password_hash"] if isinstance(user, dict) else user["password_hash"]):
        st.session_state["logged_in"] = True
        st.session_state["username"] = user["username"]
        st.session_state["role"] = user["role"]
        return True
    return False


def fazer_logout() -> None:
    for key in ["logged_in", "username", "role"]:
        st.session_state.pop(key, None)


def esta_logado() -> bool:
    return st.session_state.get("logged_in", False)


def get_role() -> str:
    return st.session_state.get("role", "viewer")


def is_admin() -> bool:
    return get_role() == "admin"


def is_organizer() -> bool:
    return get_role() in ("admin", "organizer")


def require_login() -> None:
    """Para em páginas que exigem login. Redireciona se não logado."""
    if not esta_logado():
        st.warning("Você precisa estar logado para acessar esta página.")
        st.stop()


def require_organizer() -> None:
    require_login()
    if not is_organizer():
        st.error("Acesso restrito a organizadores e administradores.")
        st.stop()


def require_admin() -> None:
    require_login()
    if not is_admin():
        st.error("Acesso restrito a administradores.")
        st.stop()


def render_sidebar_user() -> None:
    # Renomeia o item "app" para "Inicial" no menu lateral via JS (aplicado em todas as páginas)
    components.html("""
    <script>
    function renameApp() {
        const doc = window.parent.document;
        const spans = doc.querySelectorAll('[data-testid="stSidebarNav"] a span');
        spans.forEach(span => {
            if (span.textContent.trim() === 'app') {
                span.textContent = 'Inicial';
            }
        });
    }
    setTimeout(renameApp, 100);
    setTimeout(renameApp, 500);
    setTimeout(renameApp, 1500);
    </script>
    """, height=0)

    with st.sidebar:
        if esta_logado():
            st.markdown(f"**{st.session_state['username']}**")
            st.caption(ROLE_LABELS.get(get_role(), get_role()))
            if st.button("Sair", use_container_width=True):
                fazer_logout()
                st.rerun()
