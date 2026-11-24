@echo off
chcp 65001 >nul
title Groundwork
cd /d "%~dp0backend"
"%~dp0python\python.exe" run.py
echo.
echo (Server stopped. You can close this window.)
pause >nul
