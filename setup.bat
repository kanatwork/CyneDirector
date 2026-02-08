@echo off
setlocal enabledelayedexpansion
title CyneDirector Setup

echo ============================================================
echo   CyneDirector v2.1.0 - Environment Setup
echo ============================================================
echo.

:: ── 1. Find a compatible Python (3.10, 3.11, or 3.12) ──────────

set PYTHON_CMD=
set PYTHON_VER=

:: Try py launcher first (most reliable on Windows)
for %%V in (3.12 3.11 3.10) do (
    if not defined PYTHON_CMD (
        py -%%V --version >nul 2>&1
        if !errorlevel! equ 0 (
            set PYTHON_CMD=py -%%V
            for /f "tokens=2" %%A in ('py -%%V --version 2^>^&1') do set PYTHON_VER=%%A
        )
    )
)

:: Fallback: check PATH for python3.12, python3.11, etc.
if not defined PYTHON_CMD (
    for %%V in (python3.12 python3.11 python3.10 python) do (
        if not defined PYTHON_CMD (
            %%V --version >nul 2>&1
            if !errorlevel! equ 0 (
                for /f "tokens=2" %%A in ('%%V --version 2^>^&1') do (
                    echo %%A | findstr /b "3.10 3.11 3.12" >nul
                    if !errorlevel! equ 0 (
                        set PYTHON_CMD=%%V
                        set PYTHON_VER=%%A
                    )
                )
            )
        )
    )
)

if not defined PYTHON_CMD (
    echo [ERROR] No compatible Python found.
    echo.
    echo PyTorch requires Python 3.10, 3.11, or 3.12.
    echo Your system has Python 3.14 which is NOT yet supported.
    echo.
    echo Please install Python 3.12 from:
    echo   https://www.python.org/downloads/release/python-3128/
    echo.
    echo During installation, make sure to check:
    echo   [x] Add Python to PATH
    echo   [x] Install py launcher
    echo.
    echo Then re-run this script.
    pause
    exit /b 1
)

echo [OK] Found Python %PYTHON_VER% (%PYTHON_CMD%)
echo.

:: ── 2. Create virtual environment ───────────────────────────────

set VENV_DIR=venv

if exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [OK] Virtual environment already exists at %VENV_DIR%\
    echo      To recreate, delete the venv folder and re-run this script.
) else (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv %VENV_DIR%
    if !errorlevel! neq 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created at %VENV_DIR%\
)
echo.

:: ── 3. Activate venv ────────────────────────────────────────────

call %VENV_DIR%\Scripts\activate.bat
echo [OK] Virtual environment activated
echo.

:: ── 4. Upgrade pip ──────────────────────────────────────────────

echo Upgrading pip...
python -m pip install --upgrade pip --quiet
echo [OK] pip upgraded
echo.

:: ── 5. Install PyTorch with CUDA ────────────────────────────────

echo ============================================================
echo   Installing PyTorch with CUDA support
echo   (This downloads ~2.5 GB - may take a few minutes)
echo ============================================================
echo.

python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu126
if !errorlevel! neq 0 (
    echo.
    echo [WARNING] CUDA install failed. Trying CPU-only PyTorch...
    python -m pip install torch torchvision
    if !errorlevel! neq 0 (
        echo [ERROR] PyTorch installation failed.
        pause
        exit /b 1
    )
)
echo.
echo [OK] PyTorch installed
echo.

:: ── 6. Install project dependencies ────────────────────────────

echo ============================================================
echo   Installing project dependencies from requirements.txt
echo ============================================================
echo.

python -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo.
    echo [WARNING] Some dependencies failed. Attempting individually...
    echo.
    for /f "usebackq eol=# tokens=*" %%L in ("requirements.txt") do (
        echo Installing: %%L
        python -m pip install %%L 2>nul
    )
)
echo.
echo [OK] Dependencies installed
echo.

:: ── 7. Verify installation ─────────────────────────────────────

echo ============================================================
echo   Verifying installation
echo ============================================================
echo.

python -c "import torch; print(f'  torch       {torch.__version__}  CUDA={torch.cuda.is_available()}')"
python -c "import transformers; print(f'  transformers {transformers.__version__}')" 2>nul
python -c "import faster_whisper; print(f'  faster-whisper OK')" 2>nul
python -c "import chromadb; print(f'  chromadb    {chromadb.__version__}')" 2>nul
python -c "import cv2; print(f'  opencv      {cv2.__version__}')" 2>nul
python -c "import PyQt6.QtCore; print(f'  PyQt6       OK')" 2>nul
python -c "from dotenv import load_dotenv; print(f'  python-dotenv OK')" 2>nul
echo.

:: ── 8. Run device detection test ────────────────────────────────

echo ============================================================
echo   Running AI pipeline test
echo ============================================================
echo.

if exist test_device_detection.py (
    python test_device_detection.py
) else (
    echo [SKIP] test_device_detection.py not found
)
echo.

:: ── Done ────────────────────────────────────────────────────────

echo ============================================================
echo   Setup complete!
echo ============================================================
echo.
echo To use CyneDirector:
echo   1. Activate the environment:  venv\Scripts\activate
echo   2. Run the application:       python main.py
echo.
echo To run tests:
echo   python test_device_detection.py
echo.
pause
