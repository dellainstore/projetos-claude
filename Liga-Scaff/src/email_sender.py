"""
Envio de e-mail com PDFs do ranking da Liga Quarta Scaff.
Usa a API HTTP do Resend (resend.com) — sem dependência de porta SMTP.
"""

import os
import base64
import json
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

RESEND_API_URL = "https://api.resend.com/emails"


def _get_config() -> dict:
    return {
        "api_key": os.getenv("RESEND_API_KEY", ""),
        "from_email": os.getenv("RESEND_FROM", ""),
        "recipients": [
            e.strip()
            for e in os.getenv("EMAIL_RECIPIENTS", "").split(",")
            if e.strip()
        ],
    }


def enviar_ranking(
    pdfs: list[tuple[bytes, str]],
    rodada_num: int,
    temporada_nome: str,
    beer_list: list[str],
) -> tuple[bool, str]:
    """
    Envia os PDFs do ranking por e-mail via Resend API.

    Args:
        pdfs: lista de (bytes_do_pdf, nome_do_arquivo)
        rodada_num: número da rodada
        temporada_nome: nome da temporada
        beer_list: nomes de quem deve cerveja

    Returns:
        (sucesso, mensagem_erro)
    """
    config = _get_config()

    if not config["api_key"]:
        return False, "RESEND_API_KEY não configurada no .env"
    if not config["from_email"]:
        return False, "RESEND_FROM não configurado no .env"
    if not config["recipients"]:
        return False, "Nenhum destinatário configurado em EMAIL_RECIPIENTS no .env"

    beer_texto = ""
    if beer_list:
        beer_texto = f"\n🍺 Devem cerveja nessa rodada: {', '.join(beer_list)}\n"

    corpo_html = f"""
<p><strong>Liga Quarta Scaff — {temporada_nome}</strong></p>
<p>Ranking atualizado após a <strong>Rodada {rodada_num}</strong>.</p>
{f'<p>🍺 <strong>Devem cerveja nessa rodada:</strong> {", ".join(beer_list)}</p>' if beer_list else ''}
<p>Confira os PDFs em anexo.</p>
<hr/>
<small>Sistema Liga Quarta Scaff</small>
"""

    anexos = []
    for pdf_bytes, filename in pdfs:
        anexos.append({
            "filename": filename,
            "content": base64.b64encode(pdf_bytes).decode("utf-8"),
        })

    payload = {
        "from": config["from_email"],
        "to": config["recipients"],
        "subject": f"🎾 Liga Quarta Scaff — Ranking Rodada {rodada_num}",
        "html": corpo_html,
        "attachments": anexos,
    }

    try:
        resp = requests.post(
            RESEND_API_URL,
            json=payload,
            headers={"Authorization": f"Bearer {config['api_key']}"},
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("id"):
                return True, ""
            return False, f"Resposta inesperada: {resp.text}"
        try:
            detalhe = resp.json().get("message", resp.text)
        except Exception:
            detalhe = resp.text
        return False, f"Erro HTTP {resp.status_code}: {detalhe}"

    except Exception as e:
        return False, f"Erro ao enviar e-mail: {e}"


def smtp_configurado() -> bool:
    """Retorna True se a API Resend estiver configurada."""
    config = _get_config()
    return bool(config["api_key"] and config["from_email"] and config["recipients"])
