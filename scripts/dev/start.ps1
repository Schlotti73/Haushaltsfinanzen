# Startet Backend (uvicorn) und Frontend (Vite) – beendet vorherige Instanzen zuerst
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

# Vorhandene Instanzen beenden
Write-Host "Prüfe auf laufende Instanzen..." -ForegroundColor Yellow
foreach ($port in @(8000, 5173)) {
    $pids = netstat -ano | Select-String ":$port\s" | ForEach-Object {
        ($_ -split '\s+')[-1]
    } | Sort-Object -Unique
    foreach ($procId in $pids) {
        if ($procId -match '^\d+$' -and $procId -ne '0') {
            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host "  Port $port (PID $procId) beendet." -ForegroundColor Gray
            } catch {}
        }
    }
}

Start-Sleep -Seconds 1

# Backend starten
Write-Host "Starte Backend (Port 8000)..." -ForegroundColor Cyan
Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'Haushaltsfinanzen – Backend :8000'; " +
    "Set-Location '$root\backend'; " +
    ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
) -WindowStyle Normal

Start-Sleep -Seconds 2

# Frontend starten
Write-Host "Starte Frontend (Port 5173)..." -ForegroundColor Cyan
Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'Haushaltsfinanzen – Frontend :5173'; " +
    "Set-Location '$root\frontend'; " +
    "node node_modules\vite\bin\vite.js --port 5173 --host"
) -WindowStyle Normal

Write-Host ""
Write-Host "OK  Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "OK  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host ""
Write-Host "Stoppen: scripts\dev\stop.ps1" -ForegroundColor Gray
