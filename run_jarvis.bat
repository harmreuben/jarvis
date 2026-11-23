@echo off
rem Starts JARVIS. Closing the JARVIS window stops it.
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo JARVIS is not installed yet. Double-click setup_windows.bat first.
    pause
    exit /b 1
)
"venv\Scripts\python.exe" jarvis.py
if errorlevel 1 (
    echo.
    echo JARVIS stopped with an error - see the messages above.
    pause
)
