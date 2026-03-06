#!/bin/bash

if [ ! -d "venv" ]; then
    echo "[ERROR] Run setup/install_linux.sh first!"
    exit 1
fi

# убиваем старый процесс если висит
OLD_PID=$(lsof -t -i :8000 2>/dev/null)
if [ -n "$OLD_PID" ]; then
    echo "⚠️  Порт 8000 занят (PID: $OLD_PID). Убиваю..."
    kill -9 $OLD_PID 2>/dev/null
    sleep 1
fi

echo ""
echo " Bot Factory - Starting..."
echo " Open: http://localhost:8000"
echo " Stop: Ctrl+C"
echo ""

venv/bin/python app.py