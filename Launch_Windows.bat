@echo off
chcp 65001 >nul

if not exist venv (
    echo ❌ Сначала запусти установку: setup\install_windows.bat
    pause
    exit /b
)

call venv\Scripts\activate.bat
echo.
echo 🤖 Запускаю Bot Factory...
echo    Открой: http://localhost:8000
echo    Для остановки: Ctrl+C
echo.
python app.py
pause
