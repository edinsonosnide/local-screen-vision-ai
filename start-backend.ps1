# Run this from the project root to start the backend with the correct venv
Set-Location "$PSScriptRoot\backend"

if (-not (Test-Path ".venv\Scripts\activate")) {
    Write-Host "ERROR: .venv not found. Run setup first:" -ForegroundColor Red
    Write-Host "  cd backend" -ForegroundColor Yellow
    Write-Host "  python -m venv .venv" -ForegroundColor Yellow
    Write-Host "  .venv\Scripts\activate" -ForegroundColor Yellow
    Write-Host "  pip install -r requirements.txt" -ForegroundColor Yellow
    exit 1
}

Write-Host "Activating venv and starting backend..." -ForegroundColor Cyan
& ".venv\Scripts\activate.ps1"
python main.py
