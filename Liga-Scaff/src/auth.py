"""
Módulo de autenticação da Liga Quarta Scaff.
Login com bcrypt, controle de roles, sessão Streamlit.
"""

import bcrypt
import hmac
import hashlib
import secrets
import time
import streamlit as st
import streamlit.components.v1 as components

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

_LOGO_PATH = Path(__file__).parent.parent / "Logo_Liga_Scaff.jpeg"

from src import database as db

_COOKIE_NAME = "liga_scaff_auth"
_TOKEN_TTL_HOURS = 12


def _get_secret_key() -> str:
    key = db.get_setting("secret_key")
    if not key:
        key = secrets.token_hex(32)
        db.set_setting("secret_key", key)
    return key


def make_auth_token(username: str, role: str) -> str:
    expiry = int(time.time()) + _TOKEN_TTL_HOURS * 3600
    payload = f"{username}|{role}|{expiry}"
    sig = hmac.new(_get_secret_key().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def validate_auth_token(token: str) -> dict | None:
    try:
        parts = token.split("|")
        if len(parts) != 4:
            return None
        username, role, expiry_str, sig = parts
        if time.time() > int(expiry_str):
            return None
        payload = f"{username}|{role}|{expiry_str}"
        expected = hmac.new(_get_secret_key().encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        # Confirm user still exists and role matches
        user = db.get_user(username)
        if not user or user["role"] != role:
            return None
        return {"username": username, "role": role}
    except Exception:
        return None

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


def fazer_logout(cookie_controller=None) -> None:
    if cookie_controller is not None:
        try:
            cookie_controller.remove(_COOKIE_NAME)
        except Exception:
            pass
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


_ACESSO_INFO = {
    "admin": {
        "label": "🔑 Administrador",
        "itens": [
            "✅ Acesso total ao sistema",
            "✅ Jogadores, temporadas e usuários",
            "✅ Sorteio completo + entrada manual",
            "✅ Resultados (editar jogos e nomes)",
            "✅ Ranking, histórico e final",
        ],
    },
    "organizer": {
        "label": "📋 Operador",
        "itens": [
            "✅ Gerar sorteio e auditoria",
            "✅ Lançar resultados (placar)",
            "✅ Enviar PDFs por e-mail",
            "✅ Ranking, histórico",
            "❌ Criar rodadas ou editar jogadores",
            "❌ Gerenciar usuários",
        ],
    },
    "viewer": {
        "label": "👁️ Visualizador",
        "itens": [
            "✅ Ver ranking",
            "✅ Ver histórico",
            "❌ Sorteio, resultados ou qualquer edição",
        ],
    },
}


def _render_acesso_info() -> None:
    role = get_role()
    info = _ACESSO_INFO.get(role)
    if not info:
        return
    with st.expander(info["label"], expanded=False):
        for item in info["itens"]:
            st.caption(item)


def render_sidebar_user(cookie_controller=None) -> None:
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
        if _LOGO_PATH.exists():
            st.image(str(_LOGO_PATH), width=140)
        if esta_logado():
            st.markdown(f"**{st.session_state['username']}**")
            st.caption(ROLE_LABELS.get(get_role(), get_role()))
            _render_acesso_info()
            st.divider()
            if st.button("Sair", use_container_width=True):
                fazer_logout(cookie_controller)
                st.rerun()
