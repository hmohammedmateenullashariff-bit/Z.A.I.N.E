@echo off
title Z.A.I.N.E System - Terminal Agent Environment
cd /d "%~dp0"
echo ======================================================================
echo   Z.A.I.N.E - Autonomous Sovereign AI Assistant
echo   Terminal-First Agentic Operating Environment
echo ======================================================================
echo [1] Primary UI:       Interactive Terminal Agent (TUI)
echo [2] Core Service:     Headless Multi-Threaded Daemon (127.0.0.1:7860)
echo [3] Voice Protocol:   Command-Gated (Default: OFF, Use /voice on or /speak)
echo [4] Pocket Zaine:     Telegram Remote Gateway
echo [5] Memory Engine:    SQLite FTS5 + Obsidian Durable Vault
echo ======================================================================
echo.
set OLLAMA_MODELS=D:\ollama\models
python main.py
if errorlevel 1 (
    echo.
    echo [ERROR] Zaine encountered an unexpected exit.
    pause
)
