@echo off
setlocal
cd /d "%~dp0"
title LLM Arena
if exist "venv\Scripts\python.exe" (
    "venv\Scripts\python.exe" -c "import sys" >nul 2>&1
    if not errorlevel 1 (
        "venv\Scripts\python.exe" launch.py
        goto finished
    )
)
where py >nul 2>&1
if not errorlevel 1 (
    py -3 launch.py
    goto finished
)
where python >nul 2>&1
if not errorlevel 1 (
    python launch.py
    goto finished
)
echo Python 3.10 or newer is needed. Install Python, then double-click this launcher again.
pause
exit /b 1
:finished
if errorlevel 1 (
    echo.
    echo Startup failed. See the error above.
    pause
)
