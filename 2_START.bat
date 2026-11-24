@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "backend\.venv\Scripts\python.exe" goto needSetup
if not exist "frontend\node_modules" goto needSetup
echo Starting backend and frontend in separate windows...
start "Groundwork Backend" "%~dp0_backend.bat"
start "Groundwork Frontend" "%~dp0_frontend.bat"
echo Waiting for the servers to warm up...
timeout /t 6 >nul
start "" "http://localhost:5173"
echo.
echo Two windows opened: Backend (8000) and Frontend (5173).
echo Close those two windows to stop the app.
exit /b 0

:needSetup
echo [Error] Setup not done yet. Run 1_SETUP.bat first.
pause
exit /b 1
