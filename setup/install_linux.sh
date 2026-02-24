#!/bin/bash

echo ""
echo "=========================================="
echo "  Bot Factory - Install (Linux)"
echo "=========================================="
echo ""

# check Python3
if ! command -v python3 &> /dev/null; then
    echo "[!] Python3 not found. Installing..."
    echo ""

    if command -v apt &> /dev/null; then
        sudo apt update && sudo apt install -y python3 python3-venv python3-pip

    elif command -v dnf &> /dev/null; then
        sudo dnf install -y python3 python3-pip

    elif command -v pacman &> /dev/null; then
        sudo pacman -Sy --noconfirm python python-pip

    else
        echo "[ERROR] Unknown package manager"
        echo "Install Python3 manually and run again"
        exit 1
    fi

    echo ""
fi

# verify
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 still not found after install"
    exit 1
fi

echo "[OK] $(python3 --version)"
echo ""

# check venv module
if ! python3 -m venv --help &> /dev/null; then
    echo "[!] Installing python3-venv..."
    if command -v apt &> /dev/null; then
        sudo apt install -y python3-venv
    fi
fi

# run setup
python3 "$(dirname "$0")/setup.py"
