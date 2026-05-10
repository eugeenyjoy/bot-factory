#!/bin/bash

# Bot Factory Server Deploy Script
# Простой скрипт для развертывания на Linux сервере

set -e

echo "================================================"
echo "Bot Factory - Server Deploy"
echo "================================================"
echo ""

# 1. Проверка Python
echo "[1/5] Проверка Python версии..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
echo "✓ Найден Python $PYTHON_VERSION"

if [[ $(echo "$PYTHON_VERSION < 3.10" | bc -l) -eq 1 ]]; then
    echo "⚠️ Требуется Python 3.10 или выше (найден $PYTHON_VERSION)"
    exit 1
fi

# 2. Создание виртуального окружения
echo ""
echo "[2/5] Установка зависимостей..."
if [ ! -d "venv" ]; then
    echo "  Создание виртуального окружения..."
    python3 -m venv venv
fi

# Активация venv
source venv/bin/activate

# Обновление pip
pip install --upgrade pip setuptools wheel > /dev/null 2>&1

# Установка зависимостей
pip install -r requirements.txt

# 3. Проверка .env файла
echo ""
echo "[3/5] Проверка конфигурации..."
if [ ! -f ".env" ]; then
    echo "  ⚠️ Файл .env не найден"
    echo "  Копирую .env.example -> .env"
    cp .env.example .env
    echo "  ℹ️ Отредактируйте .env перед запуском на продакшене!"
else
    echo "  ✓ Файл .env найден"
fi

# 4. Проверка зависимостей импорта
echo ""
echo "[4/5] Проверка зависимостей..."
python3 -c "from telegram import Update; print('  ✓ python-telegram-bot OK')" || {
    echo "  ✗ Ошибка при установке зависимостей"
    exit 1
}

# 5. Информация для запуска
echo ""
echo "[5/5] Готово к запуску!"
echo ""
echo "================================================"
echo "ИНСТРУКЦИЯ ПО ЗАПУСКУ:"
echo "================================================"
echo ""
echo "На локальной машине:"
echo "  source venv/bin/activate"
echo "  python app.py"
echo ""
echo "На сервере (с ngx или другим reverse proxy):"
echo "  source venv/bin/activate"
echo "  export BF_HOST=0.0.0.0"
echo "  export BF_PORT=8000"
echo "  python app.py"
echo ""
echo "Или в Docker:"
echo "  docker-compose -f setup/docker-compose.yml up -d"
echo ""
echo "================================================"
