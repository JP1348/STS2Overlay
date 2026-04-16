@echo off
:: STS2 Advisor Overlay — Windows Launcher
:: Double-click this file to start the overlay.

cd /d "%~dp0"

:: Check if Python is installed
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Please install Python 3.10+ from https://python.org
    echo Make sure to tick "Add Python to PATH" during install.
    pause
    exit /b 1
)

:: Create venv if it doesn't exist
if not exist ".venv\Scripts\python.exe" (
    echo Setting up virtual environment for first run...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
    .venv\Scripts\pip install -r requirements.txt
    if errorlevel 1 (
        echo ERROR: Failed to install dependencies.
        pause
        exit /b 1
    )
    echo Setup complete.
)

:: Launch overlay (auto-detects save directory)
.venv\Scripts\python main.py %*
if errorlevel 1 (
    echo.
    echo Overlay exited with an error. See above for details.
    pause
)
