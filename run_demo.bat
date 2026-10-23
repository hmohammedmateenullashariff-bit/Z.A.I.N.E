@echo off
title Z.A.I.N.E Seminar Demo Environment
cd /d "%~dp0"

echo ======================================================================
echo   Z.A.I.N.E - Autonomous Sovereign AI Assistant
echo   Seminar Live Demonstration Mode (ZAINE_DEMO=1, SINGLE_MODEL=1)
echo ======================================================================
echo.

set ZAINE_DEMO=1
set ZAINE_SINGLE_MODEL=1
set OLLAMA_MODELS=D:\ollama\models

echo [1/2] Checking Ollama daemon...
powershell -NoProfile -Command "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2; Write-Host '  -> Ollama is online.' } catch { Write-Host '  -> Starting Ollama daemon...'; Start-Process -NoNewWindow ollama 'serve'; Start-Sleep -Seconds 3 }"

echo [2/2] Starting CoreService with these settings (a core running with other settings is restarted)...
python scripts\ensure_core.py
if errorlevel 1 (
    echo.
    echo [ERROR] Core service is not ready. See data\core_service.log
    pause
    exit /b 1
)

echo.
echo ======================================================================
echo   Launching Z.A.I.N.E Interactive Terminal (TUI)
echo ======================================================================
echo.
python zaine_tui.py

if errorlevel 1 (
    echo.
    echo [ERROR] TUI exited with error code %errorlevel%.
    pause
)
