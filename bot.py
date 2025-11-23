import os
import asyncio
from typing import Set

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from checker import Checker

TOKEN = "8513216536:AAE2O8g-yC3zCVXl_Q6z4hWwL4WqM-MnQHQ"
ALLOWED_CHAT_ID = os.environ.get("ALLOWED_CHAT_ID", "6522490688")

subscribers: Set[int] = set()
checker = Checker()


def allowed(chat_id: int) -> bool:
    if not ALLOWED_CHAT_ID:
        return True
    try:
        return chat_id == int(ALLOWED_CHAT_ID)
    except Exception:
        return False


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        await update.message.reply_text("Access denied.")
        return
    subscribers.add(chat_id)
    await update.message.reply_text(
        "Control panel:", reply_markup=main_keyboard(checker.is_running())
    )


def main_keyboard(is_running: bool) -> InlineKeyboardMarkup:
    start_btn = InlineKeyboardButton("Start", callback_data="RUN")
    stop_btn = InlineKeyboardButton("Stop", callback_data="STOP")
    status_btn = InlineKeyboardButton("Status", callback_data="STATUS")
    latest_btn = InlineKeyboardButton("Latest", callback_data="LATEST")
    # If running, show Stop first; else Start first
    if is_running:
        row1 = [stop_btn, status_btn]
    else:
        row1 = [start_btn, status_btn]
    row2 = [latest_btn]
    return InlineKeyboardMarkup([row1, row2])


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    # try both attributes for compatibility
    chat_id = getattr(query.message.chat, "id", None) if query and query.message else None
    if chat_id is None:
        # fallback to effective_chat
        chat_id = update.effective_chat.id if update.effective_chat else None
    data = (query.data or "") if query else ""

    # Handle reveal before generic acknowledgement (so we can show_alert)
    if data.startswith("REVEAL:"):
        addr = data.split(":", 1)[1]
        if not allowed(chat_id):
            await query.answer(text="Access denied.", show_alert=True)
            return
        s = checker.snapshot()
        recent = s.get("recent_found", [])
        priv = None
        for a, p, _sol, _ts in recent:
            if a == addr:
                priv = p
                break
        if priv:
            await query.answer(text=priv, show_alert=True)
        else:
            await query.answer(text="Private key not available (stale).", show_alert=True)
        return

    if data.startswith("EXPORT:"):
        addr = data.split(":", 1)[1]
        if not allowed(chat_id):
            await query.answer(text="Access denied.", show_alert=True)
            return
        s = checker.snapshot()
        recent = s.get("recent_found", [])
        priv = None
        for a, p, _sol, _ts in recent:
            if a == addr:
                priv = p
                break
        if priv:
            user_id = query.from_user.id
            try:
                await context.bot.send_message(chat_id=user_id, text=f"Private key for {addr}:\n{priv}")
                await query.answer(text="Private key sent to your DM.", show_alert=True)
            except Exception:
                await query.answer(text="Failed to send DM. Make sure you started a chat with the bot.", show_alert=True)
        else:
            await query.answer(text="Private key not available (stale).", show_alert=True)
        return

    # Acknowledge normal buttons
    await query.answer()
    if not allowed(chat_id):
        await query.edit_message_text("Access denied.")
        return

    # Standard actions
    if data == "RUN":
        if checker.is_running():
            await query.edit_message_text("Checker already running.", reply_markup=main_keyboard(True))
            return
        await checker.start()
        await query.edit_message_text("Checker started.", reply_markup=main_keyboard(True))
    elif data == "STOP":
        if not checker.is_running():
            await query.edit_message_text("Checker is not running.", reply_markup=main_keyboard(False))
            return
        await checker.stop()
        await query.edit_message_text("Checker stopped.", reply_markup=main_keyboard(False))
    elif data == "STATUS":
        s = checker.snapshot()
        uptime = s.get("uptime_s", 1)
        checks_per_s = s.get("checked", 0) / max(1, uptime)
        current_priv = s.get("current_priv", "-")
        redacted = f"{current_priv[:6]}...{current_priv[-6:]}" if current_priv and len(current_priv) > 12 else current_priv
        html = (
            f"<b>🟢 Checker Status</b>\n\n"
            f"<b>Running:</b> {'Yes' if checker.is_running() else 'No'}\n"
            f"<b>Checked:</b> {s.get('checked',0)} ({checks_per_s:.2f}/s)\n"
            f"<b>Found:</b> {s.get('found',0)}\n"
            f"<b>API Errors:</b> {s.get('api_errors',0)}\n"
            f"<b>Uptime:</b> {fmt_uptime(uptime)}\n"
            f"<b>Batch size:</b> {checker.batch_size}   <b>Concurrency:</b> {checker._concurrency}\n"
            f"<b>Current private (redacted):</b> <code>{redacted}</code>\n"
        )
        await query.edit_message_text(html, reply_markup=main_keyboard(checker.is_running()), parse_mode="HTML")
    elif data == "LATEST":
        s = checker.snapshot()
        recent = s.get("recent_found", [])[-10:]
        if not recent:
            await query.edit_message_text("No recent found wallets.", reply_markup=main_keyboard(checker.is_running()))
            return
        lines = ["<b>Latest found wallets:</b>\n\n"]
        kb_rows = []
        for i, (addr, priv, sol, ts) in enumerate(recent, start=1):
            redacted_priv = f"{priv[:6]}...{priv[-6:]}" if priv and len(priv) > 12 else priv
            lines.append(
                f"<b>{i}.</b>\n"
                f"<pre>Address: {addr}</pre>\n"
                f"<pre>Private: {redacted_priv}</pre>\n"
                f"<b>Balance:</b> <code>{sol:.9f} SOL</code>\n"
                f"<i>{ts}</i>\n"
                f"<i>────────────</i>\n\n"
            )
            # add a row of buttons for this item (Show / Export)
            kb_rows.append([
                InlineKeyboardButton("Show", callback_data=f"REVEAL:{addr}"),
                InlineKeyboardButton("Export (DM)", callback_data=f"EXPORT:{addr}"),
            ])

        kb = InlineKeyboardMarkup(kb_rows)
        await query.edit_message_text("".join(lines), reply_markup=kb, parse_mode="HTML")


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        await update.message.reply_text("Access denied.")
        return
    subscribers.add(chat_id)
    if checker.is_running():
        await update.message.reply_text("Checker already running.", reply_markup=main_keyboard(True))
        return
    await checker.start()
    await update.message.reply_text("Checker started.", reply_markup=main_keyboard(True))


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        await update.message.reply_text("Access denied.")
        return
    if not checker.is_running():
        await update.message.reply_text("Checker is not running.", reply_markup=main_keyboard(False))
        return
    await checker.stop()
    await update.message.reply_text("Checker stopped.", reply_markup=main_keyboard(False))


def fmt_uptime(seconds: int) -> str:
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        await update.message.reply_text("Access denied.")
        return
    s = checker.snapshot()
    txt = (
        f"Running: {checker.is_running()}\n"
        f"Checked: {s['checked']}\n"
        f"Found: {s['found']}\n"
        f"API Errors: {s['api_errors']}\n"
        f"Uptime: {fmt_uptime(s['uptime_s'])}\n"
    )
    await update.message.reply_text(txt, reply_markup=main_keyboard(checker.is_running()))


async def cmd_latest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    if not allowed(chat_id):
        await update.message.reply_text("Access denied.")
        return
    s = checker.snapshot()
    recent = s.get("recent_found", [])[-10:]
    if not recent:
        await update.message.reply_text("No recent found wallets.")
        return
    lines = ["<b>Latest found wallets:</b>\n\n"]
    kb_rows = []
    for i, (addr, priv, sol, ts) in enumerate(recent, start=1):
        redacted_priv = f"{priv[:6]}...{priv[-6:]}" if priv and len(priv) > 12 else priv
        lines.append(
            f"<b>{i}.</b>\n"
            f"<pre>Address: {addr}</pre>\n"
            f"<pre>Private: {redacted_priv}</pre>\n"
            f"<b>Balance:</b> <code>{sol:.9f} SOL</code>\n"
            f"<i>{ts}</i>\n"
            f"<i>────────────</i>\n\n"
        )
        kb_rows.append([
            InlineKeyboardButton("Show", callback_data=f"REVEAL:{addr}"),
            InlineKeyboardButton("Export (DM)", callback_data=f"EXPORT:{addr}"),
        ])

    kb = InlineKeyboardMarkup(kb_rows)
    await update.message.reply_text("".join(lines), reply_markup=kb, parse_mode="HTML")


async def notify_found(addr: str, priv: str, sol: float, ts: str, app: Application) -> None:
    if not subscribers:
        return
    # Pretty HTML-formatted message for found wallets, but redact private key by default.
    redacted_priv = f"{priv[:6]}...{priv[-6:]}" if priv and len(priv) > 12 else priv
    html = (
        f"<b>WALLET FOUND!</b>\n"
        f"\n"
        f"<b>Address:</b> <code>{addr}</code>\n"
        f"\n"
        f"<b>Private key:</b> <code>{redacted_priv}</code>\n"
        f"\n"
        f"<b>Balance:</b> <b>{sol:.9f} SOL</b>\n"
        f"\n"
        f"<i>{ts}</i>"
    )
    # Inline buttons: Show (alert) and Export (DM)
    kb = InlineKeyboardMarkup(
        [[
            InlineKeyboardButton("Show", callback_data=f"REVEAL:{addr}"),
            InlineKeyboardButton("Export (DM)", callback_data=f"EXPORT:{addr}"),
        ]]
    )
    for chat_id in list(subscribers):
        try:
            await app.bot.send_message(
                chat_id=chat_id, text=html, parse_mode="HTML", reply_markup=kb
            )
        except Exception:
            pass


async def main() -> None:
    """Async entrypoint that initializes and starts the Application in one event loop.

    This avoids using `asyncio.run()` to initialize the app separately and then calling
    `run_polling()`, which creates its own loop and can lead to "Event loop is closed"
    errors when libraries (httpx/httpcore) try to close transports tied to a different
    loop.
    """
    if not TOKEN:
        raise RuntimeError("TELEGRAM_TOKEN env var is required")

    app = Application.builder().token(TOKEN).build()

    async def on_found_wrapper(addr: str, priv: str, sol: float, ts: str) -> None:
        await notify_found(addr, priv, sol, ts, app)

    checker._on_found = on_found_wrapper

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("run", cmd_run))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("latest", cmd_latest))
    app.add_handler(CallbackQueryHandler(on_button))

    # Initialize and start the application inside this event loop
    await app.initialize()
    try:
        await app.start()
        # start the updater's polling (non-blocking)
        await app.updater.start_polling()

        # Keep running until cancelled
        await asyncio.Event().wait()
    finally:
        # Graceful shutdown
        try:
            await app.updater.stop()
        except Exception:
            pass
        try:
            await app.stop()
        except Exception:
            pass
        try:
            await app.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    # Run the async main() in a single event loop to avoid mixing loops.
    asyncio.run(main())
