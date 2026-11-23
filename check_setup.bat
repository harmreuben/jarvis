@echo off
rem Tests the JARVIS installation (API key, voice, search, camera...).
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo JARVIS is not installed yet. Double-click setup_windows.bat first.
    pause
    exit /b 1
)
"venv\Scripts\python.exe" check_setup.py
echo.
pause
