"""
Página de lançamento de resultados da Liga Quarta Scaff.
Suporta lançamento atual e manual (rodadas passadas).
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth
from src.utils import fmt_data
from src.scoring import calcular_pontuacao_rodada, get_beer_list, validar_placar, calcular_detalhe_por_jogo
from src.ranking import calcular_ranking
from src.pdf_generator import gerar_email_rodada_pdf, gerar_ranking_pdf, gerar_ranking_sem_desconto_pdf
from src.email_sender import enviar_ranking, smtp_configurado

st.set_page_config(page_title="Resultados — Liga Scaff", page_icon="📋", layout="wide")
auth.render_sidebar_user()
auth.require_organizer()

st.title("📋 Lançamento de Resultados")

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
if not rodadas:
    st.info("Nenhuma rodada criada para esta temporada.")
    st.stop()

# ── Seleção de rodada ─────────────────────────────────────────────────────────
rodadas_com_sorteio = [r for r in rodadas if r["status"] in ("sorteio_feito", "concluida")]
if not rodadas_com_sorteio:
    st.warning("Nenhuma rodada com sorteio. Gere um sorteio na página **Sorteio**.")
    st.stop()

rodada_sel = st.selectbox(
    "Rodada",
    options=rodadas_com_sorteio,
    format_func=lambda r: f"Rodada {r['numero']} — {fmt_data(r['data'])} ({r['status']})",
    index=len(rodadas_com_sorteio) - 1,
)

rid = rodada_sel["id"]
todos_jogadores = db.list_jogadores(apenas_ativos=False)
nomes_map = {j["id"]: j["nome"] for j in todos_jogadores}

def nome_jogo(jogo: dict, slot: str) -> str:
    jid = jogo.get(slot)
    if jid is not None:
        return nomes_map.get(jid, str(jid))
    nome_vis = jogo.get(f"{slot}_nome")
    return nome_vis if nome_vis else "?"

jogos = db.list_jogos_rodada(rid)
if not jogos:
    st.warning("Nenhum jogo encontrado. Defina um sorteio como oficial em **Sorteio**.")
    st.stop()

# ── Lançamento de resultados ──────────────────────────────────────────────────
st.subheader(f"Jogos da Rodada {rodada_sel['numero']} — {fmt_data(rodada_sel['data'])}")

rodadas_internas = sorted({j["rodada_interna"] for j in jogos})
quadras = sorted({j["quadra"] for j in jogos})
lookup = {(j["rodada_interna"], j["quadra"]): j for j in jogos}

# Carrega resultados existentes
resultados_salvos = {j["jogo_id"]: j for j in db.list_resultados_rodada(rid)}

alteracoes: dict[int, tuple[int, int]] = {}

MAX_COLS = 3

for ri in rodadas_internas:
    st.write(f"**Jogo {ri}**")

    quadras_grupo = [
        quadras[i:i + MAX_COLS] for i in range(0, len(quadras), MAX_COLS)
    ]

    for grupo in quadras_grupo:
        cols = st.columns(len(grupo))
        for ci, q in enumerate(grupo):
            jogo = lookup.get((ri, q))
            if not jogo:
                continue

            with cols[ci]:
                with st.container(border=True):
                    n1 = nome_jogo(jogo, "dupla1_j1")
                    n2 = nome_jogo(jogo, "dupla1_j2")
                    n3 = nome_jogo(jogo, "dupla2_j1")
                    n4 = nome_jogo(jogo, "dupla2_j2")

                    res_salvo = resultados_salvos.get(jogo["id"])
                    g1_default = res_salvo["games_dupla1"] if res_salvo else 0
                    g2_default = res_salvo["games_dupla2"] if res_salvo else 0

                    jid = jogo["id"]
                    edit_key = f"edit_{jid}"
                    em_edicao = st.session_state.get(edit_key, False)

                    if em_edicao and (auth.is_admin() or auth.is_organizer()):
                        st.markdown(f"**Quadra {q} ✏️**")
                        todos_j_edit = db.list_jogadores(apenas_ativos=False)
                        nomes_cad_edit = {j["nome"].lower(): j for j in todos_j_edit}

                        # st.form garante que os valores são lidos no submit, sem interferência de rerun
                        with st.form(key=f"form_edit_{jid}"):
                            ea, eb, ec = st.columns([3, 3, 2])
                            with ea:
                                ej1 = st.text_input("J1", value=n1, placeholder="J1", label_visibility="collapsed")
                            with eb:
                                ej2 = st.text_input("J2", value=n2, placeholder="J2", label_visibility="collapsed")
                            with ec:
                                eg1 = st.selectbox("g1", options=list(range(8)), index=g1_default, label_visibility="collapsed")

                            st.markdown("<div style='text-align:center;font-weight:bold;line-height:1'>×</div>", unsafe_allow_html=True)

                            ed, ee, ef = st.columns([3, 3, 2])
                            with ed:
                                ej3 = st.text_input("J3", value=n3, placeholder="J3", label_visibility="collapsed")
                            with ee:
                                ej4 = st.text_input("J4", value=n4, placeholder="J4", label_visibility="collapsed")
                            with ef:
                                eg2 = st.selectbox("g2", options=list(range(8)), index=g2_default, label_visibility="collapsed")

                            fb1, fb2 = st.columns(2)
                            with fb1:
                                submitted = st.form_submit_button("💾 Salvar", use_container_width=True, type="primary")
                            with fb2:
                                cancelar = st.form_submit_button("✕ Cancelar", use_container_width=True)

                        if cancelar:
                            st.session_state.pop(edit_key, None)
                            st.rerun()

                        if submitted:
                            nomes_ok = all([ej1.strip(), ej2.strip(), ej3.strip(), ej4.strip()])
                            valido_e, erro_e = validar_placar(eg1, eg2)
                            if not nomes_ok:
                                st.error("Preencha todos os 4 nomes.")
                            elif not valido_e:
                                st.error(f"Placar inválido: {eg1}×{eg2}. Válidos: 6-0 a 6-4 ou 7-6.")
                            else:
                                def _resolve(nome_str):
                                    j_r = nomes_cad_edit.get(nome_str.lower())
                                    return (j_r["id"], None) if j_r else (None, nome_str)
                                id1e, nv1e = _resolve(ej1.strip())
                                id2e, nv2e = _resolve(ej2.strip())
                                id3e, nv3e = _resolve(ej3.strip())
                                id4e, nv4e = _resolve(ej4.strip())
                                db.update_jogo_players(jid, id1e, id2e, id3e, id4e, nv1e, nv2e, nv3e, nv4e)
                                tb_e = 1 if max(eg1, eg2) == 7 and min(eg1, eg2) == 6 else 0
                                db.upsert_resultado(jid, eg1, eg2, tb_e)
                                if rodada_sel["status"] == "concluida":
                                    db.delete_pontuacao_rodada(rid)
                                    calcular_pontuacao_rodada(rid)
                                st.session_state.pop(edit_key, None)
                                st.rerun()

                    else:
                        hdr_col, btn_col = st.columns([5, 1])
                        with hdr_col:
                            st.markdown(f"**Quadra {q}**")
                        with btn_col:
                            if auth.is_admin() or auth.is_organizer():
                                if st.button("✏️", key=f"btn_edit_{jid}", help="Editar jogadores e placar"):
                                    st.session_state[edit_key] = True
                                    st.rerun()

                        ca, cb = st.columns([5, 2])
                        with ca:
                            st.write(f"🔵 {n1} / {n2}")
                        with cb:
                            g1 = st.selectbox(
                                "g1", options=list(range(8)), index=g1_default,
                                key=f"g1_{jogo['id']}", label_visibility="collapsed"
                            )

                        st.markdown("<div style='text-align:center;font-weight:bold;line-height:1'>×</div>",
                                    unsafe_allow_html=True)

                        cc, cd = st.columns([5, 2])
                        with cc:
                            st.write(f"🔴 {n3} / {n4}")
                        with cd:
                            g2 = st.selectbox(
                                "g2", options=list(range(8)), index=g2_default,
                                key=f"g2_{jogo['id']}", label_visibility="collapsed"
                            )

                        valido, erro = validar_placar(g1, g2)
                        if not valido:
                            st.warning(erro, icon="⚠️")
                        if valido:
                            alteracoes[jogo["id"]] = (g1, g2)
                            if res_salvo:
                                st.caption("✅ Salvo")

st.divider()

# ── Botões de ação ────────────────────────────────────────────────────────────
col1, col2, col3 = st.columns(3)

with col1:
    salvar_rascunho = st.button("💾 Salvar Rascunho", use_container_width=True)

with col2:
    publicar = st.button(
        "✅ Calcular e Publicar Rodada",
        use_container_width=True,
        type="primary",
        help="Calcula pontos e marca a rodada como concluída",
    )

with col3:
    jogos_validos = len(alteracoes) == len(jogos)
    enviar = st.button(
        "📧 Enviar Ranking por E-mail",
        use_container_width=True,
        disabled=rodada_sel["status"] != "concluida",
        help="Disponível após publicar a rodada",
    )

if salvar_rascunho:
    salvos = 0
    for jogo_id, (g1, g2) in alteracoes.items():
        valido, _ = validar_placar(g1, g2)
        if valido:
            tiebreak = 1 if (max(g1, g2) == 7 and min(g1, g2) == 6) else 0
            db.upsert_resultado(jogo_id, g1, g2, tiebreak)
            salvos += 1
    st.success(f"{salvos} resultado(s) salvo(s).")
    st.rerun()

if publicar:
    erros = []
    for jogo_id, (g1, g2) in alteracoes.items():
        valido, msg = validar_placar(g1, g2)
        if not valido:
            erros.append(f"Jogo {jogo_id}: {msg}")

    if len(alteracoes) < len(jogos):
        erros.append(f"Faltam {len(jogos) - len(alteracoes)} resultado(s) com placar válido.")

    if erros:
        for e in erros:
            st.error(e)
    else:
        with st.spinner("Calculando pontos..."):
            for jogo_id, (g1, g2) in alteracoes.items():
                tiebreak = 1 if (max(g1, g2) == 7 and min(g1, g2) == 6) else 0
                db.upsert_resultado(jogo_id, g1, g2, tiebreak)

            calcular_pontuacao_rodada(rid)
            db.update_rodada_status(rid, "concluida")

        st.success("Rodada publicada! Ranking atualizado.")
        beer = get_beer_list(rid)
        if beer:
            st.warning(f"🍺 Devem cerveja: {', '.join(beer)}")
        st.rerun()

# ── Geração dos PDFs (salva em session_state para sobreviver ao rerun) ─────────
pdf_key = f"pdfs_{rid}"

if enviar:
    with st.spinner("Gerando PDFs..."):
        ranking_atual = calcular_ranking(tid)
        detalhes = calcular_detalhe_por_jogo(rid)
        beer = get_beer_list(rid)
        rodadas_concluidas_all = [r for r in db.list_rodadas(tid) if r["status"] == "concluida"]
        rodadas_numeros = sorted([r["numero"] for r in rodadas_concluidas_all])
        data_fmt = str(rodada_sel.get("data", ""))
        rn = rodada_sel["numero"]

        pdf1 = gerar_email_rodada_pdf(
            detalhes=detalhes,
            temporada_nome=temporada["nome"],
            rodada_num=rn,
            rodada_data=data_fmt,
        )
        pdf2 = gerar_ranking_pdf(
            ranking=ranking_atual,
            temporada_nome=temporada["nome"],
            rodada_atual=rn,
            n_rodadas_total=temporada["n_rodadas"],
            rodadas_numeros=rodadas_numeros,
        )
        pdf3 = gerar_ranking_sem_desconto_pdf(
            ranking=ranking_atual,
            temporada_nome=temporada["nome"],
            rodada_atual=rn,
            n_rodadas_total=temporada["n_rodadas"],
            rodadas_numeros=rodadas_numeros,
        )

        st.session_state[pdf_key] = {
            "pdf1": pdf1, "pdf2": pdf2, "pdf3": pdf3,
            "rn": rn, "beer": beer,
            "temporada_nome": temporada["nome"],
        }

# ── Exibe downloads e botão de envio se PDFs já foram gerados ─────────────────
if pdf_key in st.session_state:
    dados = st.session_state[pdf_key]
    rn = dados["rn"]

    st.divider()
    st.markdown("**📥 Downloads**")
    dc1, dc2, dc3 = st.columns(3)
    with dc1:
        st.download_button("📋 Detalhe da Rodada", data=dados["pdf1"],
                           file_name=f"Detalhe_R{rn}.pdf", mime="application/pdf",
                           use_container_width=True)
    with dc2:
        st.download_button("📊 Ranking c/ Descarte", data=dados["pdf2"],
                           file_name=f"Ranking_Descarte.pdf", mime="application/pdf",
                           use_container_width=True)
    with dc3:
        st.download_button("📊 Ranking Geral", data=dados["pdf3"],
                           file_name=f"Ranking_Geral.pdf", mime="application/pdf",
                           use_container_width=True)

    if smtp_configurado():
        if st.button("📧 Enviar os 3 PDFs por E-mail", type="primary", use_container_width=True):
            with st.spinner("Enviando..."):
                pdfs = [
                    (dados["pdf1"], f"Detalhe_R{rn}.pdf"),
                    (dados["pdf2"], "Ranking_Descarte.pdf"),
                    (dados["pdf3"], "Ranking_Geral.pdf"),
                ]
                sucesso, msg_erro = enviar_ranking(pdfs, rn, dados["temporada_nome"], dados["beer"])
            if sucesso:
                st.success("E-mail enviado com os 3 PDFs!")
                st.session_state.pop(pdf_key, None)
            else:
                st.error(f"Erro no envio: {msg_erro}")
    else:
        st.warning("Resend não configurado. Use os botões acima para baixar os PDFs.")

# ── Preview dos placares já salvos ───────────────────────────────────────────
if resultados_salvos:
    with st.expander("Ver resumo dos resultados salvos"):
        pontuacoes = db.get_pontuacao_rodada(rid)
        if pontuacoes:
            import pandas as pd
            dados = [
                {
                    "Jogador": p["nome"],
                    "Pontos": p["pontos"],
                    "Ganhos": p["jogos_ganhos"],
                    "Perdidos": p["jogos_perdidos"],
                    "🍺": "Sim" if p["tem_beer"] else "—",
                }
                for p in pontuacoes
            ]
            st.dataframe(pd.DataFrame(dados), use_container_width=True, hide_index=True)
