"""
Página de sorteio da Liga Quarta Scaff.
Cria rodadas, gera sorteios, entrada manual combinada (jogadores + resultados) e auditoria.
"""

import streamlit as st
import sys
from pathlib import Path
from datetime import date
import time
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth
from src.pdf_generator import gerar_planilha_pdf
from src.scoring import calcular_pontuacao_rodada, get_beer_list, validar_placar
from src.sorteio_job import is_job_running, start_sorteio_job
from src.utils import parse_lista_whatsapp, validar_nome_jogador, fmt_data, fmt_datetime_brasilia

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


def _fmt_duracao(segundos: float) -> str:
    total = max(int(round(segundos)), 0)
    minutos, segs = divmod(total, 60)
    horas, mins = divmod(minutos, 60)
    if horas:
        return f"{horas}h {mins:02d}m {segs:02d}s"
    if mins:
        return f"{mins}m {segs:02d}s"
    return f"{segs}s"


def nome_jogo(jogo: dict, slot: str, nomes_map: dict) -> str:
    jid = jogo.get(slot)
    if jid is not None:
        return nomes_map.get(jid, str(jid))
    v = jogo.get(f"{slot}_nome")
    return v if v else "?"


def _partners_and_opponents(jogos: list[dict]) -> tuple[dict[int, set[int]], dict[int, set[int]]]:
    parceiros: dict[int, set[int]] = defaultdict(set)
    adversarios: dict[int, set[int]] = defaultdict(set)
    for jogo in jogos:
        j1, j2 = jogo["dupla1_j1"], jogo["dupla1_j2"]
        j3, j4 = jogo["dupla2_j1"], jogo["dupla2_j2"]
        if j1 is not None and j2 is not None:
            parceiros[j1].add(j2); parceiros[j2].add(j1)
        if j3 is not None and j4 is not None:
            parceiros[j3].add(j4); parceiros[j4].add(j3)
        for p in (j1, j2):
            if p is not None:
                adversarios[p].update(x for x in (j3, j4) if x is not None)
        for p in (j3, j4):
            if p is not None:
                adversarios[p].update(x for x in (j1, j2) if x is not None)
    return parceiros, adversarios


def _same_night_violations(jogos: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    parceiros: dict[int, set[int]] = defaultdict(set)
    adversarios: dict[int, set[int]] = defaultdict(set)
    repetiu_parceiro: list[dict] = []
    repetiu_adversario: list[dict] = []
    enfrentou_ex_parceiro: list[dict] = []

    for jogo in jogos:
        ri = jogo["rodada_interna"]
        q = jogo["quadra"]
        j1, j2 = jogo["dupla1_j1"], jogo["dupla1_j2"]
        j3, j4 = jogo["dupla2_j1"], jogo["dupla2_j2"]

        if j1 is not None and j2 is not None and j2 in parceiros[j1]:
            repetiu_parceiro.append({"jogadores": (j1, j2), "rodada_interna": ri, "quadra": q})
        if j3 is not None and j4 is not None and j4 in parceiros[j3]:
            repetiu_parceiro.append({"jogadores": (j3, j4), "rodada_interna": ri, "quadra": q})

        for p, adjs in ((j1, (j3, j4)), (j2, (j3, j4)), (j3, (j1, j2)), (j4, (j1, j2))):
            if p is None:
                continue
            for adv in adjs:
                if adv is None:
                    continue
                if adv in adversarios[p]:
                    repetiu_adversario.append({"jogador": p, "adversario": adv, "rodada_interna": ri, "quadra": q})
                if adv in parceiros[p]:
                    enfrentou_ex_parceiro.append({"jogador": p, "outro": adv, "rodada_interna": ri, "quadra": q})

        if j1 is not None and j2 is not None:
            parceiros[j1].add(j2); parceiros[j2].add(j1)
        if j3 is not None and j4 is not None:
            parceiros[j3].add(j4); parceiros[j4].add(j3)
        for p in (j1, j2):
            if p is not None:
                adversarios[p].update(x for x in (j3, j4) if x is not None)
        for p in (j3, j4):
            if p is not None:
                adversarios[p].update(x for x in (j1, j2) if x is not None)

    return repetiu_parceiro, repetiu_adversario, enfrentou_ex_parceiro


def _analisar_comparacao_rodada(
    rodada_atual: dict,
    rodadas_anteriores: list[dict],
    nomes_map: dict[int, str],
) -> dict:
    sorteio_ativo = db.get_sorteio_ativo(rodada_atual["id"])
    if not sorteio_ativo:
        return {"erro": "Nenhum sorteio oficial encontrado para a rodada selecionada."}

    jogos_atual = db.list_jogos_sorteio(sorteio_ativo["id"])
    if not jogos_atual:
        return {"erro": "O sorteio oficial selecionado não possui jogos cadastrados."}

    parceiros_atual, adversarios_atual = _partners_and_opponents(jogos_atual)
    repetiu_parceiro_noite, repetiu_adversario_noite, enfrentou_ex_parceiro = _same_night_violations(jogos_atual)

    base_por_numero: dict[int, tuple[dict[int, set[int]], dict[int, set[int]]]] = {}
    jogadores_base_por_numero: dict[int, set[int]] = {}
    for rodada in rodadas_anteriores:
        sorteio_base = db.get_sorteio_ativo(rodada["id"])
        if not sorteio_base:
            continue
        jogos_base = db.list_jogos_sorteio(sorteio_base["id"])
        parceiros_base, adversarios_base = _partners_and_opponents(jogos_base)
        base_por_numero[rodada["numero"]] = (parceiros_base, adversarios_base)
        jogadores_base_por_numero[rodada["numero"]] = set(parceiros_base) | set(adversarios_base)

    jogadores_atuais = sorted(set(parceiros_atual) | set(adversarios_atual))
    ref_por_jogador: dict[int, int | None] = {}
    parceiros_ref_por_jogador: dict[int, set[int]] = {}
    adversarios_ref_por_jogador: dict[int, set[int]] = {}

    for jogador in jogadores_atuais:
        rodada_ref = None
        for rodada in rodadas_anteriores:
            numero = rodada["numero"]
            if jogador in jogadores_base_por_numero.get(numero, set()):
                rodada_ref = numero
                break
        ref_por_jogador[jogador] = rodada_ref
        if rodada_ref is None:
            parceiros_ref_por_jogador[jogador] = set()
            adversarios_ref_por_jogador[jogador] = set()
            continue
        parceiros_base, adversarios_base = base_por_numero[rodada_ref]
        parceiros_ref_por_jogador[jogador] = parceiros_base.get(jogador, set())
        adversarios_ref_por_jogador[jogador] = adversarios_base.get(jogador, set())

    violacoes_parceiro_ref: list[dict] = []
    repeticoes_adversarios_ref: list[dict] = []

    for jogador in jogadores_atuais:
        parceiros_repetidos = sorted(parceiros_atual.get(jogador, set()) & parceiros_ref_por_jogador[jogador])
        if parceiros_repetidos:
            violacoes_parceiro_ref.append({
                "jogador": jogador,
                "rodada_ref": ref_por_jogador[jogador],
                "parceiros": parceiros_repetidos,
            })

        adversarios_repetidos = sorted(adversarios_atual.get(jogador, set()) & adversarios_ref_por_jogador[jogador])
        repeticoes_adversarios_ref.append({
            "jogador": jogador,
            "rodada_ref": ref_por_jogador[jogador],
            "adversarios": adversarios_repetidos,
            "quantidade": len(adversarios_repetidos),
        })

    repeticoes_adversarios_ref.sort(key=lambda item: (-item["quantidade"], nomes_map.get(item["jogador"], str(item["jogador"]))))

    return {
        "rodada_atual": rodada_atual,
        "rodadas_anteriores": rodadas_anteriores,
        "repetiu_parceiro_noite": repetiu_parceiro_noite,
        "repetiu_adversario_noite": repetiu_adversario_noite,
        "enfrentou_ex_parceiro": enfrentou_ex_parceiro,
        "violacoes_parceiro_ref": violacoes_parceiro_ref,
        "repeticoes_adversarios_ref": repeticoes_adversarios_ref,
        "nomes_map": nomes_map,
    }


if auth.is_admin():
    tab_criar, tab_sorteio, tab_manual, tab_auditoria, tab_comparacao = st.tabs(
        ["Criar / Gerenciar Rodadas", "Gerar Sorteio", "Entrada Manual", "Auditoria", "Comparação"]
    )
else:
    tab_sorteio, tab_auditoria, tab_comparacao = st.tabs(["Gerar Sorteio", "Auditoria", "Comparação"])
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
                    status_icon = {"pendente": "⏳", "gerando_sorteio": "⚙️", "sorteio_feito": "🎲", "concluida": "✅"}.get(r["status"], "?")
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
    rodadas_pendentes = [r for r in rodadas if r["status"] in ("pendente", "gerando_sorteio", "sorteio_feito")]

    if not rodadas_pendentes:
        st.info("Nenhuma rodada pendente de sorteio.")
        rodada_sel = None
    else:
        rodada_sel = st.selectbox(
            "Rodada para Sortear",
            options=rodadas_pendentes,
            format_func=lambda r: f"Rodada {r['numero']} — {fmt_data(r['data'])} ({r['n_jogadores']} jogadores)",
            index=len(rodadas_pendentes) - 1,
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
        sorteio_job = db.get_sorteio_job(rid)
        job_em_andamento = (
            bool(sorteio_job and sorteio_job["status"] in ("queued", "running", "finalizing"))
            or is_job_running(rid)
        )

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
                disabled=(not pode_sortear) or job_em_andamento,
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

        if sorteio_job:
            pct = max(0, min(int((sorteio_job.get("progress") or 0) * 100), 100))
            st.progress(pct)
            st.caption(
                f"{sorteio_job.get('message') or 'Aguardando...'} "
                f"Tentativa {sorteio_job.get('attempt') or 0}/{sorteio_job.get('max_attempts') or 0} · "
                f"validos {sorteio_job.get('valid_found') or 0}/{sorteio_job.get('max_valid_found') or 0}"
            )
            if sorteio_job.get("status") in ("queued", "running", "finalizing"):
                st.caption(
                    f"Tempo restante estimado: ~{_fmt_duracao(sorteio_job.get('eta_seconds') or 0)} · "
                    f"tempo decorrido: ~{_fmt_duracao(sorteio_job.get('elapsed_seconds') or 0)}"
                )
                st.info("O sorteio segue em segundo plano. Você pode trocar de página ou fechar a aba e acompanhar o tempo pela sidebar.")
            elif sorteio_job.get("status") == "completed":
                st.success("Sorteio em segundo plano concluído.")
            elif sorteio_job.get("status") == "error":
                st.error(sorteio_job.get("error_text") or "Falha ao gerar sorteio.")

        if gerar and pode_sortear:
            visitantes_reload = db.list_visitantes(rid)
            ids_vis = [-(v["id"]) for v in visitantes_reload]
            ids_finais = [j["id"] for j in jogadores_confirmados] + ids_vis
            historico = db.get_historico_jogos_rodadas(rid, n=2)
            nomes_map = {j["id"]: j["nome"] for j in todos_jogadores}
            nomes_map.update({-(v["id"]): v["nome"] for v in visitantes_reload})
            iniciou = start_sorteio_job(
                rid,
                ids_finais,
                nomes_map,
                historico_jogos=historico,
            )
            if iniciou:
                st.success("Sorteio iniciado em segundo plano.")
                st.rerun()
            else:
                st.warning("Já existe um sorteio em andamento para esta rodada.")

        if sorteio_job and sorteio_job.get("status") in ("queued", "running", "finalizing"):
            time.sleep(2)
            st.rerun()

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
                    format_func=lambda s: f"Sorteio #{s['numero']} — {fmt_datetime_brasilia(s['created_at'])}",
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

    _aberta_man = next((r for r in reversed(rodadas) if r["status"] != "concluida"), None)
    _idx_man = rodadas.index(_aberta_man) if _aberta_man else len(rodadas) - 1
    rodada_man = st.selectbox(
        "Rodada",
        options=rodadas,
        format_func=lambda r: f"Rodada {r['numero']} — {fmt_data(r['data'])} ({r['status']})",
        index=_idx_man,
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
                with st.expander(f"Sorteio #{s['numero']} — {fmt_datetime_brasilia(s['created_at'])}  [{badge}]"):
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


# ── ABA 5: Comparação ────────────────────────────────────────────────────────
with tab_comparacao:
    rodadas = db.list_rodadas(tid)
    rodadas_com_sorteio = [r for r in rodadas if db.get_sorteio_ativo(r["id"])]

    if not rodadas_com_sorteio:
        st.info("Nenhuma rodada com sorteio oficial para comparar.")
        st.stop()

    _aberta = next((r for r in reversed(rodadas_com_sorteio) if r["status"] != "concluida"), None)
    _default_idx = rodadas_com_sorteio.index(_aberta) if _aberta else len(rodadas_com_sorteio) - 1
    rodada_cmp = st.selectbox(
        "Rodada para comparar",
        options=rodadas_com_sorteio,
        format_func=lambda r: f"Rodada {r['numero']} — {fmt_data(r['data'])}",
        index=_default_idx,
        key="comparacao_rodada",
    )

    rodadas_base = [
        r for r in sorted(rodadas, key=lambda item: item["numero"], reverse=True)
        if r["numero"] < rodada_cmp["numero"] and db.get_sorteio_ativo(r["id"])
    ][:2]

    st.subheader(f"Comparação do Sorteio — Rodada {rodada_cmp['numero']}")
    if not rodadas_base:
        st.warning("Não há rodadas anteriores com sorteio oficial suficiente para comparar.")
        st.stop()

    st.caption(
        "Base usada na comparação: "
        + " · ".join(f"Rodada {r['numero']} ({fmt_data(r['data'])})" for r in rodadas_base)
    )
    st.caption(
        "A referência é individual por jogador: primeiro tenta a rodada imediatamente anterior; "
        "se o jogador não participou dela, usa a rodada anterior seguinte dentro da base."
    )

    nomes_map = {j["id"]: j["nome"] for j in db.list_jogadores(False)}
    analise = _analisar_comparacao_rodada(rodada_cmp, rodadas_base, nomes_map)

    if analise.get("erro"):
        st.error(analise["erro"])
        st.stop()

    repetiu_parceiro_noite = analise["repetiu_parceiro_noite"]
    repetiu_adversario_noite = analise["repetiu_adversario_noite"]
    enfrentou_ex_parceiro = analise["enfrentou_ex_parceiro"]
    violacoes_parceiro_ref = analise["violacoes_parceiro_ref"]
    repeticoes_adversarios_ref = analise["repeticoes_adversarios_ref"]
    pares_adversarios_repetidos: list[tuple[str, str]] = []
    pares_vistos: set[tuple[int, int]] = set()
    for item in repeticoes_adversarios_ref:
        jogador = item["jogador"]
        for adversario in item["adversarios"]:
            chave = tuple(sorted((jogador, adversario)))
            if chave in pares_vistos:
                continue
            pares_vistos.add(chave)
            pares_adversarios_repetidos.append((
                nomes_map.get(chave[0], str(chave[0])),
                nomes_map.get(chave[1], str(chave[1])),
            ))

    total_repeticoes_adversario = sum(item["quantidade"] for item in repeticoes_adversarios_ref)
    max_repeticoes_adversario = max((item["quantidade"] for item in repeticoes_adversarios_ref), default=0)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Repetiu parceiro na noite", len(repetiu_parceiro_noite))
    with c2:
        st.metric("Repetiu adversário na noite", len(repetiu_adversario_noite))
    with c3:
        st.metric("Enfrentou ex-parceiro na noite", len(enfrentou_ex_parceiro))

    c4, c5, c6 = st.columns(3)
    with c4:
        st.metric("Violação de parceiro da referência", len(violacoes_parceiro_ref))
    with c5:
        st.metric("Máx. adversários repetidos por jogador", max_repeticoes_adversario)
    with c6:
        st.metric("Total de repetições de adversários", total_repeticoes_adversario)

    if (
        not repetiu_parceiro_noite
        and not repetiu_adversario_noite
        and not enfrentou_ex_parceiro
        and not violacoes_parceiro_ref
    ):
        st.success("As regras obrigatórias do sorteio foram atendidas nesta comparação.")
    else:
        st.warning("Foram encontradas ocorrências que merecem revisão no sorteio.")

    st.divider()
    st.write("**Resumo das regras obrigatórias**")
    st.write(
        f"- Repetição de parceiro na mesma noite: **{len(repetiu_parceiro_noite)}**"
    )
    st.write(
        f"- Repetição de adversário na mesma noite: **{len(repetiu_adversario_noite)}**"
    )
    st.write(
        f"- Jogou contra alguém que já foi parceiro na noite: **{len(enfrentou_ex_parceiro)}**"
    )
    st.write(
        f"- Repetição de parceiro da rodada anterior: **{len(violacoes_parceiro_ref)}**"
    )

    st.divider()
    st.write("**Adversários repetidos da rodada anterior**")
    if not pares_adversarios_repetidos:
        st.info("Nenhum adversário repetido em relação às rodadas anteriores.")
    else:
        for nome_1, nome_2 in sorted(pares_adversarios_repetidos):
            st.write(f"- **{nome_1} × {nome_2}**")

    with st.expander("Detalhes por jogador"):
        for item in repeticoes_adversarios_ref:
            parceiros_violados = next(
                (entry["parceiros"] for entry in violacoes_parceiro_ref if entry["jogador"] == item["jogador"]),
                [],
            )
            st.write(
                f"- **{nomes_map.get(item['jogador'], str(item['jogador']))}** · "
                f"rodada de referência: **{item['rodada_ref'] or 'nenhuma'}** · "
                f"parceiros repetidos: "
                f"{', '.join(nomes_map.get(p, str(p)) for p in parceiros_violados) if parceiros_violados else 'nenhum'}"
                f" · adversários repetidos: "
                f"{', '.join(nomes_map.get(a, str(a)) for a in item['adversarios']) if item['adversarios'] else 'nenhum'}"
            )

    with st.expander("Ocorrências detalhadas das regras obrigatórias"):
        if repetiu_parceiro_noite:
            st.write("**Parceiros repetidos na mesma noite**")
            for item in repetiu_parceiro_noite:
                j1, j2 = item["jogadores"]
                st.write(
                    f"- {nomes_map.get(j1, str(j1))} / {nomes_map.get(j2, str(j2))} "
                    f"no jogo {item['rodada_interna']} · quadra {item['quadra']}"
                )
        if repetiu_adversario_noite:
            st.write("**Adversários repetidos na mesma noite**")
            for item in repetiu_adversario_noite:
                st.write(
                    f"- {nomes_map.get(item['jogador'], str(item['jogador']))} repetiu confronto com "
                    f"{nomes_map.get(item['adversario'], str(item['adversario']))} "
                    f"no jogo {item['rodada_interna']} · quadra {item['quadra']}"
                )
        if enfrentou_ex_parceiro:
            st.write("**Enfrentou alguém que já foi parceiro na mesma noite**")
            for item in enfrentou_ex_parceiro:
                st.write(
                    f"- {nomes_map.get(item['jogador'], str(item['jogador']))} enfrentou "
                    f"{nomes_map.get(item['outro'], str(item['outro']))} "
                    f"no jogo {item['rodada_interna']} · quadra {item['quadra']}"
                )
        if violacoes_parceiro_ref:
            st.write("**Parceiros repetidos da rodada anterior**")
            for item in violacoes_parceiro_ref:
                st.write(
                    f"- {nomes_map.get(item['jogador'], str(item['jogador']))} repetiu parceiro(s) da rodada anterior "
                    f"{item['rodada_ref']}: "
                    + ", ".join(nomes_map.get(p, str(p)) for p in item["parceiros"])
                )
        if (
            not repetiu_parceiro_noite
            and not repetiu_adversario_noite
            and not enfrentou_ex_parceiro
            and not violacoes_parceiro_ref
        ):
            st.info("Nenhuma ocorrência obrigatória encontrada.")
