#!/bin/bash

echo "=== Starting Scraper Only ==="

# Start Scraper
echo "Starting Scraper (fast_scraper.py)..."
nohup python3 fast_scraper.py > scraper.log 2>&1 &
SCRAPER_PID=$!
echo "-> Scraper running (PID: $SCRAPER_PID). Logs: scraper.log"

# Save PID
echo $SCRAPER_PID > scraper.pid

echo ""
echo "Scraper is running in the background."
echo "To stop: ./stop_scraper.sh"
echo "Monitor logs: tail -f scraper.log"
