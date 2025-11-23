#!/bin/bash

echo "=== Starting Solana Hunter 24/7 ==="

# 1. Start Scraper
echo "Starting Scraper (fast_scraper.py)..."
nohup python3 fast_scraper.py > scraper.log 2>&1 &
SCRAPER_PID=$!
echo "-> Scraper running (PID: $SCRAPER_PID). Logs: scraper.log"

# 2. Start Matcher
echo "Starting Matcher (Rust)..."
cd solana-matcher
nohup cargo run --release > matcher.log 2>&1 &
MATCHER_PID=$!
echo "-> Matcher running (PID: $MATCHER_PID). Logs: solana-matcher/matcher.log"

# 3. Start Monitor Bot
echo "Starting Monitor Bot..."
nohup python3 monitor_bot.py > bot.log 2>&1 &
BOT_PID=$!
echo "-> Bot running (PID: $BOT_PID). Logs: bot.log"

# Save PIDs
echo $SCRAPER_PID > ../scraper.pid
echo $MATCHER_PID > ../matcher.pid
echo $BOT_PID > ../bot.pid

echo ""
echo "All systems go! Processes are running in the background."
echo "To stop: ./stop.sh (create this or kill PIDs manually)"
echo "Monitor logs: tail -f scraper.log"
