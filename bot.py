import logging
import uuid
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from config import TELEGRAM_TOKEN, TELEGRAM_ALLOWED_USER_ID, ACTUAL_ACCOUNT_DEFAULT
from actual_client import fetch_payees, fetch_accounts, insert_transaction, delete_transaction
from payee_matcher import match_payee, parse_message_with_account

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Caches
_payees_cache: list[dict] = []
_payees_cache_ts: datetime | None = None
_accounts_cache: list[dict] = []
_active_account: dict | None = None
CACHE_TTL_SECONDS = 3600

# Pending callbacks
_pending_callbacks: dict[str, dict] = {}

# Last inserted transaction
_last_transaction: dict[str, dict] = {}

def store_callback(data: dict) -> str:
    key = str(uuid.uuid4())[:8]
    _pending_callbacks[key] = data
    return key

async def get_payees() -> list[dict]:
    global _payees_cache, _payees_cache_ts
    now = datetime.now()
    if not _payees_cache_ts or (now - _payees_cache_ts).seconds > CACHE_TTL_SECONDS:
        _payees_cache = await fetch_payees()
        _payees_cache_ts = now
        logger.info(f"Payees cache refreshed: {len(_payees_cache)} payees")
    return _payees_cache

async def get_accounts() -> list[dict]:
    global _accounts_cache, _active_account
    if not _accounts_cache:
        _accounts_cache = await fetch_accounts()
        default_name = ACTUAL_ACCOUNT_DEFAULT.lower()
        _active_account = next(
            (a for a in _accounts_cache if a["name"].lower() == default_name),
            _accounts_cache[0] if _accounts_cache else None
        )
        logger.info(f"Accounts loaded: {[a['name'] for a in _accounts_cache]}, default: {_active_account['name']}")
    return _accounts_cache

def fuzzy_resolve_account(query: str, accounts: list[dict]) -> dict | None:
    from rapidfuzz import process, fuzz
    try:
        idx = int(query) - 1
        if 0 <= idx < len(accounts):
            return accounts[idx]
    except ValueError:
        pass
    names = [a["name"] for a in accounts]
    result = process.extractOne(query, names, scorer=fuzz.WRatio)
    if result and result[1] >= 60:
        return next(a for a in accounts if a["name"] == result[0])
    return None

def is_allowed(update: Update) -> bool:
    return update.effective_user.id == TELEGRAM_ALLOWED_USER_ID

# ── Handlers ──────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    await get_accounts()
    await update.message.reply_text(
        "👋 *Actual Budget Bot*\n\n"
        "Format: `payee amount [account] [date]`\n\n"
        "Examples:\n"
        "`starbucks 80` — expense\n"
        "`payroll +15000` — income\n"
        "`netflix 120 credit`\n"
        "`uber 145 yesterday`\n"
        "`rent 12000 debit monday`\n\n"
        f"Active account: *{_active_account['name']}*\n\n"
        "Commands:\n"
        "/account — view or change active account\n"
        "/accounts — list available accounts\n"
        "/refresh — refresh payees cache",
        parse_mode="Markdown"
    )

async def accounts_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    accounts = await get_accounts()
    lines = "\n".join(f"{i+1}. {a['name']}" for i, a in enumerate(accounts))
    await update.message.reply_text(
        f"*Available accounts:*\n{lines}\n\n"
        f"Active: *{_active_account['name']}*",
        parse_mode="Markdown"
    )

async def account_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    global _active_account
    accounts = await get_accounts()

    if not context.args:
        lines = "\n".join(f"{i+1}. {a['name']}" for i, a in enumerate(accounts))
        await update.message.reply_text(
            f"Active account: *{_active_account['name']}*\n\n"
            f"*Available:*\n{lines}\n\n"
            "To change: `/account 1` or `/account <name>`",
            parse_mode="Markdown"
        )
        return

    query = " ".join(context.args)
    account = fuzzy_resolve_account(query, accounts)
    if not account:
        await update.message.reply_text(f"❌ Account `{query}` not found.", parse_mode="Markdown")
        return

    _active_account = account
    await update.message.reply_text(f"✅ Active account: *{account['name']}*", parse_mode="Markdown")

async def refresh_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    global _payees_cache_ts
    _payees_cache_ts = None
    await get_payees()
    await update.message.reply_text("✅ Payees refreshed.")

async def undo_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return
    user_id = str(update.effective_user.id)
    last = _last_transaction.get(user_id)

    if not last or not last.get("id"):
        await update.message.reply_text("Nothing to undo.")
        return

    success = await delete_transaction(last["id"])
    if success:
        sign = "+" if last["is_income"] else "-"
        _last_transaction.pop(user_id)
        await update.message.reply_text(
            f"↩️ Undone: *{last['payee']}* {sign}${last['amount']:,.2f}\n_{last['account_name']}_",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text("❌ Failed to undo. Transaction may have already been deleted.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_allowed(update): return

    text = update.message.text.strip()
    accounts = await get_accounts()
    parsed = parse_message_with_account(text, accounts)

    if not parsed:
        await update.message.reply_text(
            "Didn't understand. Format: `payee amount [account] [date]`\nExample: `starbucks 80`",
            parse_mode="Markdown"
        )
        return

    payee_query, amount, account_override, date_override, is_income = parsed

    if account_override:
        account = fuzzy_resolve_account(account_override, accounts)
        if not account:
            await update.message.reply_text(
                f"❌ Account `{account_override}` not found.",
                parse_mode="Markdown"
            )
            return
    else:
        account = _active_account

    payees = await get_payees()
    match = match_payee(payee_query, payees)

    if match["type"] == "auto":
        await _insert_and_confirm(update, match["payee"], amount, account, date_override, is_income)

    elif match["type"] == "suggest":
        keyboard = []
        for opt in match["options"]:
            key = store_callback({
                "action": "pay", "payee": opt, "amount": amount,
                "account": account, "date": date_override, "is_income": is_income
            })
            keyboard.append([InlineKeyboardButton(opt, callback_data=key)])
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel")])
        await update.message.reply_text(
            f"Which payee for *{payee_query}*?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

    else:
        key = store_callback({
            "action": "new", "payee": payee_query.title(), "amount": amount,
            "account": account, "date": date_override, "is_income": is_income
        })
        keyboard = [
            [InlineKeyboardButton(f"✅ Create \"{payee_query.title()}\"", callback_data=key)],
            [InlineKeyboardButton("❌ Cancel", callback_data="cancel")]
        ]
        await update.message.reply_text(
            f"Payee *{payee_query}* not found. Create it?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancel":
        await query.edit_message_text("❌ Cancelled.")
        return

    data = _pending_callbacks.pop(query.data, None)
    if not data:
        await query.edit_message_text("❌ Expired, please try again.")
        return

    await query.edit_message_text("⏳ Inserting...")
    try:
        tx_id = await insert_transaction(
            data["payee"], data["amount"], data["account"]["id"],
            data.get("date"), data.get("is_income", False)
        )
        _last_transaction[str(query.from_user.id)] = {
            "id": tx_id,
            "account_id": data["account"]["id"],
            "payee": data["payee"],
            "amount": data["amount"],
            "account_name": data["account"]["name"],
            "is_income": data.get("is_income", False)
        }
        date_label = f" · _{data['date']}_" if data.get("date") else ""
        sign = "+" if data.get("is_income") else "-"
        await query.edit_message_text(
            f"✅ *{data['payee']}* {sign}${data['amount']:,.2f}\n_{data['account']['name']}{date_label}_",
            parse_mode="Markdown"
        )
    except Exception as e:
        await query.edit_message_text(f"❌ Error: {e}")

async def _insert_and_confirm(
    update: Update, payee: str, amount: float,
    account: dict, tx_date: str | None = None, is_income: bool = False
):
    try:
        tx_id = await insert_transaction(payee, amount, account["id"], tx_date, is_income)
        _last_transaction[str(update.effective_user.id)] = {
            "id": tx_id,
            "account_id": account["id"],
            "payee": payee,
            "amount": amount,
            "account_name": account["name"],
            "is_income": is_income
        }
        date_label = f" · _{tx_date}_" if tx_date else ""
        sign = "+" if is_income else "-"
        await update.message.reply_text(
            f"✅ *{payee}* {sign}${amount:,.2f}\n_{account['name']}{date_label}_",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error inserting: {e}")
        await update.message.reply_text(f"❌ Error: {e}")

async def _post_init(application):
    await application.bot.set_my_commands([
        ("start", "Show usage instructions"),
        ("account", "View or change active account"),
        ("accounts", "List available accounts"),
        ("refresh", "Refresh payees cache"),
        ("undo", "Undo the last added transaction"),
    ])

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("account", account_cmd))
    app.add_handler(CommandHandler("accounts", accounts_cmd))
    app.add_handler(CommandHandler("refresh", refresh_cmd))
    app.add_handler(CommandHandler("undo", undo_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()

if __name__ == "__main__":
    main()
