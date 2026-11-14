# Registriert die taegliche Backup-Aufgabe im Windows-Aufgabenplaner.
# Liest Standardwerte aus backup.json im Einstellungsordner; Parameter
# ueberschreiben sie.
#
# Die Aufgabe ruft nicht direkt python.exe auf, sondern einen generierten
# Wrapper <Programm>\dienst\backup.cmd. Zwei Gruende:
#   * Der Aufgabenplaner kann keine Umgebungsvariablen setzen, backup.py
#     braucht aber FINANZ_DATEN_DIR, um die richtige Datenbank zu finden.
#   * Der Wrapper zeigt auf current\, nicht auf einen Versionsordner - sonst
#     waere die Aufgabe nach dem naechsten Update kaputt.

param(
    [string]$TaskName   = "",
    [string]$Zeit       = "",
    [string]$ZielOrdner = "",
    [string]$Programm   = "",
    [string]$Daten      = "",
    [string]$ServiceName = "Haushaltsfinanz"
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\pfade.ps1"

# ── Ablageorte ───────────────────────────────────────────────────────────────
$regKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ServiceName"
if (Test-Path $regKey) {
    $reg = Get-ItemProperty $regKey -ErrorAction SilentlyContinue
    if (-not $Programm -and $reg.InstallLocation) { $Programm = $reg.InstallLocation }
    if (-not $Daten    -and $reg.DatenOrdner)     { $Daten    = $reg.DatenOrdner }
}
$stamm = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$Programm = NormalisierePfad $Programm
$Daten    = NormalisierePfad $Daten
if (-not $Programm) { $Programm = $stamm }
if (-not $Daten)    { $Daten    = $stamm }

# In einer Paket-Installation laeuft alles ueber die Junction; im
# Entwicklungsbetrieb gibt es keine, dann gilt der Projektstamm.
$current = Join-Path $Programm "current"
$basis   = if (IstJunction $current) { $current } else { $stamm }

$cfgDir  = Join-Path $Daten "config"
if (-not (Test-Path $cfgDir)) { $cfgDir = Join-Path $stamm "config" }
$cfgPath = Join-Path $cfgDir "backup.json"
$python  = Join-Path $basis "backend\.venv\Scripts\python.exe"
$skript  = Join-Path $basis "scripts\backup.py"

# ── Einstellungen ────────────────────────────────────────────────────────────
$cfg = @{ task_name = "HaushaltsfinanzBackup"; uhrzeit = "02:00"; ziel_ordner = "" }
if (Test-Path $cfgPath) {
    try {
        $json = Get-Content $cfgPath -Raw | ConvertFrom-Json
        if ($json.task_name)   { $cfg.task_name   = $json.task_name   }
        if ($json.uhrzeit)     { $cfg.uhrzeit     = $json.uhrzeit     }
        if ($json.ziel_ordner) { $cfg.ziel_ordner = $json.ziel_ordner }
    } catch {
        Write-Host "WARNUNG: $cfgPath konnte nicht gelesen werden." -ForegroundColor Yellow
    }
}

# Explizite Parameter haben Vorrang
if ($TaskName)   { $cfg.task_name   = $TaskName   }
if ($Zeit)       { $cfg.uhrzeit     = $Zeit       }
if ($ZielOrdner) { $cfg.ziel_ordner = $ZielOrdner }

if (-not (Test-Path $python)) {
    Write-Error "Python-Umgebung nicht gefunden: $python"
    exit 1
}

# ── Wrapper schreiben ────────────────────────────────────────────────────────
$wrapperDir = if (IstJunction $current) { Join-Path $Programm "dienst" } else { Join-Path $stamm "logs" }
New-Item -ItemType Directory -Force $wrapperDir | Out-Null
$wrapper = Join-Path $wrapperDir "backup.cmd"

$zielArg = if ($cfg.ziel_ordner) { " --ziel `"$($cfg.ziel_ordner)`"" } else { "" }
@"
@echo off
rem Von scripts\prod\register_backup_task.ps1 erzeugt - nicht von Hand aendern.
rem Setzt die Umgebung, die der Aufgabenplaner selbst nicht setzen kann.
set "FINANZ_DATEN_DIR=$Daten"
set "PYTHONPATH=$basis\backend"
set "TESSDATA_PREFIX=$basis\backend\tessdata"
"$python" "$skript"$zielArg
exit /b %ERRORLEVEL%
"@ | Out-File $wrapper -Encoding ascii

# ── Aufgabe registrieren ─────────────────────────────────────────────────────
$action = New-ScheduledTaskAction -Execute $wrapper -WorkingDirectory $wrapperDir
$trigger = New-ScheduledTaskTrigger -Daily -At $cfg.uhrzeit
$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable:$false
$principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest

Register-ScheduledTask `
    -TaskName $cfg.task_name `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description "Taegliches Backup der Haushaltsfinanz-Datenbank und Belege" `
    -Force | Out-Null

Write-Host "Backup-Aufgabe '$($cfg.task_name)' registriert (taeglich um $($cfg.uhrzeit))." -ForegroundColor Green
Write-Host "  Startet:    $wrapper" -ForegroundColor Gray
if ($cfg.ziel_ordner) {
    Write-Host "  Zielordner: $($cfg.ziel_ordner)"
    if ($cfg.ziel_ordner -match '^\\\\') {
        Write-Host ""
        Write-Host "  Netzwerkziel: Zugangsdaten werden mit DPAPI unter dem Benutzer" -ForegroundColor Yellow
        Write-Host "  verschluesselt, der sie setzt. Die Aufgabe laeuft als SYSTEM -" -ForegroundColor Yellow
        Write-Host "  ein unter einem anderen Konto gesetztes Passwort laesst sich dort" -ForegroundColor Yellow
        Write-Host "  nicht entschluesseln, und das Backup scheitert stumm." -ForegroundColor Yellow
        Write-Host "  Passwort als SYSTEM setzen, z. B. mit PsExec:" -ForegroundColor Yellow
        Write-Host "    psexec -s -i `"$python`" `"$basis\scripts\netzlaufwerk.py`" --passwort-setzen" -ForegroundColor Gray
    }
} else {
    Write-Host "  Zielordner: $Daten\backups (Standard)"
}
Write-Host "  Pruefen:    Get-ScheduledTask -TaskName '$($cfg.task_name)'"
