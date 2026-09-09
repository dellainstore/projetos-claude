"""Envio de alertas pro Telegram — usado hoje só pelo monitoramento de
cotação do Motoqueiro (Financeiro > Motoqueiro > Monitoramento).

Como configurar:
  1. Crie o bot no Telegram falando com @BotFather (/newbot) e pegue o
     TELEGRAM_BOT_TOKEN gerado.
  2. Crie um grupo (ex: com os funcionários que pedem motoqueiro) e adicione
     o bot nele.
  3. Mande qualquer mensagem no grupo e abra no navegador:
       https://api.telegram.org/bot<TOKEN>/getUpdates
     O campo "message.chat.id" da resposta é o TELEGRAM_CHAT_ID (grupo
     costuma vir negativo, ex: -1001234567890 — copiar do jeito que vier).
  4. Colocar os dois no .env e `della restart admin`.
"""
import logging

import requests

from .config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)
TIMEOUT = 10


def configurado() -> bool:
    return bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)


def enviar_mensagem(texto: str) -> bool:
    """Manda uma mensagem pro chat/grupo configurado. Nunca levanta exceção
    — só loga o erro, porque uma falha de envio não pode travar o cron do
    monitoramento nem impedir de checar os outros monitoramentos da rodada."""
    if not configurado():
        logger.warning(
            "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID não configurados — mensagem não enviada: %s",
            texto[:80],
        )
        return False
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": texto},
            timeout=TIMEOUT,
        )
        if resp.status_code >= 400:
            logger.error("Telegram recusou o envio (%s): %s", resp.status_code, resp.text[:300])
            return False
        return True
    except Exception:
        logger.exception("Erro ao enviar mensagem pro Telegram")
        return False
