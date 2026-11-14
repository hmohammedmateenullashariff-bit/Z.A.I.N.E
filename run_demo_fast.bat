@echo off
title Z.A.I.N.E Seminar Demo Environment (Fast 3B Mode)
cd /d "%~dp0"
if exist "%~dp0.venv\Scripts\python.exe" (
    set PATH=%~dp0.venv\Scripts;%PATH%
)

echo ======================================================================
echo   Z.A.I.N.E - Autonomous Sovereign AI Assistant
echo   Seminar Live Demonstration Mode (ZAINE_FAST=1, ZAINE_DEMO=1)
echo ======================================================================
echo.

set ZAINE_FAST=1
set ZAINE_DEMO=1
set ZAINE_SINGLE_MODEL=1
set ZAINE_NUM_CTX=6144
set ZAINE_WORKSPACE=%~dp0demo_workspace
set OLLAMA_MODELS=E:\ollama\models

echo [1/2] Checking Ollama daemon and models...
python scripts\ensure_ollama.py
if errorlevel 1 (
    echo.
    echo [ERROR] Ollama daemon failed to start or load models.
    pause
    exit /b 1
)

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
