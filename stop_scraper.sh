#!/bin/bash

echo "Stopping Scraper..."

if [ -f scraper.pid ]; then
    PID=$(cat scraper.pid)
    echo "Stopping Scraper (PID: $PID)..."
    kill $PID
    rm scraper.pid
    echo "Scraper stopped."
else
    echo "Scraper PID file not found."
fi
