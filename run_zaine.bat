@echo off
title Z.A.I.N.E System - Sovereign AI Assistant
cd /d "%~dp0"
echo ======================================================================
echo   Z.A.I.N.E - Autonomous Sovereign AI Assistant
echo ======================================================================
echo [1] Wake-Word Voice: Speak "Zaine" to talk
echo [2] Holographic HUD: Launching at http://127.0.0.1:7860
echo [3] Pocket Zaine:    Connected to Telegram (@Zaine_mateen_bot)
echo [4] YouTube Studio:  Autonomous 5-slot pipeline running in background
echo ======================================================================
echo.
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Zaine encountered an unexpected exit.
    pause
)
