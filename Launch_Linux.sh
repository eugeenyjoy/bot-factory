#!/bin/bash

if [ ! -d "venv" ]; then
    echo "[ERROR] Run setup/install_linux.sh first!"
    exit 1
fi

echo ""
echo " Bot Factory - Starting..."
echo " Open: http://localhost:8000"
echo " Stop: Ctrl+C"
echo ""

venv/bin/python app.py
