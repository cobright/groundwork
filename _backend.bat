@echo off
cd /d "%~dp0backend"
echo Backend running at http://127.0.0.1:8000   (close this window to stop)
".venv\Scripts\python.exe" -m uvicorn app.main:app --reload --port 8000
pause
