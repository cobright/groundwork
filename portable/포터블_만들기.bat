@echo off
chcp 65001 >nul
title Build Portable Package
echo Building portable package. Internet required. Please wait...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_build_portable.ps1"
echo.
pause
