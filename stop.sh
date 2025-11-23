#!/bin/bash

if [ -f scraper.pid ]; then
    PID=$(cat scraper.pid)
    echo "Stopping Scraper (PID: $PID)..."
    kill $PID
    rm scraper.pid
else
    echo "Scraper PID file not found."
fi

if [ -f matcher.pid ]; then
    PID=$(cat matcher.pid)
    echo "Stopping Matcher (PID: $PID)..."
    kill $PID
    rm matcher.pid
else
    echo "Matcher PID file not found."
fi

if [ -f bot.pid ]; then
    PID=$(cat bot.pid)
    echo "Stopping Bot (PID: $PID)..."
    kill $PID
    rm bot.pid
else
    echo "Bot PID file not found."
fi

echo "Stopped."
