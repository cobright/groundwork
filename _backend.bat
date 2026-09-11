@echo off
cd /d "%~dp0backend"
echo Backend running at http://127.0.0.1:8000   (close this window to stop)
rem No --reload here: this is how users run the app, not how we develop it.
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
pause
