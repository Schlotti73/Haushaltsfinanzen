# Legt das letzte Update zurueck.
#
# Code und Datenbank sind beim Rollback untrennbar: die Anwendung migriert auf
# head, und eine zurueckgerollte Version kennt die Revision der neueren nicht -
# sie wuerde den Start mit einer Schema-Abweichung verweigern. Hat das Update
# das Schema geaendert, wird deshalb auch die Datenbank zurueckgespielt.
#
# Die Alembic-downgrade()-Funktionen sind dafuer kein Weg: sie sind destruktiv
# (drop_column, drop_table) und teils absichtlich unvollstaendig.
#
#   .\rollback.ps1
#   .\rollback.ps1 -Version v1.4.2      # auf eine bestimmte Version zurueck

param(
    [string]$Version     = "",
    [string]$Programm    = "",
    [string]$Daten       = "",
    [string]$ServiceName = "Haushaltsfinanz",
    [switch]$OhneDatenbank   # nur den Code zurueck (nur sinnvoll ohne Schema-Wechsel)
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\pfade.ps1"

if (-not (IstAdmin)) {
    Write-Host "Keine Adminrechte - starte neu als Administrator…" -ForegroundColor Yellow
    $shell = if (Cmd "pwsh") { "pwsh" } else { "powershell" }
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"",
                 "-ServiceName", "`"$ServiceName`"")
    if ($Version)        { $argList += @("-Version", "`"$Version`"") }
    if ($Programm)       { $argList += @("-Programm", "`"$Programm`"") }
    if ($Daten)          { $argList += @("-Daten", "`"$Daten`"") }
    if ($OhneDatenbank)  { $argList += "-OhneDatenbank" }
    # -PassThru und .ExitCode, nicht $LASTEXITCODE: der bezieht sich allein auf
    # native Aufrufe im EIGENEN Prozess. Ohne das meldete ein gescheiterter
    # Lauf nach dem UAC-Neustart nach aussen Erfolg.
    $p = Start-Process $shell -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $p.ExitCode
}

function Abort([string]$msg) {
    Write-Host "`nFEHLER: $msg" -ForegroundColor Red
    exit 1
}

# ── 1. Installation und letztes Update finden ────────────────────────────────
$regKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ServiceName"
if (Test-Path $regKey) {
    $reg = Get-ItemProperty $regKey
    if (-not $Programm -and $reg.InstallLocation) { $Programm = $reg.InstallLocation }
    if (-not $Daten    -and $reg.DatenOrdner)     { $Daten    = $reg.DatenOrdner }
}
$Programm = NormalisierePfad $Programm
$Daten    = NormalisierePfad $Daten
if (-not $Programm) { $Programm = $StandardProgramm }
if (-not $Daten)    { $Daten    = $StandardDaten }

$current  = Join-Path $Programm "current"
$winsw    = WinswPfade $Programm
$protokoll = Join-Path $Programm "letztes-update.json"

if (-not (Test-Path $current)) { Abort "Keine Installation unter $Programm gefunden." }
$jetzigerOrdner = JunctionZiel $current
if (-not $jetzigerOrdner) { Abort "$current ist keine Junction - bitte von Hand pruefen." }
$jetzigeVersion = LeseVersion $jetzigerOrdner

$info = $null
if (Test-Path $protokoll) {
    try { $info = Get-Content $protokoll -Raw | ConvertFrom-Json } catch {}
}

# ── 2. Ziel bestimmen ────────────────────────────────────────────────────────
if ($Version) {
    $zielOrdner = Join-Path $Programm "versionen\$Version"
    if (-not (Test-Path $zielOrdner)) {
        Write-Host "  Vorhandene Versionen:" -ForegroundColor Yellow
        Versionsordner $Programm | ForEach-Object { Write-Host "    $($_.Name)" -ForegroundColor Gray }
        Abort "Version $Version ist nicht installiert."
    }
    # Eine Sicherung passt nur, wenn sie aus genau diesem Uebergang stammt.
    if (-not ($info -and $info.von_ordner -and $info.von_ordner.TrimEnd('\') -ieq $zielOrdner.TrimEnd('\'))) {
        $info = $null
    }
} elseif ($info -and $info.von_ordner -and (Test-Path $info.von_ordner)) {
    $zielOrdner = $info.von_ordner
} else {
    $kandidaten = @(Versionsordner $Programm | Where-Object {
        $_.FullName.TrimEnd('\').ToLower() -ne $jetzigerOrdner.TrimEnd('\').ToLower() })
    if (-not $kandidaten) { Abort "Es ist nur eine Version installiert - kein Rollback moeglich." }
    $zielOrdner = $kandidaten[0].FullName
    Write-Host "  Kein Update-Protokoll gefunden, nehme die zuletzt geschriebene Version." -ForegroundColor Yellow
}
$zielVersion = LeseVersion $zielOrdner

if ($zielOrdner.TrimEnd('\') -ieq $jetzigerOrdner.TrimEnd('\')) {
    Abort "Diese Version laeuft bereits: $jetzigeVersion"
}

# ── 3. Entscheiden, was mit der Datenbank passiert ───────────────────────────
$dbPfad = Join-Path $Daten "finanzen.db"
$schemaGleich = [bool]($info -and $info.schema_unveraendert)
$sicherung = if ($info) { "$($info.sicherung)" } else { "" }
$dbZurueck = $false

if ($OhneDatenbank) {
    $dbZurueck = $false
} elseif ($schemaGleich) {
    # Verlustfreier Fall: das Update hat das Schema nicht angefasst, die alte
    # Programmversion kann die heutige Datenbank lesen.
    $dbZurueck = $false
} else {
    if (-not $sicherung -or -not (Test-Path $sicherung)) {
        Abort @"
Die Sicherung von vor dem Update fehlt$(if ($sicherung) { ": $sicherung" }).
  Ohne sie laesst sich der Code nicht allein zurueckrollen: $zielVersion kennt
  die Schema-Revision der laufenden Datenbank nicht und wuerde den Start
  verweigern.
  Abhilfe: eine passende Sicherung aus $Daten\backups von Hand einspielen,
  oder auf der jetzigen Version bleiben.
"@
    }
    $dbZurueck = $true
}

# ── 4. Uebersicht und Bestaetigung ───────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Yellow
Write-Host "║   Rollback                                                   ║" -ForegroundColor Yellow
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Laeuft jetzt:  $jetzigeVersion"
Write-Host "  Zurueck auf:   $zielVersion" -ForegroundColor Cyan
Write-Host ""
if ($dbZurueck) {
    $alter = ""
    if ($info.zeitpunkt) {
        try {
            $seit = (Get-Date) - [datetime]$info.zeitpunkt
            $alter = " (Update war vor $([int]$seit.TotalHours) h $($seit.Minutes) min)"
        } catch {}
    }
    Write-Host "  Das Update hat das Schema geaendert:" -ForegroundColor Red
    Write-Host "    $($info.schema_vorher) -> $($info.schema_nachher)" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Die Datenbank wird aus der Sicherung zurueckgespielt$alter" -ForegroundColor Red
    Write-Host "    $sicherung" -ForegroundColor Gray
    Write-Host ""
    Write-Host "  ALLES, WAS SEIT DEM UPDATE ERFASST WURDE, GEHT VERLOREN." -ForegroundColor Red
    Write-Host "  Die jetzige Datenbank wird vorher zur Seite gelegt." -ForegroundColor Gray
} elseif ($OhneDatenbank) {
    Write-Host "  Nur der Code wird zurueckgelegt (-OhneDatenbank)." -ForegroundColor Yellow
    Write-Host "  Passt das Schema nicht, verweigert der Dienst den Start." -ForegroundColor Yellow
} else {
    Write-Host "  Das Schema ist unveraendert ($($info.schema_nachher))." -ForegroundColor Green
    Write-Host "  Die Datenbank bleibt, wie sie ist - verlustfreier Rollback." -ForegroundColor Green
}
Write-Host ""

$confirm = Read-Host "  Rollback durchfuehren? [J/N]"
if ($confirm -notmatch "^[JjYy]") { Write-Host "Abgebrochen." -ForegroundColor Yellow; exit 0 }
if ($dbZurueck) {
    $zweite = Read-Host "  Zur Sicherheit: Zielversion zur Bestaetigung eingeben ($zielVersion)"
    if ($zweite.Trim() -ne $zielVersion) { Abort "Eingabe passt nicht - abgebrochen, nichts geaendert." }
}

# ── 5. Durchfuehren ──────────────────────────────────────────────────────────
Step "Stoppe Dienst '$ServiceName'…"
if (Test-Path $winsw.Xml) { & $winsw.Exe stop $winsw.Xml }

if ($dbZurueck) {
    Step "Lege die jetzige Datenbank zur Seite…"
    $beiseite = Join-Path $Daten "backups\verworfen-$jetzigeVersion`_$(Get-Date -Format 'yyyyMMdd-HHmm').db"
    if (Test-Path $dbPfad) {
        Copy-Item $dbPfad $beiseite -Force
        foreach ($s in @("-wal", "-shm")) {
            if (Test-Path "$dbPfad$s") { Copy-Item "$dbPfad$s" "$beiseite$s" -Force }
        }
        Write-Host "  $beiseite" -ForegroundColor Gray
    }

    Step "Spiele die Datenbank von vor dem Update zurueck…"
    # WAL-Dateien der jetzigen DB muessen weg: sonst wuerde SQLite sie auf die
    # zurueckgespielte Datei anwenden und sie damit beschaedigen.
    foreach ($s in @("-wal", "-shm")) {
        Remove-Item "$dbPfad$s" -Force -ErrorAction SilentlyContinue
    }
    Copy-Item $sicherung $dbPfad -Force
    foreach ($s in @("-wal", "-shm")) {
        if (Test-Path "$sicherung$s") { Copy-Item "$sicherung$s" "$dbPfad$s" -Force }
    }
    Write-Host "  $dbPfad" -ForegroundColor Gray
}

Step "Lege current auf versionen\$zielVersion um…"
try { SetzeJunction $current $zielOrdner } catch { Abort "$_" }

if (Test-Path $regKey) { Set-ItemProperty $regKey "DisplayVersion" "$zielVersion" }

# Das Protokoll gilt nicht mehr - sonst wuerde ein zweiter Aufruf dieselbe
# Sicherung erneut einspielen.
if (Test-Path $protokoll) {
    Move-Item $protokoll (Join-Path $Programm "letztes-update.zurueckgerollt.json") -Force
}

Step "Starte Dienst…"
if (Test-Path $winsw.Xml) { & $winsw.Exe start $winsw.Xml }

# ── 6. Health-Check ──────────────────────────────────────────────────────────
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

Step "Health-Check (warte 5 s)…"
Start-Sleep -Seconds 5
try {
    $resp = HealthAbfrage "${schema}://localhost:${port}/api/health"
    Write-Host "  OK: $($resp | ConvertTo-Json -Compress)" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Rollback abgeschlossen: $jetzigeVersion -> $zielVersion" -ForegroundColor Green
} catch {
    Write-Host "  Health-Check fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Logs: $Daten\logs" -ForegroundColor Yellow
    exit 1
}
Write-Host ""
