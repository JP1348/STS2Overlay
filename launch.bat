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
    if not exist ".venv\Scripts\python.exe" (
        echo ERROR: Failed to create virtual environment.
        echo Make sure Python 3.10+ is installed from https://python.org
        echo and that "Add Python to PATH" was ticked during install.
        echo Also disable the Microsoft Store Python alias in:
        echo   Settings ^> Apps ^> Advanced app settings ^> App execution aliases
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

:: Launch overlay
.venv\Scripts\python main.py --save-dir "C:\Users\John\AppData\Roaming\SlayTheSpire2\steam\76561197979082210\profile1\saves" %*
if errorlevel 1 (
    echo.
    echo Overlay exited with an error. See above for details.
    pause
)
