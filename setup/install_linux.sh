#!/bin/bash
echo ""
echo "=========================================="
echo "  Bot Factory — Установка (Linux)"
echo "=========================================="
echo ""

# проверяем есть ли Python
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 не найден!"
    echo ""
    echo "Установи:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  Arch:          sudo pacman -S python"
    echo "  Fedora:        sudo dnf install python3"
    echo ""
    echo "После установки — запусти этот скрипт снова."
    exit 1
fi

echo "✅ Python3 найден!"
python3 --version
echo ""

# проверяем python3-venv
if ! python3 -m venv --help &> /dev/null; then
    echo "❌ Модуль venv не найден!"
    echo "  Установи: sudo apt install python3-venv"
    exit 1
fi

# запускаем умный установщик
python3 "$(dirname "$0")/setup.py"
