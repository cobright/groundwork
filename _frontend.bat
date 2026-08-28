@echo off
cd /d "%~dp0frontend"
echo Frontend dev server starting...   (close this window to stop)
call npm run dev
pause
