@echo off
title Z.A.I.N.E - Autonomous Sovereign Intelligence
cd /d "%~dp0"

echo ======================================================================
echo             Z . A . I . N . E   S Y S T E M   W A K E
echo         Zero-latency Autonomous Intelligent Neural Entity
echo ======================================================================
echo.

set ZAINE_FAST=1
set ZAINE_DEMO=1
set ZAINE_SINGLE_MODEL=1
set ZAINE_NUM_CTX=6144
set ZAINE_WORKSPACE=%~dp0demo_workspace
set OLLAMA_MODELS=D:\ollama\models

echo [1/3] Checking Ollama Neural Daemon and Models...
python scripts\ensure_ollama.py
if errorlevel 1 (
    echo.
    echo [ERROR] Ollama daemon failed to start or load models.
    pause
    exit /b 1
)

echo [2/3] Initializing Hardened Core Service (:7860)...
python scripts\ensure_core.py
if errorlevel 1 (
    echo.
    echo [ERROR] Core service failed to start or warm up. See data\core_service.log
    pause
    exit /b 1
)

echo [3/3] Deploying Living Arc Reactor Satellite HUD...
start "" python satellite_hud\satellite_app.py

echo.
echo ======================================================================
echo   Launching Z.A.I.N.E Terminal Operating Environment (TUI)
echo ======================================================================
echo.
python zaine_tui.py

if errorlevel 1 (
    echo.
    echo [ERROR] TUI exited with error code %errorlevel%.
    pause
)
