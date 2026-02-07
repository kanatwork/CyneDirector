@echo off
:: CyneDirector Launcher - uses the venv Python automatically
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo [ERROR] Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)
venv\Scripts\python.exe main.py %*
if %errorlevel% neq 0 pause
