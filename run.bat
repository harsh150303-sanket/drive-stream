@echo off
setlocal
cd /d "%~dp0"
if not exist .venv (
  echo Creating Python virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (echo Python 3 was not found. Install Python 3.10+ and try again.&pause&exit /b 1)
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if not exist .env copy .env.example .env >nul
start "DriveStream Server" /b cmd /c "python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000"
timeout /t 2 /nobreak >nul
start "" http://localhost:8000/
echo DriveStream is running at http://localhost:8000/
pause
