# Gibt die Dev-Ports 8000 (Backend) und 5173 (Frontend) im Heimnetz frei.
# Ausfuehren als Administrator!

param(
    [int[]]$Ports = @(8000, 5173)
)

$ErrorActionPreference = "Stop"

foreach ($port in $Ports) {
    $name = "Haushaltsfinanz Dev :$port"
    if (Get-NetFirewallRule -DisplayName $name -ErrorAction SilentlyContinue) {
        Write-Host "Regel '$name' existiert bereits." -ForegroundColor Yellow
        continue
    }
    New-NetFirewallRule -DisplayName $name `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $port `
        -Profile Private | Out-Null
    Write-Host "Firewall-Regel '$name' angelegt (Profil: Privat)." -ForegroundColor Green
}

$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1"
} | Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "Fertig. Vom Smartphone im selben WLAN testen:" -ForegroundColor Cyan
if ($ip) {
    Write-Host "  http://$ip`:5173" -ForegroundColor Green
} else {
    Write-Host "  http://<PC-IP>:5173  (IP per 'ipconfig' ermitteln)" -ForegroundColor Green
}
