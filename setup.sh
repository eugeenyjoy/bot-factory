cat > ~/projects/bot-factory/setup.sh << 'EOF'
#!/bin/bash
echo "🤖 Bot Factory — Установка"
echo "=========================="

# проверяем Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден. Установите: sudo apt install python3 python3-venv"
    exit 1
fi

# создаём venv
echo "📦 Создаю виртуальное окружение..."
python3 -m venv venv
source venv/bin/activate

# ставим зависимости
echo "📥 Устанавливаю зависимости..."
pip install -r requirements.txt

echo ""
echo "✅ Готово!"
echo ""
echo "Запуск:"
echo "  source venv/bin/activate"
echo "  python app.py"
echo ""
echo "Потом открой: http://localhost:8000"
EOF
