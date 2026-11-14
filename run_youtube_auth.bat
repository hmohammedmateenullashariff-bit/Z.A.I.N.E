@echo off
title Z.A.I.N.E - YouTube Authentication
cd /d "%~dp0"
if exist .venv\Scripts\python.exe (
    set PYTHON_CMD=.venv\Scripts\python.exe
) else (
    set PYTHON_CMD=python
)
echo ======================================================================
echo   Z.A.I.N.E - YouTube Studio OAuth2 Setup
echo ======================================================================
echo Using: %PYTHON_CMD%
%PYTHON_CMD% youtube_studio\setup_auth.py
pause

