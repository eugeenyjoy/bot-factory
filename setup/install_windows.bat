@echo off
chcp 65001 >nul
echo.
echo ==========================================
echo   Bot Factory — Установка (Windows)
echo ==========================================
echo.

REM проверяем есть ли Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден!
    echo.
    echo Скачай и установи:
    echo https://www.python.org/downloads/
    echo.
    echo ⚠️ При установке ОБЯЗАТЕЛЬНО поставь галочку:
    echo    [x] Add Python to PATH
    echo.
    echo После установки Python — запусти этот файл снова.
    echo.
    pause
    exit /b
)

echo ✅ Python найден!
python --version
echo.

REM запускаем умный установщик
python "%~dp0setup.py"

pause
