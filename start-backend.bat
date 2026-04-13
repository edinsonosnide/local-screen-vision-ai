@echo off
cd /d "%~dp0backend"

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: .venv not found. Run setup first:
    echo   cd backend
    echo   python -m venv .venv
    echo   .venv\Scripts\activate
    echo   pip install -r requirements.txt
    pause
    exit /b 1
)

echo Starting backend...
call .venv\Scripts\activate.bat
python main.py
pause
