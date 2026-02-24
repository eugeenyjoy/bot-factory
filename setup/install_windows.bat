@echo off
chcp 65001 >nul

echo.
echo ==========================================
echo   Bot Factory - Install (Windows)
echo ==========================================
echo.

REM check if Python exists
python --version >nul 2>&1
if errorlevel 1 goto :nopython

REM check Python version (must be 3.9-3.12)
for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)

if %PYMINOR% GEQ 13 (
    echo [!] Python %PYVER% is too new, need 3.9-3.12
    echo     Removing is recommended:
    echo     Settings - Apps - Python %PYVER% - Uninstall
    echo.
    goto :installpython
)

if %PYMINOR% LSS 9 (
    echo [!] Python %PYVER% is too old, need 3.9-3.12
    goto :installpython
)

echo [OK] Python %PYVER%
goto :runsetup

:nopython
echo [!] Python not found
echo.

:installpython
echo Trying to install Python 3.12 via winget...
echo.

winget --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] winget not found
    echo.
    echo Install Python manually:
    echo https://www.python.org/downloads/release/python-31210/
    echo Check "Add Python to PATH"!
    echo.
    echo Then run this file again.
    pause
    exit /b
)

winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements

if errorlevel 1 (
    echo [ERROR] Failed to install Python
    echo Install manually: https://www.python.org/downloads/release/python-31210/
    pause
    exit /b
)

echo.
echo ==========================================
echo   [OK] Python installed!
echo   CLOSE this window and run again.
echo   PATH needs to refresh.
echo ==========================================
echo.
pause
exit /b

:runsetup
echo.
python "%~dp0setup.py"
pause
