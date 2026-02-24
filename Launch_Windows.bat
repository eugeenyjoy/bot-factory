@echo off

if not exist venv (
    echo [ERROR] Run setup\install_windows.bat first!
    pause
    exit /b
)

echo.
echo  Bot Factory - Starting...
echo  Open: http://localhost:8000
echo  Stop: Ctrl+C
echo.

venv\Scripts\python.exe app.py
pause
