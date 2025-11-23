#!/bin/bash

echo "Stopping Matcher and Bot..."

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
