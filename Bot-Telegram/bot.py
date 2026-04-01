import os
import logging
from dotenv import load_dotenv
import anthropic
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ALLOWED_USER_IDS = os.getenv("ALLOWED_USER_IDS", "")

allowed_ids: set[int] = set()
if ALLOWED_USER_IDS.strip():
    allowed_ids = {int(uid.strip()) for uid in ALLOWED_USER_IDS.split(",") if uid.strip()}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# Histórico por chat_id: lista de mensagens no formato da API Anthropic
historico: dict[int, list[dict]] = {}


def is_allowed(user_id: int) -> bool:
    if not allowed_ids:
        return True
    return user_id in allowed_ids


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("Acesso não autorizado.")
        return
    await update.message.reply_text(
        f"Olá, {user.first_name}! Sou o assistente Claude da Della Instore.\n"
        "Pode me perguntar o que quiser. Use /clear para reiniciar a conversa."
    )


async def clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("Acesso não autorizado.")
        return
    historico.pop(update.effective_chat.id, None)
    await update.message.reply_text("Conversa reiniciada.")


async def responder(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_allowed(user.id):
        await update.message.reply_text("Acesso não autorizado.")
        return

    chat_id = update.effective_chat.id
    texto = update.message.text

    if chat_id not in historico:
        historico[chat_id] = []

    historico[chat_id].append({"role": "user", "content": texto})

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    try:
        resposta = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=(
                "Você é um assistente inteligente da Della Instore. "
                "Responda sempre em português, de forma clara e objetiva."
            ),
            messages=historico[chat_id],
        )
        conteudo = resposta.content[0].text
        historico[chat_id].append({"role": "assistant", "content": conteudo})
        await update.message.reply_text(conteudo)
    except Exception as e:
        logger.error("Erro ao chamar a API do Claude: %s", e)
        await update.message.reply_text("Ocorreu um erro ao processar sua mensagem. Tente novamente.")


def main() -> None:
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, responder))
    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    main()
