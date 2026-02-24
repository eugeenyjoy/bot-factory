#!/bin/bash

if [ ! -d "venv" ]; then
    echo "❌ Сначала запусти установку: bash setup/install_linux.sh"
    exit 1
fi

source venv/bin/activate
echo ""
echo "🤖 Запускаю Bot Factory..."
echo "   Открой: http://localhost:8000"
echo "   Для остановки: Ctrl+C"
echo ""
python app.py
