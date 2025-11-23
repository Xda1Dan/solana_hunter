import os
import json
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Configuration ---
TOKEN = "8513216536:AAE2O8g-yC3zCVXl_Q6z4hWwL4WqM-MnQHQ"
ALLOWED_USER_ID = 6522490688  # Replace with your ID from bot.py
SCRAPER_STATS_FILE = "scraper_stats.json"
MATCHER_STATS_FILE = "matcher_stats.json"
FOUND_FILE = "found.txt"

# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- State ---
last_found_size = 0

def read_json(path):
    try:
        if os.path.exists(path):
            with open(path, "r") as f:
                return json.load(f)
    except Exception:
        pass
    return {}

def get_status_text():
    scraper = read_json(SCRAPER_STATS_FILE)
    matcher = read_json(MATCHER_STATS_FILE)
    
    s_speed = scraper.get("speed_blocks_per_sec", 0)
    s_found = scraper.get("high_value_found", 0)
    s_slot = scraper.get("current_slot", 0)
    
    m_speed = matcher.get("speed_keys_per_sec", 0)
    m_checked = matcher.get("checked", 0)
    m_found = matcher.get("found", 0)
    m_uptime = matcher.get("uptime_seconds", 0)
    
    return (
        f"🚀 *Solana Hunter Status* 🚀\n\n"
        f"*Scraper (Python)*\n"
        f"• Speed: `{s_speed:.1f} blk/s`\n"
        f"• Slot: `{s_slot}`\n"
        f"• Targets Found: `{s_found}`\n\n"
        f"*Matcher (Rust)*\n"
        f"• Speed: `{m_speed/1000:.1f}k keys/s`\n"
        f"• Total Checked: `{m_checked:,}`\n"
        f"• Jackpots: `{m_found}`\n"
        f"• Uptime: `{int(m_uptime)}s`"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return

    keyboard = [
        [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh")],
        [InlineKeyboardButton("📜 View Found", callback_data="found")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(get_status_text(), reply_markup=reply_markup, parse_mode="Markdown")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if user.id != ALLOWED_USER_ID:
        await query.answer("Access Denied")
        return

    await query.answer()

    if query.data == "refresh":
        keyboard = [
            [InlineKeyboardButton("🔄 Refresh Status", callback_data="refresh")],
            [InlineKeyboardButton("📜 View Found", callback_data="found")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await query.edit_message_text(get_status_text(), reply_markup=reply_markup, parse_mode="Markdown")
        except Exception:
            pass # Content didn't change

    elif query.data == "found":
        if os.path.exists(FOUND_FILE):
            with open(FOUND_FILE, "r") as f:
                content = f.read()[-4000:] # Telegram limit
            if not content:
                content = "No jackpots yet."
        else:
            content = "No found file yet."
            
        await query.message.reply_text(f"💰 *Found Wallets*:\n\n`{content}`", parse_mode="Markdown")

async def monitor_found(app: Application):
    global last_found_size
    while True:
        try:
            if os.path.exists(FOUND_FILE):
                current_size = os.path.getsize(FOUND_FILE)
                if current_size > last_found_size:
                    # New content!
                    with open(FOUND_FILE, "r") as f:
                        f.seek(last_found_size)
                        new_content = f.read()
                    
                    if new_content.strip():
                        await app.bot.send_message(
                            chat_id=ALLOWED_USER_ID,
                            text=f"🚨 *JACKPOT FOUND!* 🚨\n\n`{new_content}`",
                            parse_mode="Markdown"
                        )
                    last_found_size = current_size
            else:
                last_found_size = 0
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        
        await asyncio.sleep(5)

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))

    # Start monitor task
    loop = asyncio.get_event_loop()
    loop.create_task(monitor_found(app))

    print("Bot started...")
    app.run_polling()

if __name__ == "__main__":
    main()
