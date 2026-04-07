"""
Página de gestão de jogadores da Liga Quarta Scaff.
CRUD de jogadores, temporadas e importação via lista WhatsApp.
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth
from src.utils import parse_lista_whatsapp

st.set_page_config(page_title="Jogadores — Liga Scaff", page_icon="👤", layout="wide")
auth.render_sidebar_user()
auth.require_login()

st.title("👤 Jogadores")

tab_jogadores, tab_temporadas, tab_participantes = st.tabs(
    ["Jogadores Cadastrados", "Temporadas", "Participantes da Temporada"]
)

# ── ABA 1: Jogadores Cadastrados ──────────────────────────────────────────────
with tab_jogadores:
    col_lista, col_form = st.columns([2, 1])

    with col_lista:
        st.subheader("Lista de Jogadores")
        mostrar_inativos = st.checkbox("Mostrar inativos também")
        jogadores = db.list_jogadores(apenas_ativos=not mostrar_inativos)

        if jogadores:
            for j in jogadores:
                with st.container(border=True):
                    c1, c2, c3, c4, c5 = st.columns([3, 3, 2, 1, 1])
                    with c1:
                        st.write(f"**{j['nome']}**" + ("" if j["ativo"] else " _(inativo)_"))
                    with c2:
                        st.caption(j["email"] or "—")
                    with c3:
                        st.caption(j["whatsapp"] or "—")
                    with c4:
                        if auth.is_admin():
                            if j["ativo"]:
                                if st.button("✏️", key=f"edit_{j['id']}", help="Editar"):
                                    st.session_state["editando_jogador"] = dict(j)
                                    st.rerun()
                            else:
                                if st.button("✅", key=f"reativar_{j['id']}", help="Reativar"):
                                    db.toggle_jogador_ativo(j["id"], True)
                                    st.rerun()
                    with c5:
                        if auth.is_admin():
                            if st.button("🗑️", key=f"del_{j['id']}", help="Excluir jogador"):
                                st.session_state["confirmar_excluir"] = j["id"]
                                st.rerun()

            # Confirmação de exclusão fora do loop
            confirmar_id = st.session_state.get("confirmar_excluir")
            if confirmar_id and auth.is_admin():
                j_conf = db.get_jogador(confirmar_id)
                if j_conf:
                    st.warning(f"⚠️ Excluir **{j_conf['nome']}** permanentemente?")
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.button("Sim, excluir", type="primary", use_container_width=True):
                            db.delete_jogador(confirmar_id)
                            st.session_state.pop("confirmar_excluir", None)
                            st.success("Jogador excluído.")
                            st.rerun()
                    with c2:
                        if st.button("Cancelar", use_container_width=True):
                            st.session_state.pop("confirmar_excluir", None)
                            st.rerun()
        else:
            st.info("Nenhum jogador cadastrado.")

    with col_form:
        # Formulário de edição
        editando = st.session_state.get("editando_jogador")
        if editando and auth.is_admin():
            st.subheader(f"Editar: {editando['nome']}")
            with st.form("form_editar_jogador"):
                nome = st.text_input("Nome", value=editando["nome"])
                email = st.text_input("E-mail", value=editando["email"] or "")
                whatsapp = st.text_input("WhatsApp", value=editando["whatsapp"] or "")
                c1, c2 = st.columns(2)
                with c1:
                    salvar = st.form_submit_button("Salvar", use_container_width=True, type="primary")
                with c2:
                    desativar = st.form_submit_button("Desativar", use_container_width=True)

            if salvar and nome.strip():
                db.update_jogador(editando["id"], nome.strip(), email.strip(), whatsapp.strip())
                st.session_state.pop("editando_jogador", None)
                st.success("Jogador atualizado!")
                st.rerun()
            if desativar:
                db.toggle_jogador_ativo(editando["id"], False)
                st.session_state.pop("editando_jogador", None)
                st.warning("Jogador desativado.")
                st.rerun()

            if st.button("Cancelar", use_container_width=True):
                st.session_state.pop("editando_jogador", None)
                st.rerun()

        elif auth.is_admin():
            st.subheader("Novo Jogador")
            with st.form("form_novo_jogador", clear_on_submit=True):
                nome = st.text_input("Nome *")
                email = st.text_input("E-mail")
                whatsapp = st.text_input("WhatsApp")
                if st.form_submit_button("Cadastrar", use_container_width=True, type="primary"):
                    if nome.strip():
                        db.create_jogador(nome.strip(), email.strip(), whatsapp.strip())
                        st.success(f"Jogador **{nome.strip()}** cadastrado!")
                        st.rerun()
                    else:
                        st.error("Nome é obrigatório.")

        st.divider()

        # Import via lista WhatsApp
        if auth.is_admin():
            st.subheader("📱 Import via WhatsApp")
            st.caption(
                "Cole a lista do WhatsApp. Suporta formatos: `1 - Nome`, `- Nome`, `• Nome` ou só `Nome`."
            )
            lista_texto = st.text_area(
                "Lista do WhatsApp",
                height=150,
                placeholder="1 - João Silva\n2 - Pedro Santos\n- Marcos Oliveira\n...",
                key="wpp_import",
            )
            if st.button("Detectar Nomes", use_container_width=True):
                if lista_texto.strip():
                    todos = db.list_jogadores(apenas_ativos=False)
                    encontrados, nao_encontrados = parse_lista_whatsapp(lista_texto, todos)
                    st.session_state["nomes_wpp_encontrados"] = [j["nome"] for j in encontrados]
                    st.session_state["nomes_wpp_novos"] = nao_encontrados
                    st.rerun()

            encontrados_wpp = st.session_state.get("nomes_wpp_encontrados", [])
            novos_wpp = st.session_state.get("nomes_wpp_novos", [])

            if encontrados_wpp or novos_wpp:
                if encontrados_wpp:
                    st.success(f"Já cadastrados ({len(encontrados_wpp)}): {', '.join(encontrados_wpp)}")
                if novos_wpp:
                    st.warning(f"Novos — serão cadastrados ({len(novos_wpp)}): {', '.join(novos_wpp)}")
                    if st.button(f"Cadastrar {len(novos_wpp)} novo(s)", type="primary"):
                        for nome in novos_wpp:
                            db.create_jogador(nome)
                        st.session_state.pop("nomes_wpp_encontrados", None)
                        st.session_state.pop("nomes_wpp_novos", None)
                        st.success(f"{len(novos_wpp)} jogadores cadastrados!")
                        st.rerun()
                else:
                    st.info("Todos os nomes já estão cadastrados.")
                if st.button("Limpar"):
                    st.session_state.pop("nomes_wpp_encontrados", None)
                    st.session_state.pop("nomes_wpp_novos", None)
                    st.rerun()


# ── ABA 2: Temporadas ─────────────────────────────────────────────────────────
with tab_temporadas:
    col_lista, col_form = st.columns([2, 1])

    with col_lista:
        st.subheader("Temporadas")
        temporadas = db.list_temporadas()

        if temporadas:
            for t in temporadas:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([3, 2, 1])
                    with c1:
                        badge = "🟢 Ativa" if t["ativa"] else "⚫ Inativa"
                        st.write(f"**{t['nome']}** {badge}")
                        st.caption(f"{t['n_rodadas']} rodadas · descarta {t['n_descartadas']} piores")
                    with c2:
                        rodadas = db.list_rodadas(t["id"])
                        concluidas = len([r for r in rodadas if r["status"] == "concluida"])
                        st.metric("Rodadas", f"{concluidas}/{len(rodadas)}")
                    with c3:
                        if auth.is_admin():
                            if not t["ativa"]:
                                if st.button("Ativar", key=f"ativar_temp_{t['id']}"):
                                    db.set_temporada_ativa(t["id"])
                                    st.rerun()
                            if st.button("🗑️", key=f"del_temp_{t['id']}", help="Excluir temporada"):
                                st.session_state["confirmar_del_temp"] = t["id"]
                                st.rerun()

            conf_tid = st.session_state.get("confirmar_del_temp")
            if conf_tid and auth.is_admin():
                t_conf = db.get_temporada(conf_tid)
                if t_conf:
                    st.warning(
                        f"⚠️ Excluir **{t_conf['nome']}** e TODOS os dados (rodadas, sorteios, resultados, ranking)? "
                        "Esta ação não pode ser desfeita."
                    )
                    ca, cb = st.columns(2)
                    with ca:
                        if st.button("Sim, excluir tudo", type="primary", use_container_width=True):
                            db.delete_temporada(conf_tid)
                            st.session_state.pop("confirmar_del_temp", None)
                            st.success("Temporada excluída.")
                            st.rerun()
                    with cb:
                        if st.button("Cancelar", use_container_width=True, key="cancel_del_temp"):
                            st.session_state.pop("confirmar_del_temp", None)
                            st.rerun()
        else:
            st.info("Nenhuma temporada cadastrada.")

    with col_form:
        if auth.is_admin():
            st.subheader("Nova Temporada")
            with st.form("form_nova_temporada", clear_on_submit=True):
                nome = st.text_input("Nome", placeholder="Liga Quarta Scaff 2025")
                ano = st.number_input("Ano", min_value=2020, max_value=2035, value=2025)
                n_rodadas = st.number_input("Nº de Rodadas", min_value=1, max_value=20, value=8)
                n_descartadas = st.number_input(
                    "Piores rodadas descartadas", min_value=0, max_value=5, value=2
                )
                if st.form_submit_button("Criar Temporada", use_container_width=True, type="primary"):
                    if nome.strip():
                        tid = db.create_temporada(nome.strip(), int(ano), int(n_rodadas), int(n_descartadas))
                        if not db.get_temporada_ativa():
                            db.set_temporada_ativa(tid)
                        st.success(f"Temporada **{nome.strip()}** criada!")
                        st.rerun()
                    else:
                        st.error("Nome é obrigatório.")


# ── ABA 3: Participantes da Temporada ─────────────────────────────────────────
with tab_participantes:
    temporadas = db.list_temporadas()
    if not temporadas:
        st.info("Crie uma temporada primeiro.")
        st.stop()

    temporada_selecionada = st.selectbox(
        "Temporada",
        options=temporadas,
        format_func=lambda t: t["nome"],
        key="temp_participantes",
    )

    if temporada_selecionada:
        tid = temporada_selecionada["id"]
        todos_jogadores = db.list_jogadores(apenas_ativos=True)
        participantes_ids = {j["id"] for j in db.list_jogadores_temporada(tid)}

        st.subheader(f"Participantes — {temporada_selecionada['nome']}")
        st.caption(f"Selecione quem participa desta temporada.")

        if not todos_jogadores:
            st.warning("Cadastre jogadores primeiro.")
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.write("**Participando**")
                participantes = [j for j in todos_jogadores if j["id"] in participantes_ids]
                for j in participantes:
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.write(j["nome"])
                    with c2:
                        if auth.is_admin():
                            if st.button("➖", key=f"rem_{tid}_{j['id']}", help="Remover"):
                                db.remove_jogador_temporada(j["id"], tid)
                                st.rerun()

            with col2:
                st.write("**Disponíveis**")
                disponiveis = [j for j in todos_jogadores if j["id"] not in participantes_ids]
                for j in disponiveis:
                    c1, c2 = st.columns([4, 1])
                    with c1:
                        st.write(j["nome"])
                    with c2:
                        if auth.is_admin():
                            if st.button("➕", key=f"add_{tid}_{j['id']}", help="Adicionar"):
                                db.add_jogador_temporada(j["id"], tid)
                                st.rerun()

            st.divider()
            if auth.is_admin() and disponiveis:
                if st.button("Adicionar Todos à Temporada", type="primary"):
                    for j in disponiveis:
                        db.add_jogador_temporada(j["id"], tid)
                    st.success("Todos os jogadores adicionados!")
                    st.rerun()
