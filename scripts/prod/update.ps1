# Update aus einem Release-Paket.
#
# Der teure Teil (Entpacken, Python-Umgebung aufbauen) laeuft, WAEHREND der
# Dienst noch die alte Version bedient. Gestoppt wird nur fuer Backup,
# Migration und das Umlegen der Junction - die Ausfallzeit bleibt bei Sekunden.
# Scheitert etwas davor, laeuft die alte Version einfach weiter.
#
#   .\update.ps1 -Paket D:\Austausch\Haushaltsfinanz_v1.5.0.zip
#   .\update.ps1 -Paket \\dein-pc\releases\Haushaltsfinanz_v1.5.0.zip
#   .\update.ps1 -Ordner D:\Austausch\Haushaltsfinanz_v1.5.0   (entpacktes Paket)
#   .\update.ps1 -AusUpdates                 (neueste ZIP aus <Daten>\updates)
#
# Die beiden letzten Formen bedient update.cmd - der Doppelklick-Weg.

[CmdletBinding(DefaultParameterSetName = "Zip")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Zip", Position = 0)][string]$Paket,
    # Ein bereits entpacktes Paket: der Ordner IST die Quelle, es wird nichts
    # ein zweites Mal entpackt. So ruft die update.cmd im Paketstamm an.
    [Parameter(Mandatory = $true, ParameterSetName = "Ordner")][string]$Ordner,
    # Die neueste ZIP aus <Daten>\updates nehmen - dorthin laedt die Anwendung.
    # So ruft der erzeugte Starter im Programmordner an.
    [Parameter(Mandatory = $true, ParameterSetName = "AusUpdates")][switch]$AusUpdates,
    [string]$Programm    = "",
    [string]$Daten       = "",
    [string]$ServiceName = "Haushaltsfinanz",
    [int]$BehalteVersionen = 2
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\pfade.ps1"

if (-not (IstAdmin)) {
    Write-Host "Keine Adminrechte - starte neu als Administrator…" -ForegroundColor Yellow
    $shell = if (Cmd "pwsh") { "pwsh" } else { "powershell" }
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"",
                 "-ServiceName", "`"$ServiceName`"")
    # Die Quelle muss mit, sonst steht der erhoehte Neustart ohne Paket da.
    switch ($PSCmdlet.ParameterSetName) {
        "Ordner"     { $argList += @("-Ordner", "`"$Ordner`"") }
        "AusUpdates" { $argList += "-AusUpdates" }
        default      { $argList += @("-Paket", "`"$Paket`"") }
    }
    if ($Programm) { $argList += @("-Programm", "`"$Programm`"") }
    if ($Daten)    { $argList += @("-Daten", "`"$Daten`"") }
    # -PassThru und .ExitCode, nicht $LASTEXITCODE: der bezieht sich allein auf
    # native Aufrufe im EIGENEN Prozess. Ohne das meldete ein gescheitertes
    # Update nach aussen Erfolg.
    $p = Start-Process $shell -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $p.ExitCode
}

$script:winsw = $null
function Abort([string]$msg) {
    Write-Host "`nFEHLER: $msg" -ForegroundColor Red
    if ($script:winsw -and (Test-Path $script:winsw.Xml)) {
        Write-Host "Stelle den laufenden Zustand wieder her…" -ForegroundColor Yellow
        & $script:winsw.Exe start $script:winsw.Xml 2>$null
    }
    exit 1
}

# Die entpackte Quelle wegraeumen - ausser sie wurde mit -Ordner uebergeben.
# Dann gehoert sie dem Aufrufer, und das Update loeschte sonst den Ordner, aus
# dem es gerade laeuft.
function RaeumeQuelle([string]$pfad, [bool]$behalten) {
    if (-not $behalten -and $pfad) {
        Remove-Item $pfad -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ── 1. Installation finden ───────────────────────────────────────────────────
$regKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ServiceName"
if (Test-Path $regKey) {
    $reg = Get-ItemProperty $regKey
    if (-not $Programm -and $reg.InstallLocation) { $Programm = $reg.InstallLocation }
    if (-not $Daten    -and $reg.DatenOrdner)     { $Daten    = $reg.DatenOrdner }
    $alteVersion = $reg.DisplayVersion
}
$Programm = NormalisierePfad $Programm
$Daten    = NormalisierePfad $Daten
if (-not $Programm) { $Programm = $StandardProgramm }
if (-not $Daten)    { $Daten    = $StandardDaten }

# -AusUpdates: die Anwendung legt geladene Pakete unter <Daten>\updates ab und
# raeumt aeltere dort selbst weg - im Normalfall liegt also genau eines da.
# Eine Auswahlliste waere doppelt: weiter unten stehen Installiert/Paket
# gegenueber und es wird ohnehin mit [J/N] zurueckgefragt.
if ($AusUpdates) {
    $updateOrdner = Join-Path $Daten "updates"
    $neuestes = @(Get-ChildItem (Join-Path $updateOrdner "*.zip") -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending) | Select-Object -First 1
    if (-not $neuestes) {
        Abort @"
Kein Paket unter $updateOrdner gefunden.
  Abhilfe: in der Anwendung unter Einstellungen > Programm-Update herunterladen,
           oder eine ZIP-Datei auf update.cmd ziehen.
"@
    }
    $Paket = $neuestes.FullName
}

$current = Join-Path $Programm "current"
$script:winsw = WinswPfade $Programm

if (-not (Test-Path $current)) {
    Abort @"
Keine Installation unter $Programm gefunden.
  Fuer die Erstinstallation das Paket entpacken und setup.cmd starten.
"@
}
$alterOrdner = JunctionZiel $current
if (-not $alterOrdner) { Abort "$current ist keine Junction - bitte von Hand pruefen." }
if (-not $alteVersion) { $alteVersion = LeseVersion $alterOrdner }

# ── 2. Paket bereitstellen ───────────────────────────────────────────────────
# $tmp ist in beiden Faellen der entpackte Paketinhalt. Bei -Ordner zeigt er
# auf die uebergebene Quelle und darf darum nicht geloescht werden.
$quelleBehalten = $false

if ($Ordner) {
    $aufgeloest = Resolve-Path -LiteralPath $Ordner -ErrorAction SilentlyContinue
    if (-not $aufgeloest) { Abort "Ordner nicht gefunden: $Ordner" }
    $tmp = $aufgeloest.Path
    $quelleBehalten = $true
    Step "Benutze das entpackte Paket unter $tmp"
    Get-ChildItem $tmp -Recurse -File -Include *.ps1,*.psm1,*.cmd | Unblock-File -ErrorAction SilentlyContinue
} else {
    if (-not (Test-Path $Paket)) { Abort "Paket nicht gefunden: $Paket" }

    Step "Entpacke Paket…"
    $tmp = Join-Path ([System.IO.Path]::GetTempPath()) "hf-update-$(Get-Date -Format 'yyyyMMdd-HHmmss')"
    New-Item -ItemType Directory -Force $tmp | Out-Null
    try {
        # Unblock-File: ein Paket vom Netzlaufwerk oder aus dem Download tragt
        # Mark-of-the-Web, PowerShell verweigert die enthaltenen Skripte sonst.
        Unblock-File $Paket -ErrorAction SilentlyContinue
        Expand-Archive -Path $Paket -DestinationPath $tmp -Force
    } catch {
        Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
        Abort "Paket konnte nicht entpackt werden: $_"
    }
    Get-ChildItem $tmp -Recurse -File -Include *.ps1,*.psm1,*.cmd | Unblock-File -ErrorAction SilentlyContinue
}

$versionsDatei = Join-Path $tmp "VERSION"
if (-not (Test-Path $versionsDatei)) {
    RaeumeQuelle $tmp $quelleBehalten
    Abort "Das Paket hat keine VERSION-Datei - es ist kein Release-Paket."
}
$neueVersion = (Get-Content $versionsDatei -Raw).Trim()
$wheels = Join-Path $tmp "wheels"
if (-not (Test-Path $wheels)) {
    RaeumeQuelle $tmp $quelleBehalten
    Abort "Dem Paket fehlt wheels\ - ohne Internet nicht installierbar. Paket neu erstellen."
}

Write-Host ""
Write-Host "  Installiert:  $alteVersion" -ForegroundColor Gray
Write-Host "  Paket:        $neueVersion" -ForegroundColor Cyan
Write-Host "  Programm:     $Programm"
Write-Host "  Daten:        $Daten   (bleibt unberuehrt)" -ForegroundColor Green
Write-Host ""

$zielVersion = Join-Path $Programm "versionen\$neueVersion"
if ($neueVersion -eq $alteVersion) {
    Write-Host "  HINWEIS: Diese Version laeuft bereits." -ForegroundColor Yellow
}
$confirm = Read-Host "  Update einspielen? [J/N]"
if ($confirm -notmatch "^[JjYy]") {
    RaeumeQuelle $tmp $quelleBehalten
    Write-Host "Abgebrochen." -ForegroundColor Yellow; exit 0
}

# ── 3. Neue Version aufbauen - Dienst laeuft weiter ──────────────────────────
Step "Lege versionen\$neueVersion an… (der Dienst bedient weiter $alteVersion)"
if (Test-Path $zielVersion) {
    if ($zielVersion.TrimEnd('\') -ieq $alterOrdner.TrimEnd('\')) {
        RaeumeQuelle $tmp $quelleBehalten
        Abort "versionen\$neueVersion ist die gerade laufende Version. Zum Neuaufbau erst auf eine andere Version wechseln."
    }
    Remove-Item $zielVersion -Recurse -Force
}
New-Item -ItemType Directory -Force $zielVersion | Out-Null
Copy-Item "$tmp\*" $zielVersion -Recurse -Force
RaeumeQuelle $tmp $quelleBehalten

$pyZiel = "3.11"
$pyZielExe = FindPython $pyZiel
if (-not $pyZielExe) { Abort "Python $pyZiel nicht gefunden - install_service.ps1 ausfuehren." }

$venv   = Join-Path $zielVersion "backend\.venv"
$python = Join-Path $venv "Scripts\python.exe"

Step "Baue Python-Umgebung offline aus wheels\…"
& $pyZielExe -m venv $venv
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) { Abort "venv konnte nicht angelegt werden" }
& $python -m pip install --no-index --find-links (Join-Path $zielVersion "wheels") `
    -r (Join-Path $zielVersion "backend\requirements.txt") -q
if ($LASTEXITCODE -ne 0) { Abort "Installation aus wheels\ fehlgeschlagen - Paket unvollstaendig." }

# Ab hier laufen alle Python-Aufrufe gegen die echten Daten.
$env:FINANZ_DATEN_DIR = $Daten
$env:TESSDATA_PREFIX  = Join-Path $zielVersion "backend\tessdata"
Remove-Item Env:\FINANZ_AUTO_MIGRATE -ErrorAction SilentlyContinue

$revVorher = AlembicRevision $python $zielVersion
Write-Host "  Schema vor dem Update: $(if ($revVorher) { $revVorher } else { '(unbekannt)' })" -ForegroundColor Gray

# ── 4. Umschalten - ab hier ist der Dienst kurz aus ─────────────────────────
Step "Stoppe Dienst '$ServiceName'…"
& $script:winsw.Exe stop $script:winsw.Xml
if ($LASTEXITCODE -ne 0) { Abort "Dienst konnte nicht gestoppt werden" }

Step "Pflicht-Backup der Datenbank…"
$dbPfad = Join-Path $Daten "finanzen.db"
$sicherung = ""
if (Test-Path $dbPfad) {
    $backupDir = Join-Path $Daten "backups"
    New-Item -ItemType Directory -Force $backupDir | Out-Null
    $sicherung = Join-Path $backupDir "vor-$neueVersion`_von-$alteVersion`_$(Get-Date -Format 'yyyyMMdd-HHmm').db"
    Copy-Item $dbPfad $sicherung -Force
    # WAL-Dateien mitnehmen: ohne sie fehlen die letzten Transaktionen.
    foreach ($suffix in @("-wal", "-shm")) {
        if (Test-Path "$dbPfad$suffix") { Copy-Item "$dbPfad$suffix" "$sicherung$suffix" -Force }
    }
    Write-Host "  $sicherung" -ForegroundColor Gray
} else {
    Write-Host "  Keine Datenbank unter $dbPfad - nichts zu sichern." -ForegroundColor Yellow
}

Step "Datenbank-Migration…"
$seed = Join-Path $zielVersion "scripts\prod\seed_admin.py"
$env:PYTHONPATH = Join-Path $zielVersion "backend"
$dbOutput = & $python $seed
if ($LASTEXITCODE -ne 0) {
    Write-Host ($dbOutput -join "`n") -ForegroundColor Red
    Abort @"
Migration fehlgeschlagen. Es wurde nichts umgeschaltet - die alte Version
  ($alteVersion) laeuft weiter, sobald der Dienst wieder startet.
  Die Datenbank liegt unveraendert vor; Sicherung: $sicherung
"@
}
$dbOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
$revNachher = ($dbOutput | Where-Object { $_ -match "^ALEMBIC_REV=" }) -replace "^ALEMBIC_REV=", ""

Step "Lege current auf versionen\$neueVersion um…"
try { SetzeJunction $current $zielVersion } catch { Abort "$_" }

# Was ein Rollback zurueckzulegen hat. Ohne diese Datei muesste rollback.ps1
# raten, welche Sicherung zu welcher Version gehoert.
$schemaGleich = ($revVorher -and $revNachher -and $revVorher -eq $revNachher)
@{
    zeitpunkt     = (Get-Date).ToString("s")
    von_version   = $alteVersion
    nach_version  = $neueVersion
    von_ordner    = $alterOrdner
    nach_ordner   = $zielVersion
    datenbank     = $dbPfad
    sicherung     = $sicherung
    schema_vorher = $revVorher
    schema_nachher = $revNachher
    schema_unveraendert = $schemaGleich
} | ConvertTo-Json | Out-File (Join-Path $Programm "letztes-update.json") -Encoding utf8

Step "Starte Dienst…"
& $script:winsw.Exe start $script:winsw.Xml

# ── 5. Health-Check ─────────────────────────────────────────────────────────
$port = "8000"; $schema = "http"
$cfgServer = Join-Path $Daten "config\server.json"
if (Test-Path $cfgServer) {
    try {
        $srv = Get-Content $cfgServer -Raw | ConvertFrom-Json
        if ($srv.port) { $port = "$($srv.port)" }
        if ($srv.https -and $srv.https.aktiviert -and $srv.https.zertifikat) {
            $port = "$($srv.https.port)"; $schema = "https"
        }
    } catch {}
}

Step "Health-Check (bis zu 90 s)…"
try {
    $resp = WarteAufHealth "${schema}://localhost:${port}/api/health" 90
    Write-Host "  OK: $($resp | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "  Health-Check fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Logs:     $Daten\logs" -ForegroundColor Yellow
    Write-Host "  Rollback: $current\scripts\prod\rollback.ps1" -ForegroundColor Yellow
    exit 1
}

# ── 6. Registry und Aufraeumen ──────────────────────────────────────────────
if (Test-Path $regKey) { Set-ItemProperty $regKey "DisplayVersion" "$neueVersion" }

# Den Doppelklick-Starter anlegen bzw. auffrischen. Hier und nicht frueher:
# scheitert das Update vorher, soll kein Starter erscheinen, der auf eine
# Version zeigt, die nie aktiv wurde. Eine Installation aus der Zeit vor dem
# Starter bekommt ihn damit beim ersten Update nachgereicht.
try {
    $starter = SchreibeUpdateStarter $Programm
    Write-Host "  Starter aufgefrischt: $starter" -ForegroundColor Gray
} catch {
    Write-Host "  Hinweis: $Programm\update.cmd konnte nicht geschrieben werden ($_)" -ForegroundColor Yellow
}

$alle = Versionsordner $Programm
$behalten = @($zielVersion, $alterOrdner | ForEach-Object { $_.TrimEnd('\').ToLower() })
$zuLoeschen = @($alle | Where-Object { $behalten -notcontains $_.FullName.TrimEnd('\').ToLower() } |
    Select-Object -Skip ([Math]::Max(0, $BehalteVersionen - 1)))
if ($zuLoeschen) {
    Step "Raeume alte Versionen auf…"
    foreach ($o in $zuLoeschen) {
        Write-Host "  entferne $($o.Name)" -ForegroundColor Gray
        Remove-Item $o.FullName -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ── 7. Zusammenfassung ──────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Update abgeschlossen: $alteVersion -> $neueVersion" -ForegroundColor Green
Write-Host "  App: ${schema}://localhost:${port}"
Write-Host ""
if ($schemaGleich) {
    Write-Host "  Das Schema ist unveraendert ($revNachher)." -ForegroundColor Green
    Write-Host "  Ein Rollback ist deshalb verlustfrei moeglich." -ForegroundColor Green
} else {
    Write-Host "  Schema: $(if ($revVorher) { $revVorher } else { '(unbekannt)' }) -> $revNachher" -ForegroundColor Yellow
    Write-Host "  Ein Rollback spielt die Datenbank von vor dem Update zurueck;" -ForegroundColor Yellow
    Write-Host "  alles seither Gebuchte waere verloren." -ForegroundColor Yellow
}
Write-Host "  Rollback: $current\scripts\prod\rollback.ps1"
Write-Host ""
