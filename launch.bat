@echo off
:: STS2 Advisor Overlay — Windows Launcher
:: Double-click this file to start the overlay.

cd /d "%~dp0"

:: Check if Python is installed
where python >nul 2>&1
if errorlevel 1 (
    echo Python not found. Please install Python 3.10+ from https://python.org
    pause
    exit /b 1
)

:: Create venv if it doesn't exist
if not exist ".venv\Scripts\python.exe" (
    echo Setting up virtual environment for first run...
    python -m venv .venv
    .venv\Scripts\pip install -r requirements.txt
    echo Setup complete.
)

:: Launch overlay (auto-detects save directory)
.venv\Scripts\python main.py %*
