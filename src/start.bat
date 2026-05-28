@echo off
REM RAG Pipeline startup script for Windows

echo.
echo ==========================================
echo RAG Pipeline Startup Script
echo ==========================================

REM Step 1: Ensure virtual environment and install dependencies only if needed
echo.
echo [1] Checking virtual environment and dependencies...

REM SCRIPT_DIR is this src/ directory
set "SCRIPT_DIR=%~dp0"
set "VENV_DIR=%SCRIPT_DIR%..\.venv"

REM Use label flow to avoid nested IF/ELSE parsing issues
IF EXIST "%VENV_DIR%\Scripts\python.exe" GOTO venv_ok

IF EXIST "%VENV_DIR%\pyvenv.cfg" (
    echo     [WARN] Incomplete virtual environment detected at %VENV_DIR% - removing
    rmdir /S /Q "%VENV_DIR%"
)

echo     [INFO] Creating virtual environment at %VENV_DIR%
python -m venv "%VENV_DIR%"
if %errorlevel% neq 0 (
    echo     [ERR] Failed to create virtual environment
    pause
    exit /b 1
)

:venv_ok
echo     [OK] Virtual environment ready at %VENV_DIR%
call "%VENV_DIR%\Scripts\activate.bat" 2>nul
echo     [OK] Activated virtual environment

REM Check if a core dependency (fastapi) is installed to avoid reinstalling everything
"%VENV_DIR%\Scripts\python.exe" -m pip show fastapi >nul 2>&1
IF %errorlevel% EQU 0 GOTO deps_ok

echo     [INFO] Installing dependencies from requirements.txt...
"%VENV_DIR%\Scripts\python.exe" -m pip install -r "%SCRIPT_DIR%requirements.txt"
if %errorlevel% neq 0 (
    echo     [ERR] Error installing dependencies (see output)
    pause
    exit /b 1
)

:deps_ok
echo     [OK] Dependencies are present

REM Step 2: Create sample documents
echo.
echo [2] Creating sample documents...
python crawler.py --mode sample --output ./sample_docs
if %errorlevel% equ 0 (
    echo     [OK] Sample documents created
) else (
    echo     [ERR] Error creating sample documents
    pause
    exit /b 1
)

REM Step 3: Start FastAPI server
echo.
echo [3] Starting FastAPI server...
echo.
echo     Swagger UI: http://localhost:8001/docs
echo     API Base: http://localhost:8001
echo.
echo     Press Ctrl+C to stop the server
echo.

python -m uvicorn api:app --reload --host 0.0.0.0 --port 8001

pause
