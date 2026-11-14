# Startet Backend + Frontend, bleibt aktiv solange der Dev-Server laeuft
# und beendet beide Prozesse nach Bestaetigung (ENTER) wieder.
#
#   -Reload   $true  (Standard) – uvicorn mit --reload (Auto-Restart bei Dateiänderungen)
#   -Reload   $false            – kein --reload (Debugger-kompatibel, kein Reloader-Kindprozess)

param(
    [bool]$Reload = $true
)

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

function Stop-Port([int]$port) {
    $procIds = netstat -ano | Select-String ":$port\s" | ForEach-Object {
        ($_ -split '\s+')[-1]
    } | Sort-Object -Unique
    foreach ($procId in $procIds) {
        if ($procId -match '^\d+$' -and $procId -ne '0') {
            try {
                Stop-Process -Id $procId -Force -ErrorAction Stop
                Write-Host "  Port $port (PID $procId) beendet." -ForegroundColor Gray
            } catch {}
        }
    }
}

Write-Host "Pruefe auf laufende Instanzen..." -ForegroundColor Yellow
Stop-Port 8000
Stop-Port 5173
Start-Sleep -Seconds 1

$reloadFlag = if ($Reload) { "--reload" } else { "" }
$reloadLabel = if ($Reload) { " [--reload]" } else { " [kein Reload, Debugger-kompatibel]" }

Write-Host "Starte Backend (Port 8000)$reloadLabel..." -ForegroundColor Cyan
$backend = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'Haushaltsfinanzen - Backend :8000$reloadLabel'; " +
    "Set-Location '$root\backend'; " +
    ".venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 $reloadFlag".Trim()
) -WindowStyle Normal -PassThru

Start-Sleep -Seconds 2

Write-Host "Starte Frontend (Port 5173)..." -ForegroundColor Cyan
$frontend = Start-Process -FilePath "powershell" -ArgumentList @(
    "-NoExit", "-Command",
    "`$host.UI.RawUI.WindowTitle = 'Haushaltsfinanzen - Frontend :5173'; " +
    "Set-Location '$root\frontend'; " +
    "node node_modules\vite\bin\vite.js --port 5173 --host"
) -WindowStyle Normal -PassThru

Write-Host ""
Write-Host "OK  Backend:  http://localhost:8000" -ForegroundColor Green
Write-Host "OK  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host ""
Write-Host "Dev-Server laeuft. ENTER druecken, um beide Server zu beenden..." -ForegroundColor Yellow
Read-Host | Out-Null

Write-Host ""
Write-Host "Beende Dev-Server..." -ForegroundColor Cyan

foreach ($proc in @($backend, $frontend)) {
    if ($proc -and -not $proc.HasExited) {
        try {
            Start-Process -FilePath "taskkill" -ArgumentList "/PID $($proc.Id) /T /F" -WindowStyle Hidden -Wait
        } catch {}
    }
}

# Sicherheitsnetz: falls Reloader-Kindprozesse die Ports noch halten
Stop-Port 8000
Stop-Port 5173

Write-Host "Dev-Server beendet." -ForegroundColor Green
