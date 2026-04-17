"""
Página de sorteio da Liga Quarta Scaff.
Cria rodadas, gera sorteios, entrada manual combinada (jogadores + resultados) e auditoria.
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth
from src.draw_engine import gerar_sorteio, sorteio_para_tabela, validar_sorteio
from src.pdf_generator import gerar_planilha_pdf
from src.scoring import calcular_pontuacao_rodada, get_beer_list, validar_placar
from src.utils import parse_lista_whatsapp, validar_nome_jogador, fmt_data

auth.require_organizer()

st.title("🎲 Sorteio")

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


def nome_jogo(jogo: dict, slot: str, nomes_map: dict) -> str:
    jid = jogo.get(slot)
    if jid is not None:
        return nomes_map.get(jid, str(jid))
    v = jogo.get(f"{slot}_nome")
    return v if v else "?"


if auth.is_admin():
    tab_criar, tab_sorteio, tab_manual, tab_auditoria = st.tabs(
        ["Criar / Gerenciar Rodadas", "Gerar Sorteio", "Entrada Manual", "Auditoria"]
    )
else:
    tab_sorteio, tab_auditoria = st.tabs(["Gerar Sorteio", "Auditoria"])
    tab_criar = None
    tab_manual = None


# ── ABA 1: Criar / Gerenciar Rodadas ─────────────────────────────────────────
if tab_criar is not None:
    with tab_criar:
        rodadas = db.list_rodadas(tid)

        col_lista, col_form = st.columns([2, 1])

        with col_lista:
            st.subheader("Rodadas da Temporada")
            if rodadas:
                for r in rodadas:
                    status_icon = {"pendente": "⏳", "sorteio_feito": "🎲", "concluida": "✅"}.get(r["status"], "?")
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns([3, 2, 1, 1])
                        with c1:
                            st.write(f"{status_icon} **Rodada {r['numero']}** — {fmt_data(r['data'])}")
                            st.caption(f"{r['n_jogadores']} jogadores · {r['status']}")
                        with c2:
                            sorteio_ativo = db.get_sorteio_ativo(r["id"])
                            if sorteio_ativo:
                                n_sorteios = len(db.list_sorteios(r["id"]))
                                st.caption(f"Sorteio #{sorteio_ativo['numero']} oficial · {n_sorteios} gerado(s)")
                        with c3:
                            if auth.is_admin():
                                if st.button("✏️", key=f"edit_rodada_{r['id']}", help="Editar rodada"):
                                    st.session_state["editar_rodada"] = r["id"]
                                    st.session_state.pop("confirmar_del_rodada", None)
                                    st.rerun()
                        with c4:
                            if auth.is_admin():
                                if st.button("🗑️", key=f"del_rodada_{r['id']}", help="Excluir rodada"):
                                    st.session_state["confirmar_del_rodada"] = r["id"]
                                    st.session_state.pop("editar_rodada", None)
                                    st.rerun()

                # Modal de edição
                edit_id = st.session_state.get("editar_rodada")
                if edit_id and auth.is_admin():
                    r_edit = db.get_rodada(edit_id)
                    if r_edit:
                        st.info(f"✏️ Editando **Rodada {r_edit['numero']}**")
                        with st.form(key="form_edit_rodada"):
                            ea, eb, ec = st.columns(3)
                            with ea:
                                novo_num = st.number_input("Número", min_value=1, max_value=20, value=int(r_edit["numero"]))
                            with eb:
                                from datetime import datetime as _dt
                                data_atual = _dt.strptime(str(r_edit["data"]), "%Y-%m-%d").date()
                                nova_data = st.date_input("Data", value=data_atual)
                            with ec:
                                novo_n = st.selectbox(
                                    "Nº de Jogadores",
                                    options=[16, 20, 24, 28, 32],
                                    index=[16, 20, 24, 28, 32].index(int(r_edit["n_jogadores"])) if r_edit["n_jogadores"] in [16, 20, 24, 28, 32] else 0,
                                )
                            fa, fb = st.columns(2)
                            with fa:
                                salvar_edit = st.form_submit_button("💾 Salvar", use_container_width=True, type="primary")
                            with fb:
                                cancelar_edit = st.form_submit_button("✕ Cancelar", use_container_width=True)

                        if salvar_edit:
                            db.update_rodada(edit_id, int(novo_num), str(nova_data), int(novo_n))
                            st.session_state.pop("editar_rodada", None)
                            st.success("Rodada atualizada!")
                            st.rerun()
                        if cancelar_edit:
                            st.session_state.pop("editar_rodada", None)
                            st.rerun()

                # Confirmação de exclusão
                conf_id = st.session_state.get("confirmar_del_rodada")
                if conf_id and auth.is_admin():
                    r_conf = db.get_rodada(conf_id)
                    if r_conf:
                        st.warning(f"⚠️ Excluir **Rodada {r_conf['numero']} — {fmt_data(r_conf['data'])}** e todos os dados? Esta ação não pode ser desfeita.")
                        ca, cb = st.columns(2)
                        with ca:
                            if st.button("Sim, excluir rodada", type="primary", use_container_width=True):
                                db.delete_rodada(conf_id)
                                st.session_state.pop("confirmar_del_rodada", None)
                                st.success("Rodada excluída.")
                                st.rerun()
                        with cb:
                            if st.button("Cancelar", use_container_width=True):
                                st.session_state.pop("confirmar_del_rodada", None)
                                st.rerun()
            else:
                st.info("Nenhuma rodada criada ainda.")

        with col_form:
            st.subheader("Nova Rodada")
            with st.form("form_nova_rodada", clear_on_submit=True):
                proximo_num = max([r["numero"] for r in rodadas], default=0) + 1
                numero = st.number_input("Número", min_value=1, max_value=20, value=proximo_num)
                data_rodada = st.date_input("Data", value=date.today())
                n_jogadores = st.selectbox("Nº de Jogadores", options=[16, 20, 24, 28, 32])
                if st.form_submit_button("Criar Rodada", use_container_width=True, type="primary"):
                    db.create_rodada(tid, int(numero), str(data_rodada), int(n_jogadores))
                    st.success(f"Rodada {numero} criada!")
                    st.rerun()


# ── ABA 2: Gerar Sorteio ─────────────────────────────────────────────────────
with tab_sorteio:
    rodadas = db.list_rodadas(tid)
    rodadas_pendentes = [r for r in rodadas if r["status"] in ("pendente", "sorteio_feito")]

    if not rodadas_pendentes:
        st.info("Nenhuma rodada pendente de sorteio.")
        rodada_sel = None
    else:
        rodada_sel = st.selectbox(
            "Rodada para Sortear",
            options=rodadas_pendentes,
            format_func=lambda r: f"Rodada {r['numero']} — {fmt_data(r['data'])} ({r['n_jogadores']} jogadores)",
            key="sorteio_rodada",
        )

    if rodada_sel:
        rid = rodada_sel["id"]
        n_total = rodada_sel["n_jogadores"]
        todos_jogadores = db.list_jogadores(apenas_ativos=True)
        jogadores_temp = db.list_jogadores_temporada(tid)

        st.subheader("1. Cole a lista do WhatsApp para confirmar presentes")
        st.caption(
            "Formatos aceitos: `1 - Nome`, `- Nome`, `• Nome` ou só `Nome`. "
            "Apenas nomes que batem com jogadores cadastrados serão incluídos."
        )

        col_wpp, col_visitantes = st.columns([3, 1])

        with col_wpp:
            lista_wpp = st.text_area(
                "Lista do WhatsApp",
                height=180,
                placeholder="1 - João Silva\n2 - Pedro Santos\n- Marcos Oliveira\nLucas Pereira\n...",
                key=f"wpp_sorteio_{rid}",
            )

            jogadores_confirmados: list[dict] = []
            nao_encontrados: list[str] = []

            if lista_wpp.strip():
                jogadores_confirmados, nao_encontrados = parse_lista_whatsapp(
                    lista_wpp, jogadores_temp
                )
                st.success(f"✅ {len(jogadores_confirmados)} jogadores da liga identificados.")
                if nao_encontrados:
                    st.warning(
                        f"⚠️ Não encontrados no cadastro (serão ignorados): "
                        f"{', '.join(nao_encontrados)}"
                    )
            else:
                st.caption("Cole a lista acima para selecionar os participantes.")

        with col_visitantes:
            st.write("**Visitantes**")
            visitantes = db.list_visitantes(rid)
            for v in visitantes:
                c1, c2 = st.columns([4, 1])
                with c1:
                    st.write(f"👤 {v['nome']}")
                with c2:
                    if st.button("✕", key=f"del_v_{v['id']}"):
                        db.delete_visitante(v["id"])
                        st.rerun()
            with st.form(f"form_vis_{rid}", clear_on_submit=True):
                nome_v = st.text_input("Adicionar visitante")
                if st.form_submit_button("➕", use_container_width=True):
                    if nome_v.strip():
                        db.add_visitante(rid, nome_v.strip())
                        st.rerun()

        visitantes = db.list_visitantes(rid)
        total_confirmados = len(jogadores_confirmados) + len(visitantes)

        st.info(
            f"Da liga: **{len(jogadores_confirmados)}** · "
            f"Visitantes: **{len(visitantes)}** · "
            f"**Total: {total_confirmados} / {n_total}**"
        )

        pode_sortear = total_confirmados == n_total and total_confirmados % 4 == 0
        if not pode_sortear and lista_wpp.strip():
            if total_confirmados != n_total:
                st.warning(f"{'Faltam' if total_confirmados < n_total else 'Sobraram'} "
                           f"{abs(n_total - total_confirmados)} jogadores para completar as {n_total // 4} quadras.")

        sorteio_ativo = db.get_sorteio_ativo(rid)

        # Pré-gera o PDF se já existe sorteio, para o download ser direto no 1º clique
        pdf_data = None
        if sorteio_ativo:
            _jogos_pdf = db.list_jogos_sorteio(sorteio_ativo["id"])
            _nomes_pdf = {j["id"]: j["nome"] for j in todos_jogadores}
            _tabela_pdf = [{
                "rodada_interna": j["rodada_interna"],
                "quadra": j["quadra"],
                "dupla1": f"{nome_jogo(j,'dupla1_j1',_nomes_pdf)} / {nome_jogo(j,'dupla1_j2',_nomes_pdf)}",
                "dupla2": f"{nome_jogo(j,'dupla2_j1',_nomes_pdf)} / {nome_jogo(j,'dupla2_j2',_nomes_pdf)}",
                "dupla1_j1": j["dupla1_j1"], "dupla1_j2": j["dupla1_j2"],
                "dupla2_j1": j["dupla2_j1"], "dupla2_j2": j["dupla2_j2"],
            } for j in _jogos_pdf]
            pdf_data = gerar_planilha_pdf(rodada_sel["numero"], fmt_data(rodada_sel["data"]), _tabela_pdf, _nomes_pdf)

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            gerar = st.button(
                "🎲 Gerar Sorteio",
                disabled=not pode_sortear,
                use_container_width=True,
                type="primary",
            )
        with col_b2:
            if pdf_data:
                st.download_button(
                    "🖨️ Baixar Planilha PDF",
                    data=pdf_data,
                    file_name=f"planilha_rodada_{rodada_sel['numero']}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                )
            else:
                st.button("🖨️ Baixar Planilha PDF", disabled=True, use_container_width=True)

        if gerar and pode_sortear:
            with st.spinner("Gerando sorteio..."):
                try:
                    visitantes_reload = db.list_visitantes(rid)
                    ids_vis = [-(v["id"]) for v in visitantes_reload]
                    ids_finais = [j["id"] for j in jogadores_confirmados] + ids_vis

                    historico = db.get_historico_jogos_rodadas(rid, n=2)
                    resultado = gerar_sorteio(ids_finais, historico_jogos=historico)
                    erros = validar_sorteio(resultado, ids_finais)

                    if erros:
                        st.error(f"Sorteio inválido: {erros[0]}")
                    else:
                        sorteio_id = db.create_sorteio(rid)
                        nomes_map = {j["id"]: j["nome"] for j in todos_jogadores}
                        nomes_map.update({-(v["id"]): v["nome"] for v in visitantes_reload})
                        tabela = sorteio_para_tabela(resultado, nomes_map)

                        for jogo in tabela:
                            def _id(v): return v if v > 0 else None
                            def _nv(v): return nomes_map.get(v) if v < 0 else None
                            db.insert_jogo(
                                sorteio_id, jogo["rodada_interna"], jogo["quadra"],
                                _id(jogo["dupla1_j1"]), _id(jogo["dupla1_j2"]),
                                _id(jogo["dupla2_j1"]), _id(jogo["dupla2_j2"]),
                                _nv(jogo["dupla1_j1"]), _nv(jogo["dupla1_j2"]),
                                _nv(jogo["dupla2_j1"]), _nv(jogo["dupla2_j2"]),
                            )
                        db.set_sorteio_ativo(sorteio_id, rid)
                        db.update_rodada_status(rid, "sorteio_feito")
                        st.success("Sorteio gerado!")
                        st.rerun()

                except ValueError as e:
                    st.error(str(e))

        # Exibe sorteio ativo
        sorteio_ativo = db.get_sorteio_ativo(rid)
        if sorteio_ativo:
            st.divider()
            st.subheader(f"Sorteio Oficial — #{sorteio_ativo['numero']}")

            jogos = db.list_jogos_sorteio(sorteio_ativo["id"])
            nomes_map = {j["id"]: j["nome"] for j in todos_jogadores}
            rodadas_internas = sorted({j["rodada_interna"] for j in jogos})
            quadras = sorted({j["quadra"] for j in jogos})
            lookup = {(j["rodada_interna"], j["quadra"]): j for j in jogos}

            for ri in rodadas_internas:
                st.write(f"**Jogo {ri}**")
                cols = st.columns(len(quadras))
                for qi, q in enumerate(quadras):
                    jogo = lookup.get((ri, q))
                    if jogo:
                        with cols[qi]:
                            with st.container(border=True):
                                n1 = nome_jogo(jogo, "dupla1_j1", nomes_map)
                                n2 = nome_jogo(jogo, "dupla1_j2", nomes_map)
                                n3 = nome_jogo(jogo, "dupla2_j1", nomes_map)
                                n4 = nome_jogo(jogo, "dupla2_j2", nomes_map)
                                st.caption(f"Quadra {q}")
                                st.write(f"**{n1} / {n2}**")
                                st.markdown("<center>×</center>", unsafe_allow_html=True)
                                st.write(f"**{n3} / {n4}**")

            sorteios_todos = db.list_sorteios(rid)
            if len(sorteios_todos) > 1:
                st.divider()
                outro = st.selectbox(
                    "Trocar sorteio oficial:",
                    options=[s for s in sorteios_todos if s["id"] != sorteio_ativo["id"]],
                    format_func=lambda s: f"Sorteio #{s['numero']} — {s['created_at']}",
                )
                if st.button("Definir como oficial", type="secondary"):
                    db.set_sorteio_ativo(outro["id"], rid)
                    st.rerun()


# ── ABA 3: Entrada Manual ────────────────────────────────────────────────────
if tab_manual is not None:
  with tab_manual:
    rodadas = db.list_rodadas(tid)
    if not rodadas:
        st.info("Crie uma rodada na aba **Criar / Gerenciar Rodadas** primeiro.")
        st.stop()

    rodada_man = st.selectbox(
        "Rodada",
        options=rodadas,
        format_func=lambda r: f"Rodada {r['numero']} — {fmt_data(r['data'])} ({r['status']})",
        key="manual_rodada",
    )

    if not rodada_man:
        st.stop()

    rid_m = rodada_man["id"]
    n_quadras_m = rodada_man["n_jogadores"] // 4
    todos_j = db.list_jogadores(apenas_ativos=True)
    nomes_cadastrados = {j["nome"].lower(): j for j in todos_j}

    # Se rodada já concluída, apenas admin pode reeditar
    if rodada_man["status"] == "concluida" and not auth.is_admin():
        st.warning("Esta rodada já está concluída.")
        st.stop()

    st.caption(
        f"Rodada {rodada_man['numero']} · {n_quadras_m} quadras · "
        "💡 Nome cadastrado pontua no ranking. Nome desconhecido = visitante."
    )

    # ── Pré-carrega dados existentes para edição ──────────────────────────────
    prefill_key = f"prefilled_{rid_m}"
    if not st.session_state.get(prefill_key):
        sorteio_ativo = db.get_sorteio_ativo(rid_m)
        if sorteio_ativo:
            jogos_existentes = db.list_jogos_sorteio(sorteio_ativo["id"])
            resultados_existentes = {r["jogo_id"]: r for r in db.list_resultados_rodada(rid_m)}
            todos_j_map = {j["id"]: j["nome"] for j in db.list_jogadores(apenas_ativos=False)}
            for jex in jogos_existentes:
                ri_ex = jex["rodada_interna"]
                q_ex = jex["quadra"]
                def _nome_slot(jogo_dict, slot):
                    jid = jogo_dict.get(slot)
                    if jid is not None:
                        return todos_j_map.get(jid, "")
                    return jogo_dict.get(f"{slot}_nome") or ""
                st.session_state[f"m_{rid_m}_{ri_ex}_{q_ex}_j1"] = _nome_slot(jex, "dupla1_j1")
                st.session_state[f"m_{rid_m}_{ri_ex}_{q_ex}_j2"] = _nome_slot(jex, "dupla1_j2")
                st.session_state[f"m_{rid_m}_{ri_ex}_{q_ex}_j3"] = _nome_slot(jex, "dupla2_j1")
                st.session_state[f"m_{rid_m}_{ri_ex}_{q_ex}_j4"] = _nome_slot(jex, "dupla2_j2")
                res_ex = resultados_existentes.get(jex["id"])
                if res_ex:
                    st.session_state[f"m_{rid_m}_{ri_ex}_{q_ex}_g1"] = res_ex["games_dupla1"]
                    st.session_state[f"m_{rid_m}_{ri_ex}_{q_ex}_g2"] = res_ex["games_dupla2"]
            st.session_state[prefill_key] = True

    # Mostra no máximo 3 quadras por linha para ter espaço suficiente
    MAX_COLS = 3

    for ri in range(1, 5):
        st.markdown(f"#### Jogo {ri}")

        # Divide quadras em grupos de MAX_COLS
        quadras_grupo = [
            list(range(qi * MAX_COLS + 1, min(qi * MAX_COLS + MAX_COLS + 1, n_quadras_m + 1)))
            for qi in range((n_quadras_m + MAX_COLS - 1) // MAX_COLS)
        ]

        for grupo in quadras_grupo:
            cols = st.columns(len(grupo))
            for ci, q in enumerate(grupo):
                with cols[ci]:
                    with st.container(border=True):
                        st.markdown(f"**Quadra {q}**")

                        # Dupla 1 — nomes + placar inline
                        ca, cb, cc = st.columns([3, 3, 2])
                        with ca:
                            j1 = st.text_input("J1", key=f"m_{rid_m}_{ri}_{q}_j1", placeholder="Nome", label_visibility="collapsed")
                        with cb:
                            j2 = st.text_input("J2", key=f"m_{rid_m}_{ri}_{q}_j2", placeholder="Nome", label_visibility="collapsed")
                        with cc:
                            g1 = st.selectbox(
                                "g1", options=list(range(8)), index=0,
                                key=f"m_{rid_m}_{ri}_{q}_g1", label_visibility="collapsed"
                            )

                        st.markdown("<div style='text-align:center;font-weight:bold;line-height:1'>×</div>", unsafe_allow_html=True)

                        # Dupla 2 — nomes + placar inline
                        cd, ce, cf = st.columns([3, 3, 2])
                        with cd:
                            j3 = st.text_input("J3", key=f"m_{rid_m}_{ri}_{q}_j3", placeholder="Nome", label_visibility="collapsed")
                        with ce:
                            j4 = st.text_input("J4", key=f"m_{rid_m}_{ri}_{q}_j4", placeholder="Nome", label_visibility="collapsed")
                        with cf:
                            g2 = st.selectbox(
                                "g2", options=list(range(8)), index=0,
                                key=f"m_{rid_m}_{ri}_{q}_g2", label_visibility="collapsed"
                            )

                        # Indica visitantes
                        for nd in [j1, j2, j3, j4]:
                            if nd and nd.strip() and nd.strip().lower() not in nomes_cadastrados:
                                st.caption(f"👤 {nd} = visitante")

    st.markdown("---")

    col_salvar, col_pub = st.columns(2)
    with col_salvar:
        salvar_man = st.button("💾 Salvar Rascunho", use_container_width=True)
    with col_pub:
        publicar_man = st.button(
            "✅ Salvar e Publicar Rodada",
            use_container_width=True,
            type="primary",
            help="Salva sorteio, calcula pontos e marca a rodada como concluída.",
        )

    def _coletar_dados_manual():
        """Coleta e valida todos os campos do formulário manual."""
        erros = []
        jogos_coletados = []

        for ri in range(1, 5):
            for qi in range(n_quadras_m):
                q = qi + 1
                j1s = st.session_state.get(f"m_{rid_m}_{ri}_{q}_j1", "").strip()
                j2s = st.session_state.get(f"m_{rid_m}_{ri}_{q}_j2", "").strip()
                j3s = st.session_state.get(f"m_{rid_m}_{ri}_{q}_j3", "").strip()
                j4s = st.session_state.get(f"m_{rid_m}_{ri}_{q}_j4", "").strip()
                g1v = int(st.session_state.get(f"m_{rid_m}_{ri}_{q}_g1", 6))
                g2v = int(st.session_state.get(f"m_{rid_m}_{ri}_{q}_g2", 0))

                if not all([j1s, j2s, j3s, j4s]):
                    erros.append(f"Jogo {ri} / Quadra {q}: todos os nomes são obrigatórios.")
                    continue

                ok_p, msg_p = validar_placar(g1v, g2v)
                if not ok_p:
                    erros.append(f"Jogo {ri} / Quadra {q}: {msg_p}")

                def resolve(nome_str):
                    j = nomes_cadastrados.get(nome_str.lower())
                    return (j["id"], None) if j else (None, nome_str)

                id1, nv1 = resolve(j1s)
                id2, nv2 = resolve(j2s)
                id3, nv3 = resolve(j3s)
                id4, nv4 = resolve(j4s)

                jogos_coletados.append({
                    "ri": ri, "q": q,
                    "id1": id1, "id2": id2, "id3": id3, "id4": id4,
                    "nv1": nv1, "nv2": nv2, "nv3": nv3, "nv4": nv4,
                    "g1": g1v, "g2": g2v,
                    "tiebreak": 1 if max(g1v, g2v) == 7 and min(g1v, g2v) == 6 else 0,
                })

        return jogos_coletados, erros

    def _persistir_manual(jogos_coletados, publicar=False):
        """Salva sorteio manual e resultados no banco."""
        # Remove sorteio anterior se existir
        sorteios_existentes = db.list_sorteios(rid_m)
        for s in sorteios_existentes:
            db.delete_sorteio(s["id"])

        sorteio_id = db.create_sorteio(rid_m)

        for jogo in jogos_coletados:
            jogo_id = db.insert_jogo(
                sorteio_id, jogo["ri"], jogo["q"],
                jogo["id1"], jogo["id2"], jogo["id3"], jogo["id4"],
                jogo["nv1"], jogo["nv2"], jogo["nv3"], jogo["nv4"],
            )
            db.upsert_resultado(jogo_id, jogo["g1"], jogo["g2"], jogo["tiebreak"])

        db.set_sorteio_ativo(sorteio_id, rid_m)
        db.update_rodada_status(rid_m, "concluida" if publicar else "sorteio_feito")

        if publicar:
            db.delete_pontuacao_rodada(rid_m)
            calcular_pontuacao_rodada(rid_m)

        return sorteio_id

    if salvar_man:
        jogos_coletados, erros = _coletar_dados_manual()
        if erros:
            for e in erros:
                st.error(e)
        else:
            _persistir_manual(jogos_coletados, publicar=False)
            st.success("Rascunho salvo! Você pode continuar editando.")
            st.rerun()

    if publicar_man:
        jogos_coletados, erros = _coletar_dados_manual()
        if erros:
            for e in erros:
                st.error(e)
        else:
            _persistir_manual(jogos_coletados, publicar=True)
            beer = get_beer_list(rid_m)
            st.success("Rodada publicada e pontos calculados!")
            if beer:
                st.warning(f"🍺 Devem cerveja: {', '.join(beer)}")
            st.rerun()


# ── ABA 4: Auditoria ─────────────────────────────────────────────────────────
with tab_auditoria:
    import pandas as pd

    rodadas = db.list_rodadas(tid)
    if not rodadas:
        st.info("Nenhuma rodada criada.")
        rodada_audit = None
    else:
        # Prioridade: rodada aberta (pendente/sorteio_feito) → última concluída
        _aberta = next((r for r in reversed(rodadas) if r["status"] != "concluida"), None)
        _default_idx = rodadas.index(_aberta) if _aberta else len(rodadas) - 1
        rodada_audit = st.selectbox(
            "Rodada",
            options=rodadas,
            format_func=lambda r: f"Rodada {r['numero']} — {fmt_data(r['data'])}",
            index=_default_idx,
            key="audit_rodada",
        )

    if rodada_audit:
        sorteios = db.list_sorteios(rodada_audit["id"])
        sorteio_ativo = db.get_sorteio_ativo(rodada_audit["id"])
        ativo_id = sorteio_ativo["id"] if sorteio_ativo else None

        st.subheader(f"Sorteios — Rodada {rodada_audit['numero']}")
        if not sorteios:
            st.info("Nenhum sorteio gerado para esta rodada.")
        else:
            st.metric("Total de sorteios gerados", len(sorteios))
            st.divider()

            for s in sorteios:
                badge = "🟢 OFICIAL" if s["id"] == ativo_id else "⚫ Não oficial"
                with st.expander(f"Sorteio #{s['numero']} — {s['created_at']}  [{badge}]"):
                    jogos = db.list_jogos_sorteio(s["id"])
                    nomes_map_a = {j["id"]: j["nome"] for j in db.list_jogadores(False)}

                    rodadas_int = sorted({j["rodada_interna"] for j in jogos})
                    quadras_a = sorted({j["quadra"] for j in jogos})
                    lookup_a = {(j["rodada_interna"], j["quadra"]): j for j in jogos}

                    linhas = []
                    for ri in rodadas_int:
                        linha = {"Jogo": f"Jogo {ri}"}
                        for q in quadras_a:
                            jogo = lookup_a.get((ri, q))
                            if jogo:
                                linha[f"Q{q}"] = (
                                    f"{nome_jogo(jogo,'dupla1_j1',nomes_map_a)}/"
                                    f"{nome_jogo(jogo,'dupla1_j2',nomes_map_a)}"
                                    f" × "
                                    f"{nome_jogo(jogo,'dupla2_j1',nomes_map_a)}/"
                                    f"{nome_jogo(jogo,'dupla2_j2',nomes_map_a)}"
                                )
                            else:
                                linha[f"Q{q}"] = "—"
                        linhas.append(linha)

                    st.dataframe(pd.DataFrame(linhas).set_index("Jogo"), use_container_width=True)

                    if s["id"] != ativo_id:
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button(f"Definir #{s['numero']} como oficial", key=f"of_{s['id']}"):
                                db.set_sorteio_ativo(s["id"], rodada_audit["id"])
                                st.rerun()
                        with c2:
                            if st.button(f"🗑️ Excluir #{s['numero']}", key=f"del_{s['id']}"):
                                db.delete_sorteio(s["id"])
                                st.rerun()
