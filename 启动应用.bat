@echo off
setlocal
cd /d "%~dp0"

set "PYTHON=python"
if exist "venv\Scripts\python.exe" set "PYTHON=venv\Scripts\python.exe"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"

rem launch.py starts the server, waits for /ping, then opens the browser.
"%PYTHON%" scripts\launch.py %*
if errorlevel 1 (
    echo.
    echo Startup failed. See the error above.
    pause
)
