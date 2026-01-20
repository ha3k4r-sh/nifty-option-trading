@echo off
REM Nifty Option Trading - Windows Startup Script
REM No virtual environment - uses system Python

echo ================================================
echo       Nifty Option Trading - Starting...
echo ================================================

cd /d "%~dp0backend"

REM Create required directories
if not exist cache mkdir cache
if not exist data mkdir data
if not exist logs mkdir logs

REM Install dependencies (system-wide)
echo Installing dependencies...
pip install -r requirements.txt -q

echo.
echo ================================================
echo   Server starting at http://localhost:8000
echo   Login: http://localhost:8000/login
echo   Credentials: admin / admin
echo ================================================
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
