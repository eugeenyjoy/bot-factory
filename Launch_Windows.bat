@echo off

if not exist venv (
    echo [ERROR] Run setup\install_windows.bat first!
    pause
    exit /b
)

REM убиваем старый процесс если висит
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000 ^| findstr LISTENING') do (
    echo ⚠️  Port 8000 busy (PID: %%a). Killing...
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 >nul

echo.
echo  Bot Factory - Starting...
echo  Open: http://localhost:8000
echo  Stop: Ctrl+C
echo.

venv\Scripts\python.exe app.py
pause