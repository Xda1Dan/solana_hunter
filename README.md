# Solana Wallet Checker Bot

Two run modes:

- CLI infinite checker (optional): `main.py`
- Telegram bot (AWS-friendly): `bot.py` using `checker.py` with inline buttons

## Setup

- Python 3.9+
- Install deps:

```bash
pip install -r requirements.txt
```

### Configuration

- `bot.py` includes a hardcoded Telegram bot token.
- Optional environment variables:
  - `ALLOWED_CHAT_ID` – restrict access to a single chat id
  - `RPC_URL`, `BATCH_SIZE`, `CONCURRENCY`, `TIMEOUT_S`, `FOUND_FILE`, `TEST_INJECT_PRIV` – override defaults if desired

## CLI Infinite Checker (optional)

```bash
python main.py
```

- Press Ctrl+C to stop cleanly.
- Found wallets are appended to `found.txt` (CSV).

## Telegram Bot (buttons UI)

```bash
export ALLOWED_CHAT_ID=123456789 # optional
python bot.py
```

Usage:
- Send `/start` to receive the control panel with buttons:
  - Start – begin the checker loop
  - Stop – stop the checker loop
  - Status – show counters and uptime (message updates in place)
  - Latest – show last 10 found wallets

Notes:
- Bot runs with long polling; for 24/7 on AWS, use `tmux` or a systemd service.
- All finds are appended to `FOUND_FILE` CSV (`found.txt` by default).
