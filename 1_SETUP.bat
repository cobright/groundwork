@echo off
setlocal EnableExtensions
cd /d "%~dp0"
echo ================================
echo   Groundwork - first-time setup
echo ================================
echo.
set "PYCMD="
py -3.12 --version >nul 2>nul && set "PYCMD=py -3.12"
if not defined PYCMD ( py -3.11 --version >nul 2>nul && set "PYCMD=py -3.11" )
if not defined PYCMD ( py -3.13 --version >nul 2>nul && set "PYCMD=py -3.13" )
if not defined PYCMD ( py -3 --version >nul 2>nul && set "PYCMD=py -3" )
if not defined PYCMD ( py --version >nul 2>nul && set "PYCMD=py" )
if not defined PYCMD ( python --version >nul 2>nul && set "PYCMD=python" )
if not defined PYCMD goto noPython
echo Using Python launcher: %PYCMD%
echo.
cd backend

call :buildvenv
if errorlevel 1 (
  echo.
  echo The environment did not pass the import check. Rebuilding from scratch...
  if exist ".venv" rmdir /s /q ".venv"
  call :buildvenv
  if errorlevel 1 goto envFail
)

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

:buildvenv
rem Creates .venv, installs packages, and proves that they really load.
rem A venv left over from another Python version is removed instead of reused.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys" >nul 2>nul
  if errorlevel 1 (
    echo Existing virtual environment is broken. Removing it...
    rmdir /s /q ".venv"
  )
)
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  %PYCMD% -m venv .venv
)
if not exist ".venv\Scripts\python.exe" (
  echo [Error] Could not create the virtual environment.
  exit /b 1
)
echo Installing backend packages ^(this may take a minute^)...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [Error] Backend package install failed. See the messages above.
  exit /b 1
)
echo Checking that the packages actually load...
".venv\Scripts\python.exe" -c "import fastapi, pydantic, httpx, dotenv, docx, openpyxl, pypdf, defusedxml"
if errorlevel 1 exit /b 1
echo Backend environment OK.
exit /b 0

:noPython
echo [Error] Python not found via "py" or "python". Install Python 3 first.
echo         Use an installer from python.org ^(3.11 or 3.12 recommended^).
pause
exit /b 1
:envFail
echo.
echo [Error] The backend packages still fail to import.
echo         Delete the folder  backend\.venv  by hand and run this file again.
echo         If it keeps failing, install Python 3.12 from python.org and retry.
pause
exit /b 1
:npmFail
echo [Error] npm install failed. Is Node.js installed and on PATH?
pause
exit /b 1
