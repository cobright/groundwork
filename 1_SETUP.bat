@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ================================
echo   AI Workbench - first-time setup
echo ================================
echo.
set "PYCMD="
py -3.14 --version >nul 2>nul && set "PYCMD=py -3.14"
if not defined PYCMD ( py -3 --version >nul 2>nul && set "PYCMD=py -3" )
if not defined PYCMD ( py --version >nul 2>nul && set "PYCMD=py" )
if not defined PYCMD ( python --version >nul 2>nul && set "PYCMD=python" )
if not defined PYCMD goto noPython
echo Using Python launcher: %PYCMD%
echo.
cd backend
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYCMD% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" goto venvFail
echo Installing backend packages ^(this may take a minute^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto pipFail
if not exist ".env" ( if exist ".env.example" copy ".env.example" ".env" >nul )
cd ..
echo.
echo Installing frontend packages ^(npm^)...
cd frontend
call npm install
if errorlevel 1 goto npmFail
cd ..
echo.
echo ================================
echo   Setup complete.
echo   Next: double-click  2_START.bat
echo ================================
pause
exit /b 0

:noPython
echo [Error] Python not found via "py" or "python". Install Python 3 first.
pause
exit /b 1
:venvFail
echo [Error] Could not create the virtual environment.
pause
exit /b 1
:pipFail
echo [Error] Backend package install failed. See the messages above.
pause
exit /b 1
:npmFail
echo [Error] npm install failed. Is Node.js installed and on PATH?
pause
exit /b 1
