# Zeigt Version, Dienststatus, Health-Check und die letzten Logs.
#
# Funktioniert sowohl in einer Paket-Installation (Programm- und Datenordner
# getrennt) als auch im Entwicklungsbetrieb, wo beides im Projektstamm liegt.

param(
    [string]$ServiceName = "Haushaltsfinanz",
    [string]$Programm    = "",
    [string]$Daten       = "",
    [string]$Port        = "",
    [int]$LogLines       = 30
)

. "$PSScriptRoot\pfade.ps1"

# ── Ablageorte bestimmen ─────────────────────────────────────────────────────
$regKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ServiceName"
$installedVersion = $null
if (Test-Path $regKey) {
    $reg = Get-ItemProperty $regKey -ErrorAction SilentlyContinue
    $installedVersion = $reg.DisplayVersion
    if (-not $Programm -and $reg.InstallLocation) { $Programm = $reg.InstallLocation }
    if (-not $Daten    -and $reg.DatenOrdner)     { $Daten    = $reg.DatenOrdner }
}
# Rueckfall fuer den Entwicklungsbetrieb: alles im Projektstamm
$stamm = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Programm = NormalisierePfad $Programm
$Daten    = NormalisierePfad $Daten
if (-not $Programm) { $Programm = $stamm }
if (-not $Daten)    { $Daten    = $stamm }

$current = Join-Path $Programm "current"

Write-Host "=== Installation ===" -ForegroundColor Cyan
if ($installedVersion) {
    Write-Host "  Version:  $installedVersion"
} else {
    Write-Host "  Kein Software-Eintrag - Entwicklungsbetrieb oder nicht installiert." -ForegroundColor Yellow
}
Write-Host "  Programm: $Programm"
if (IstJunction $current) {
    $ziel = JunctionZiel $current
    Write-Host "  current:  -> $(Split-Path $ziel -Leaf)" -ForegroundColor Gray
    $alle = Versionsordner $Programm
    if ($alle.Count -gt 1) {
        $andere = @($alle | Where-Object { $_.FullName.TrimEnd('\') -ine $ziel.TrimEnd('\') } | ForEach-Object { $_.Name })
        Write-Host "  daneben:  $($andere -join ', ')  (fuer Rollback)" -ForegroundColor Gray
    }
}
Write-Host "  Daten:    $Daten"

$protokoll = Join-Path $Programm "letztes-update.json"
if (Test-Path $protokoll) {
    try {
        $info = Get-Content $protokoll -Raw | ConvertFrom-Json
        Write-Host ""
        Write-Host "  Letztes Update: $($info.von_version) -> $($info.nach_version) am $($info.zeitpunkt)" -ForegroundColor Gray
        if ($info.schema_unveraendert) {
            Write-Host "    Schema unveraendert - Rollback waere verlustfrei." -ForegroundColor Green
        } else {
            Write-Host "    Schema geaendert ($($info.schema_vorher) -> $($info.schema_nachher))." -ForegroundColor Yellow
            Write-Host "    Rollback spielt die Datenbank zurueck: $($info.sicherung)" -ForegroundColor Yellow
        }
    } catch {}
}

# ── Port und Protokoll ───────────────────────────────────────────────────────
# Dieselbe Datei wie Dienst und Anwendung.
$schema = "http"
$cfgServer = Join-Path $Daten "config\server.json"
if (-not (Test-Path $cfgServer)) { $cfgServer = Join-Path $Daten "server.json" }
if (Test-Path $cfgServer) {
    try {
        $srv = Get-Content $cfgServer -Raw | ConvertFrom-Json
        if (-not $Port -and $srv.port) { $Port = "$($srv.port)" }
        if ($srv.https -and $srv.https.aktiviert) {
            $schema = "https"
            $Port = "$($srv.https.port)"
        }
    } catch { }
}
if (-not $Port) { $Port = "8000" }

Write-Host "`n=== Dienststatus ===" -ForegroundColor Cyan
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc) {
    $color = if ($svc.Status -eq 'Running') { 'Green' } else { 'Red' }
    Write-Host "  $ServiceName : $($svc.Status)" -ForegroundColor $color
} else {
    Write-Host "  Dienst '$ServiceName' nicht gefunden." -ForegroundColor Yellow
}

Write-Host "`n=== Health-Check ===" -ForegroundColor Cyan
try {
    $resp = HealthAbfrage "${schema}://localhost:$Port/api/health" -TimeoutSec 5
    Write-Host "  OK - $($resp | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "  FEHLER: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Haeufige Ursache: der Dienst verweigert den Start wegen einer" -ForegroundColor Yellow
    Write-Host "  Schema-Abweichung. Die Logs unten nennen dann, was zu tun ist." -ForegroundColor Yellow
}

Write-Host "`n=== Letzte $LogLines Log-Zeilen ===" -ForegroundColor Cyan
$logDir = Join-Path $Daten "logs"
$logFile = Join-Path $logDir "backend.log"
if (-not (Test-Path $logFile)) {
    # WinSW benennt die Dateien nach der Dienst-ID
    $logFile = Get-ChildItem $logDir -Filter "*.out.log" -ErrorAction SilentlyContinue |
               Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
if ($logFile -and (Test-Path $logFile)) {
    Write-Host "  ($logFile)" -ForegroundColor DarkGray
    Get-Content $logFile -Tail $LogLines
} else {
    Write-Host "  Keine Log-Datei gefunden in $logDir" -ForegroundColor Yellow
}

$errFile = Get-ChildItem $logDir -Filter "*err*.log" -ErrorAction SilentlyContinue |
           Where-Object { $_.Length -gt 0 } | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if ($errFile) {
    Write-Host "`n=== Fehlerprotokoll (letzte 20 Zeilen) ===" -ForegroundColor Cyan
    Write-Host "  ($($errFile.FullName))" -ForegroundColor DarkGray
    Get-Content $errFile.FullName -Tail 20
}
