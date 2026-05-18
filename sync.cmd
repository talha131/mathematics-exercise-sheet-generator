@echo off
REM ============================================================
REM  Install / refresh project dependencies.
REM
REM  Double-click this file to run `uv sync` in a terminal.
REM    - If everything succeeds the window closes automatically.
REM    - If something fails the window pauses so you can read the
REM      error before it disappears.
REM ============================================================

setlocal
cd /d "%~dp0"

where uv >nul 2>nul
if errorlevel 1 (
    echo.
    echo uv is not installed or not on your PATH.
    echo.
    echo Install it from https://docs.astral.sh/uv/getting-started/installation/
    echo or run this from PowerShell:
    echo     powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo.
    pause
    exit /b 1
)

echo Installing dependencies...
echo.
uv sync
set EC=%ERRORLEVEL%

if %EC% neq 0 (
    echo.
    echo ============================================================
    echo  uv sync exited with error code %EC%.
    echo  Press any key to close this window.
    echo ============================================================
    pause >nul
)

exit /b %EC%
