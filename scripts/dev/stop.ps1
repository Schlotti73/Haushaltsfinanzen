# Beendet uvicorn (Port 8000) und Vite (Port 5173)
$ports = @(8000, 5173)
foreach ($port in $ports) {
    $pids = netstat -ano | Select-String ":$port\s" | ForEach-Object {
        ($_ -split '\s+')[-1]
    } | Sort-Object -Unique
    foreach ($pid in $pids) {
        if ($pid -match '^\d+$' -and $pid -ne '0') {
            try {
                Stop-Process -Id $pid -Force -ErrorAction Stop
                Write-Host "Port $port (PID $pid) beendet." -ForegroundColor Green
            } catch {
                Write-Host "Port $port (PID $pid): $($_.Exception.Message)" -ForegroundColor Yellow
            }
        }
    }
}
Write-Host "Fertig." -ForegroundColor Cyan
