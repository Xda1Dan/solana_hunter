#!/bin/bash

echo "=== Starting Matcher + Bot ==="

# 1. Start Matcher
echo "Starting Matcher (Rust)..."
cd solana-matcher
nohup cargo run --release > matcher.log 2>&1 &
MATCHER_PID=$!
echo "-> Matcher running (PID: $MATCHER_PID). Logs: solana-matcher/matcher.log"

# 2. Start Monitor Bot
cd ..
echo "Starting Monitor Bot..."
nohup python3 monitor_bot.py > bot.log 2>&1 &
BOT_PID=$!
echo "-> Bot running (PID: $BOT_PID). Logs: bot.log"

# Save PIDs
echo $MATCHER_PID > matcher.pid
echo $BOT_PID > bot.pid

echo ""
echo "Matcher and Bot are running!"
echo "To stop: ./stop_matcher.sh"
echo "Monitor via Telegram bot"
