@echo off
REM ============================================================
REM  Start the Math Exercise Sheets web app.
REM
REM  Double-click this file to run the local server.
REM    - It listens on http://127.0.0.1:8000
REM    - Open that URL in your browser.
REM    - Press Ctrl+C in this terminal to stop the server.
REM    - The window closes when the server exits cleanly; it
REM      stays open so you can read the error if the server
REM      fails to start.
REM ============================================================

setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo uv is not installed or not on your PATH.
    echo Install it from https://docs.astral.sh/uv/getting-started/installation/
    echo then double-click sync.cmd before running this file.
    echo.
    pause
    exit /b 1
)

echo ============================================================
echo  Math Exercise Sheets - http://127.0.0.1:8000
echo  Press Ctrl+C to stop.
echo ============================================================
echo.

uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
set EC=%ERRORLEVEL%

if %EC% neq 0 (
    echo.
    echo ============================================================
    echo  Server exited with error code %EC%.
    echo  Press any key to close this window.
    echo ============================================================
    pause >nul
)

exit /b %EC%
