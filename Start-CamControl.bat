@echo off
title CamControl
cd /d "%~dp0"

:: Kill any existing instances on port 8080
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8080 "') do taskkill /f /pid %%a >nul 2>&1

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo Python not found. Installing via winget...
    winget install Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    refreshenv 2>nul
)

:: Create venv if missing
if not exist ".venv\Scripts\python.exe" (
    echo Setting up environment - this takes 2 minutes on first run...
    python -m venv .venv
    .venv\Scripts\pip install fastapi uvicorn requests pillow --quiet
)

:: Start go2rtc in background
if exist "tools\go2rtc.exe" (
    start /b "" "tools\go2rtc.exe" -config "tools\go2rtc.yaml"
)

:: Start gateway
echo Starting CamControl at http://localhost:8080
echo.
start "" http://localhost:8080/
.venv\Scripts\python.exe -m camera_bridge.main

pause
