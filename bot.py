import asyncio
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import TELEGRAM_TOKEN, TELEGRAM_ALLOWED_USER_ID
from actual_client import fetch_payees, insert_transaction
from payee_matcher import match_payee, parse_message

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache de payees
_payees_cache: list[dict] = []
_cache_ts: datetime | None = None
CACHE_TTL_SECONDS = 3600

async def get_payees() -> list[dict]:
    global _payees_cache, _cache_ts
    now = datetime.now()
    if not _cache_ts or (now - _cache_ts).seconds > CACHE_TTL_SECONDS:
        _payees_cache = await fetch_payees()
        _cache_ts = now
        logger.info(f"Payees cache refreshed: {len(_payees_cache)} payees")
    return _payees_cache

def is_allowed(update: Update) -> bool:
    return update.effective_user.id == TELEGRAM_ALLOWED_USER_ID

# ── Handlers ──────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    await update.message.reply_text(
        "👋 Bot de Actual Budget listo.\n\n"
        "Envía una transacción así:\n"
        "`starbucks 80`\n"
        "`netflix 120`\n"
        "`uber 145`",
        parse_mode="Markdown"
    )

async def refresh_payees(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return
    global _cache_ts
    _cache_ts = None
    await get_payees()
    await update.message.reply_text("✅ Lista de payees actualizada.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update):
        return

    text = update.message.text.strip()
    parsed = parse_message(text)

    if not parsed:
        await update.message.reply_text(
            "No entendí. Formato: `payee monto`\nEjemplo: `starbucks 80`",
            parse_mode="Markdown"
        )
        return

    payee_query, amount = parsed
    payees = await get_payees()
    match = match_payee(payee_query, payees)

    if match["type"] == "auto":
        # Insertar directo
        await _insert_and_confirm(update, match["payee"], amount)

    elif match["type"] == "suggest":
        # Mostrar opciones
        keyboard = [
            [InlineKeyboardButton(opt, callback_data=f"pay|{opt}|{amount}")]
            for opt in match["options"]
        ]
        keyboard.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancel")])
        await update.message.reply_text(
            f"¿Cuál payee quisiste decir para *{payee_query}*?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:
        # No encontrado — preguntar si crear
        keyboard = [
            [InlineKeyboardButton(f"✅ Crear \"{payee_query.title()}\"", callback_data=f"new|{payee_query.title()}|{amount}")],
            [InlineKeyboardButton("❌ Cancelar", callback_data="cancel")]
        ]
        await update.message.reply_text(
            f"No encontré *{payee_query}* en tus payees.\n¿Quieres crearlo?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Cancelado.")
        return

    parts = query.data.split("|")
    action = parts[0]
    payee = parts[1]
    amount = float(parts[2])

    if action in ("pay", "new"):
        await query.edit_message_text(f"⏳ Insertando...")
        await _insert_and_confirm_query(query, payee, amount)

async def _insert_and_confirm(update: Update, payee: str, amount: float):
    try:
        await insert_transaction(payee, amount)
        await update.message.reply_text(f"✅ *{payee}* ${amount:,.2f}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error inserting transaction: {e}")
        await update.message.reply_text(f"❌ Error al insertar: {e}")

async def _insert_and_confirm_query(query, payee: str, amount: float):
    try:
        await insert_transaction(payee, amount)
        await query.edit_message_text(f"✅ *{payee}* ${amount:,.2f}", parse_mode="Markdown")
    except Exception as e:
        logger.error(f"Error inserting transaction: {e}")
        await query.edit_message_text(f"❌ Error al insertar: {e}")

def create_app() -> Application:
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("refresh", refresh_payees))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    return app
