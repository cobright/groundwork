@echo off
chcp 65001 >nul
title Haengjeong Workbench
cd /d "%~dp0backend"
"%~dp0python\python.exe" run.py
echo.
echo (Server stopped. You can close this window.)
pause >nul
