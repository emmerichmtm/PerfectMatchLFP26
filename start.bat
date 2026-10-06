@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo First double-click setup_windows.bat to prepare this computer.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" app.py
if errorlevel 1 pause
