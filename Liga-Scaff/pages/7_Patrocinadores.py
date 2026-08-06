"""
Página de gestão de patrocinadores da Liga Quarta Scaff.
Upload de logos por temporada (oficial + apoiadores) — usados automaticamente
no PDF da planilha de jogos (aba Sorteio).
"""

import streamlit as st
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src import database as db, auth

auth.require_admin()

st.title("🏷️ Patrocinadores")
st.caption("Cadastrados por temporada — aparecem automaticamente no PDF da planilha de jogos.")

TIPOS_ACEITOS = ["png", "jpg", "jpeg"]


def _mime(arquivo) -> str:
    return arquivo.type or "image/png"


temporadas = db.list_temporadas()
if not temporadas:
    st.info("Crie uma temporada em **Jogadores** primeiro.")
    st.stop()

temporada = st.selectbox(
    "Temporada",
    options=temporadas,
    format_func=lambda t: t["nome"],
    index=next((i for i, t in enumerate(temporadas) if t["ativa"]), 0),
    key="patro_temporada",
)
tid = temporada["id"]

# ── Patrocinador Oficial ───────────────────────────────────────────────────────
st.divider()
st.subheader("⭐ Patrocinador Oficial")
st.caption("Aparece maior, do lado direito da planilha, com Instagram e QR Code (se cadastrado).")

oficial = db.get_patrocinador_oficial(tid)
editando_oficial = st.session_state.get("editando_patrocinador_oficial", False)

if oficial and not editando_oficial:
    with st.container(border=True):
        c1, c2 = st.columns([1, 3])
        with c1:
            st.image(oficial["logo_blob"], width=140)
            if oficial["qrcode_blob"]:
                st.image(oficial["qrcode_blob"], width=90, caption="QR Code")
        with c2:
            st.write(f"**{oficial['nome']}**")
            if oficial["instagram"]:
                st.caption(f"📷 {oficial['instagram']}")
            cb1, cb2, cb3 = st.columns(3)
            with cb1:
                if st.button("✏️ Editar", key="edit_oficial", use_container_width=True):
                    st.session_state["editando_patrocinador_oficial"] = True
                    st.rerun()
            with cb2:
                if st.button("⬇️ Rebaixar", key="rebaixar_oficial", use_container_width=True,
                             help="Torna este patrocinador um apoiador"):
                    db.update_patrocinador(oficial["id"], oficial["nome"], oficial["instagram"], "apoiador")
                    st.success("Rebaixado para apoiador.")
                    st.rerun()
            with cb3:
                if st.button("🗑️ Excluir", key="del_oficial", use_container_width=True):
                    db.delete_patrocinador(oficial["id"])
                    st.success("Patrocinador oficial removido.")
                    st.rerun()

elif oficial and editando_oficial:
    st.write(f"Editando: **{oficial['nome']}**")
    with st.form("form_editar_oficial"):
        nome = st.text_input("Nome", value=oficial["nome"])
        instagram = st.text_input("Instagram", value=oficial["instagram"] or "", placeholder="@usuario ou link")
        nova_logo = st.file_uploader("Nova logo (opcional — mantém a atual se não enviar)", type=TIPOS_ACEITOS)
        novo_qr = st.file_uploader("Novo QR Code (opcional)", type=TIPOS_ACEITOS)
        remover_qr = st.checkbox("Remover QR Code atual") if oficial["qrcode_blob"] else False
        fa, fb = st.columns(2)
        with fa:
            salvar = st.form_submit_button("💾 Salvar", use_container_width=True, type="primary")
        with fb:
            cancelar = st.form_submit_button("✕ Cancelar", use_container_width=True)

    if salvar and nome.strip():
        db.update_patrocinador(
            oficial["id"], nome.strip(), instagram.strip(), "oficial",
            logo_blob=nova_logo.getvalue() if nova_logo else None,
            logo_mime=_mime(nova_logo) if nova_logo else None,
            qrcode_blob=novo_qr.getvalue() if novo_qr else None,
            qrcode_mime=_mime(novo_qr) if novo_qr else None,
            remover_qrcode=remover_qr,
        )
        st.session_state.pop("editando_patrocinador_oficial", None)
        st.success("Patrocinador oficial atualizado!")
        st.rerun()
    if cancelar:
        st.session_state.pop("editando_patrocinador_oficial", None)
        st.rerun()

else:
    st.info("Nenhum patrocinador oficial cadastrado nesta temporada.")
    with st.form("form_novo_oficial", clear_on_submit=True):
        nome = st.text_input("Nome *")
        instagram = st.text_input("Instagram", placeholder="@usuario ou link")
        logo = st.file_uploader("Logo *", type=TIPOS_ACEITOS)
        qrcode = st.file_uploader("QR Code (opcional)", type=TIPOS_ACEITOS)
        if st.form_submit_button("Cadastrar como Oficial", use_container_width=True, type="primary"):
            if not nome.strip():
                st.error("Nome é obrigatório.")
            elif not logo:
                st.error("A logo é obrigatória.")
            else:
                novo_id = db.create_patrocinador(
                    tid, "oficial", nome.strip(),
                    logo.getvalue(), _mime(logo),
                    instagram=instagram.strip(),
                    qrcode_blob=qrcode.getvalue() if qrcode else None,
                    qrcode_mime=_mime(qrcode) if qrcode else None,
                )
                if novo_id == -1:
                    st.error("Já existe um patrocinador oficial nesta temporada. Rebaixe-o ou exclua-o antes.")
                else:
                    st.success(f"**{nome.strip()}** cadastrado como patrocinador oficial!")
                    st.rerun()

# ── Apoiadores ──────────────────────────────────────────────────────────────────
st.divider()
st.subheader("🤝 Apoiadores")
st.caption("Logos menores, do lado esquerdo da planilha.")

apoiadores = db.list_patrocinadores(tid, tipo="apoiador")
editando_apoiador_id = st.session_state.get("editando_apoiador_id")

if apoiadores:
    for p in apoiadores:
        if editando_apoiador_id == p["id"]:
            with st.container(border=True):
                st.write(f"Editando: **{p['nome']}**")
                with st.form(f"form_editar_apoiador_{p['id']}"):
                    nome = st.text_input("Nome", value=p["nome"])
                    nova_logo = st.file_uploader(
                        "Nova logo (opcional — mantém a atual se não enviar)", type=TIPOS_ACEITOS
                    )
                    fa, fb = st.columns(2)
                    with fa:
                        salvar = st.form_submit_button("💾 Salvar", use_container_width=True, type="primary")
                    with fb:
                        cancelar = st.form_submit_button("✕ Cancelar", use_container_width=True)
                if salvar and nome.strip():
                    db.update_patrocinador(
                        p["id"], nome.strip(), None, "apoiador",
                        logo_blob=nova_logo.getvalue() if nova_logo else None,
                        logo_mime=_mime(nova_logo) if nova_logo else None,
                    )
                    st.session_state.pop("editando_apoiador_id", None)
                    st.success("Apoiador atualizado!")
                    st.rerun()
                if cancelar:
                    st.session_state.pop("editando_apoiador_id", None)
                    st.rerun()
        else:
            with st.container(border=True):
                c1, c2, c3, c4, c5 = st.columns([1, 3, 1, 1, 1])
                with c1:
                    st.image(p["logo_blob"], width=90)
                with c2:
                    st.write(f"**{p['nome']}**")
                with c3:
                    if st.button("⭐", key=f"promover_{p['id']}", help="Tornar Oficial"):
                        if db.get_patrocinador_oficial(tid):
                            st.error(
                                "Já existe um patrocinador oficial nesta temporada. "
                                "Rebaixe-o ou exclua-o antes de promover este apoiador."
                            )
                        else:
                            db.update_patrocinador(p["id"], p["nome"], p["instagram"], "oficial")
                            st.success(f"**{p['nome']}** agora é o patrocinador oficial!")
                            st.rerun()
                with c4:
                    if st.button("✏️", key=f"edit_apoiador_{p['id']}", help="Editar"):
                        st.session_state["editando_apoiador_id"] = p["id"]
                        st.rerun()
                with c5:
                    if st.button("🗑️", key=f"del_apoiador_{p['id']}", help="Excluir"):
                        st.session_state["confirmar_del_apoiador"] = p["id"]
                        st.rerun()

    confirmar_id = st.session_state.get("confirmar_del_apoiador")
    if confirmar_id:
        p_conf = db.get_patrocinador(confirmar_id)
        if p_conf:
            st.warning(f"⚠️ Excluir o apoiador **{p_conf['nome']}**?")
            ca, cb = st.columns(2)
            with ca:
                if st.button("Sim, excluir", type="primary", use_container_width=True, key="conf_del_apoiador_sim"):
                    db.delete_patrocinador(confirmar_id)
                    st.session_state.pop("confirmar_del_apoiador", None)
                    st.success("Apoiador excluído.")
                    st.rerun()
            with cb:
                if st.button("Cancelar", use_container_width=True, key="conf_del_apoiador_cancelar"):
                    st.session_state.pop("confirmar_del_apoiador", None)
                    st.rerun()
else:
    st.info("Nenhum apoiador cadastrado nesta temporada.")

st.markdown("##### Novo Apoiador")
with st.form("form_novo_apoiador", clear_on_submit=True):
    nome = st.text_input("Nome *")
    logo = st.file_uploader("Logo *", type=TIPOS_ACEITOS)
    if st.form_submit_button("Adicionar Apoiador", use_container_width=True, type="primary"):
        if not nome.strip():
            st.error("Nome é obrigatório.")
        elif not logo:
            st.error("A logo é obrigatória.")
        else:
            db.create_patrocinador(tid, "apoiador", nome.strip(), logo.getvalue(), _mime(logo))
            st.success(f"**{nome.strip()}** adicionado como apoiador!")
            st.rerun()
