import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Configuration ---
TOKEN = "8513216536:AAE2O8g-yC3zCVXl_Q6z4hWwL4WqM-MnQHQ"
ALLOWED_USER_ID = 6522490688
SCRAPER_STATS_FILE = "scraper_stats.json"
MATCHER_STATS_FILE = "matcher_stats.json"
FOUND_FILE = "found.txt"
TARGETS_FILE = "targets.txt"
SCRAPER_LOG = "scraper.log"
MATCHER_LOG = "solana-matcher/matcher.log"

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

def format_uptime(seconds):
    """Format seconds into human-readable uptime"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds/60)}m {int(seconds%60)}s"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"

def progress_bar(value, max_value, length=10):
    """Create a text-based progress bar"""
    if max_value == 0:
        filled = 0
    else:
        filled = int((value / max_value) * length)
    bar = "█" * filled + "░" * (length - filled)
    return f"[{bar}]"

def get_main_keyboard():
    """Main menu keyboard"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Status", callback_data="status"),
            InlineKeyboardButton("📈 Stats", callback_data="stats")
        ],
        [
            InlineKeyboardButton("🎯 Targets", callback_data="targets"),
            InlineKeyboardButton("💰 Found", callback_data="found")
        ],
        [
            InlineKeyboardButton("📄 Logs", callback_data="logs"),
            InlineKeyboardButton("❓ Help", callback_data="help")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_status_text():
    """Enhanced status with progress bars"""
    scraper = read_json(SCRAPER_STATS_FILE)
    matcher = read_json(MATCHER_STATS_FILE)
    
    s_speed = scraper.get("speed_blocks_per_sec", 0)
    s_found = scraper.get("high_value_found", 0)
    s_slot = scraper.get("current_slot", 0)
    s_checked = scraper.get("signers_checked", 0)
    
    m_speed = matcher.get("speed_keys_per_sec", 0)
    m_checked = matcher.get("checked", 0)
    m_found = matcher.get("found", 0)
    m_uptime = matcher.get("uptime_seconds", 0)
    
    # Speed indicators
    s_speed_bar = progress_bar(min(s_speed, 10), 10, 8)
    m_speed_bar = progress_bar(min(m_speed/1000, 50), 50, 8)
    
    return (
        f"🚀 *SOLANA HUNTER* 🚀\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*🔍 SCRAPER*\n"
        f"⚡ Speed: `{s_speed:.1f}` blk/s {s_speed_bar}\n"
        f"📍 Slot: `{s_slot:,}`\n"
        f"👤 Signers: `{s_checked:,}`\n"
        f"🎯 Targets: `{s_found}`\n\n"
        f"*🔥 MATCHER*\n"
        f"⚡ Speed: `{m_speed/1000:.1f}k` keys/s {m_speed_bar}\n"
        f"🔢 Checked: `{m_checked:,}`\n"
        f"💎 Jackpots: `{m_found}`\n"
        f"⏱ Uptime: `{format_uptime(m_uptime)}`\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"_Last updated: {datetime.now().strftime('%H:%M:%S')}_"
    )

def get_stats_text():
    """Detailed statistics"""
    scraper = read_json(SCRAPER_STATS_FILE)
    matcher = read_json(MATCHER_STATS_FILE)
    
    s_blocks = scraper.get("blocks_processed", 0)
    s_txs = scraper.get("transactions_scanned", 0)
    s_signers = scraper.get("signers_checked", 0)
    
    m_checked = matcher.get("checked", 0)
    m_speed = matcher.get("speed_keys_per_sec", 0)
    m_uptime = matcher.get("uptime_seconds", 0)
    
    # Calculate averages
    avg_tx_per_block = s_txs / s_blocks if s_blocks > 0 else 0
    
    return (
        f"📈 *DETAILED STATISTICS*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Scraper Metrics*\n"
        f"• Blocks: `{s_blocks:,}`\n"
        f"• Transactions: `{s_txs:,}`\n"
        f"• Avg TX/Block: `{avg_tx_per_block:.1f}`\n"
        f"• Signers: `{s_signers:,}`\n\n"
        f"*Matcher Metrics*\n"
        f"• Total Checked: `{m_checked:,}`\n"
        f"• Current Speed: `{m_speed:,.0f}` keys/s\n"
        f"• Runtime: `{format_uptime(m_uptime)}`\n"
        f"• Avg Speed: `{m_checked/m_uptime if m_uptime > 0 else 0:,.0f}` keys/s\n"
    )

def get_targets_text():
    """Target information"""
    if os.path.exists(TARGETS_FILE):
        with open(TARGETS_FILE, "r") as f:
            lines = f.readlines()
        count = len(lines)
        size_kb = os.path.getsize(TARGETS_FILE) / 1024
        
        # Show last 5 targets
        recent = "".join(lines[-5:]) if count > 0 else "None yet"
        
        return (
            f"🎯 *TARGET DATABASE*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📊 Total: `{count}` addresses\n"
            f"💾 Size: `{size_kb:.1f}` KB\n\n"
            f"*Last 5 Targets:*\n"
            f"```\n{recent.strip()}\n```"
        )
    else:
        return "🎯 *TARGET DATABASE*\n\nNo targets file found."

def get_logs_text():
    """Recent logs from scraper and matcher"""
    logs = "📄 *RECENT LOGS*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    
    # Scraper logs
    if os.path.exists(SCRAPER_LOG):
        with open(SCRAPER_LOG, "r") as f:
            lines = f.readlines()
        recent = "".join(lines[-10:])
        logs += f"*Scraper (last 10 lines):*\n```\n{recent.strip()}\n```\n\n"
    else:
        logs += "*Scraper:* No logs\n\n"
    
    # Matcher logs
    if os.path.exists(MATCHER_LOG):
        with open(MATCHER_LOG, "r") as f:
            lines = f.readlines()
        recent = "".join(lines[-10:])
        logs += f"*Matcher (last 10 lines):*\n```\n{recent.strip()}\n```"
    else:
        logs += "*Matcher:* No logs"
    
    return logs

def get_help_text():
    """Help message with all commands"""
    return (
        f"❓ *COMMAND REFERENCE*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"/start - Main menu\n"
        f"/status - Live system status\n"
        f"/stats - Detailed statistics\n"
        f"/targets - Target database info\n"
        f"/found - View found wallets\n"
        f"/logs - Recent log entries\n"
        f"/help - This help message\n\n"
        f"💡 *Tip:* Use the inline keyboard buttons for quick access!"
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return

    welcome = (
        f"👋 *Welcome to Solana Hunter!*\n\n"
        f"Your 24/7 wallet discovery system is ready.\n"
        f"Use the menu below to monitor progress:\n"
    )
    await update.message.reply_text(
        welcome, 
        reply_markup=get_main_keyboard(), 
        parse_mode="Markdown"
    )

async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return
    
    await update.message.reply_text(
        get_status_text(),
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return
    
    await update.message.reply_text(
        get_stats_text(),
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def targets_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return
    
    await update.message.reply_text(
        get_targets_text(),
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def logs_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return
    
    await update.message.reply_text(
        get_logs_text(),
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return
    
    await update.message.reply_text(
        get_help_text(),
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def found_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if user.id != ALLOWED_USER_ID:
        await update.message.reply_text("⛔ Access Denied")
        return
    
    if os.path.exists(FOUND_FILE):
        with open(FOUND_FILE, "r") as f:
            content = f.read()[-3000:]
        if not content.strip():
            content = "No jackpots yet. Keep hunting! 🎯"
    else:
        content = "No found file yet."
    
    await update.message.reply_text(
        f"💰 *FOUND WALLETS*\n━━━━━━━━━━━━━━━━━━━━\n\n```\n{content}\n```",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = query.from_user
    if user.id != ALLOWED_USER_ID:
        await query.answer("⛔ Access Denied")
        return

    await query.answer()

    # Route to appropriate handler
    if query.data == "status":
        try:
            await query.edit_message_text(
                get_status_text(),
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass
    
    elif query.data == "stats":
        try:
            await query.edit_message_text(
                get_stats_text(),
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass
    
    elif query.data == "targets":
        try:
            await query.edit_message_text(
                get_targets_text(),
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass
    
    elif query.data == "found":
        await found_cmd(update, context)
    
    elif query.data == "logs":
        await logs_cmd(update, context)
    
    elif query.data == "help":
        try:
            await query.edit_message_text(
                get_help_text(),
                reply_markup=get_main_keyboard(),
                parse_mode="Markdown"
            )
        except Exception:
            pass

async def monitor_found(app: Application):
    """Enhanced found wallet monitoring with beautiful alerts"""
    global last_found_size
    while True:
        try:
            if os.path.exists(FOUND_FILE):
                current_size = os.path.getsize(FOUND_FILE)
                if current_size > last_found_size:
                    # New content!
                    with open(FOUND_FILE, "r") as f:
                        f.seek(last_found_size)
                        new_content = f.read().strip()
                    
                    if new_content:
                        # Parse the found entry (format: timestamp,address,balance)
                        lines = new_content.strip().split("\n")
                        for line in lines:
                            parts = line.split(",")
                            if len(parts) >= 2:
                                timestamp = parts[0]
                                address = parts[1]
                                balance = parts[2] if len(parts) > 2 else "0.0"
                                
                                # Beautiful alert
                                alert = (
                                    f"🎉🎉🎉 *JACKPOT FOUND!* 🎉🎉🎉\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n\n"
                                    f"💎 *Address:*\n"
                                    f"`{address}`\n\n"
                                    f"💰 *Balance:* `{balance}` SOL\n"
                                    f"🕐 *Time:* {timestamp}\n\n"
                                    f"━━━━━━━━━━━━━━━━━━━━\n"
                                    f"_Keep hunting!_ 🚀"
                                )
                                
                                # Inline button to view on Solscan
                                keyboard = [[
                                    InlineKeyboardButton(
                                        "🔍 View on Solscan",
                                        url=f"https://solscan.io/account/{address}"
                                    )
                                ]]
                                
                                await app.bot.send_message(
                                    chat_id=ALLOWED_USER_ID,
                                    text=alert,
                                    parse_mode="Markdown",
                                    reply_markup=InlineKeyboardMarkup(keyboard)
                                )
                    
                    last_found_size = current_size
            else:
                last_found_size = 0
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        
        await asyncio.sleep(5)

async def post_init(application: Application):
    """Initialize monitoring task after application starts"""
    asyncio.create_task(monitor_found(application))

def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("targets", targets_cmd))
    app.add_handler(CommandHandler("found", found_cmd))
    app.add_handler(CommandHandler("logs", logs_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    
    # Callback handler
    app.add_handler(CallbackQueryHandler(button))

    logger.info("✅ Enhanced Solana Hunter Bot started!")
    app.run_polling()

if __name__ == "__main__":
    main()
