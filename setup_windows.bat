@echo off
setlocal
cd /d "%~dp0"
echo PerfectMatchLFP26 - first-time setup
echo.
if exist ".venv\Scripts\python.exe" goto install
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv .venv
    goto check
)
python -c "import sys; assert sys.version_info >= (3, 11)" >nul 2>&1
if errorlevel 1 (
    echo Python 3.11 or newer was not found. Ask IT to install Python 3.12 from python.org,
    echo with "Add python.exe to PATH" enabled, then run this file again.
    goto failed
)
python -m venv .venv
:check
if not exist ".venv\Scripts\python.exe" goto failed
:install
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
echo.
echo Setup complete. Double-click start.bat to open the app.
if not defined LFM_NO_PAUSE pause
exit /b 0
:failed
echo.
echo SETUP FAILED. Keep this window open and show the message above to IT.
if not defined LFM_NO_PAUSE pause
exit /b 1
