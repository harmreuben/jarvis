@echo off
rem Updates JARVIS to the latest version from GitHub (or drag a JARVIS zip onto this file).
rem Keeps your settings, contacts, reminders and chat history. Everything below is on one line on purpose:
rem this file may be replaced during the update, and Windows reads .bat files as it goes.
cd /d "%~dp0" & powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_jarvis.ps1" %* & echo. & pause & exit /b
