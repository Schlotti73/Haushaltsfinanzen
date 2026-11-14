# Installiert die Haushaltsfinanz-App aus einem entpackten Release-Paket.
#
# Wird ueblicherweise ueber setup.cmd gestartet. Das Paket wird nach
# <Programm>\versionen\<Version>\ kopiert; die Junction <Programm>\current
# zeigt darauf, und der Dienst laeuft ueber diese Junction. Daten liegen
# getrennt davon und werden nie ersetzt. Siehe docs\release-paket.md.
#
#   .\install_service.ps1
#   .\install_service.ps1 -Programm D:\Apps\Haushaltsfinanzen -Daten D:\Daten\HF
#   .\install_service.ps1 -Port 8080

param(
    [string]$Programm    = "",
    [string]$Daten       = "",
    [string]$ServiceName = "Haushaltsfinanz",
    [string]$Port        = "",
    [switch]$Unbeaufsichtigt
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\pfade.ps1"

# ── 1. Admin-Wechsel ──────────────────────────────────────────────────────────
if (-not (IstAdmin)) {
    Write-Host "Keine Adminrechte - starte neu als Administrator…" -ForegroundColor Yellow
    $shell = if (Cmd "pwsh") { "pwsh" } else { "powershell" }
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    if ($Programm)       { $argList += @("-Programm", "`"$Programm`"") }
    if ($Daten)          { $argList += @("-Daten", "`"$Daten`"") }
    if ($Port)           { $argList += @("-Port", "$Port") }
    if ($ServiceName)    { $argList += @("-ServiceName", "`"$ServiceName`"") }
    if ($Unbeaufsichtigt){ $argList += "-Unbeaufsichtigt" }
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

# ── 2. Quelle pruefen ─────────────────────────────────────────────────────────
$quelle = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

$versionsDatei = Join-Path $quelle "VERSION"
$wheelsQuelle  = Join-Path $quelle "wheels"

if (-not (Test-Path $versionsDatei)) {
    Abort @"
Keine VERSION-Datei neben dem Skript gefunden ($versionsDatei).
  Dieses Skript installiert aus einem Release-Paket. Ein Git-Checkout ist
  keines - Pakete entstehen mit scripts\prod\create_prod_zip.ps1.
"@
}
if (-not (Test-Path $wheelsQuelle)) {
    Abort @"
Der Ordner wheels\ fehlt im Paket.
  Ohne ihn liesse sich die Python-Umgebung auf diesem Rechner nicht ohne
  Internet aufbauen. Das Paket ist unvollstaendig - neu erstellen.
"@
}

$version = (Get-Content $versionsDatei -Raw).Trim()
if (-not $version) { Abort "Die VERSION-Datei ist leer." }

# ── 3. Zielpfade ──────────────────────────────────────────────────────────────
$Programm = NormalisierePfad $Programm
$Daten    = NormalisierePfad $Daten
if (-not $Programm) { $Programm = $StandardProgramm }
if (-not $Daten)    { $Daten    = $StandardDaten }

# Der Dienst-Wrapper bekommt die Pfade in einer XML-Datei. Ein & oder < im
# Pfad macht sie ungueltig, und der Dienst liesse sich nicht einrichten.
foreach ($p in @($Programm, $Daten)) {
    if ($p -match '[&<>"]') {
        Abort "Der Pfad '$p' enthaelt ein Zeichen, das die Dienst-Konfiguration ungueltig macht (& < > `")."
    }
}

$versionen   = Join-Path $Programm "versionen"
$zielVersion = Join-Path $versionen $version
$current     = Join-Path $Programm "current"
$winsw       = WinswPfade $Programm
$istQuelleZiel = ((Resolve-Path $quelle).Path.TrimEnd('\') -ieq $zielVersion.TrimEnd('\'))

$cfgDir  = Join-Path $Daten "config"
$cfgServer = Join-Path $cfgDir "server.json"
$dbPfad  = Join-Path $Daten "finanzen.db"
$dbIstNeu = -not (Test-Path $dbPfad)

# Python der Zielversion. Passend halten zu docs/betrieb.md und requirements.
$pyZiel    = "3.11"
$pyWinget  = "Python.Python.3.11"
$pyZielExe = FindPython $pyZiel

$venv   = Join-Path $zielVersion "backend\.venv"
# Immer "python.exe -m <modul>" statt pip.exe/uvicorn.exe: die Konsolen-EXEn
# einer venv tragen deren Pfad fest in sich und schlagen nach einem
# Verschieben/Kopieren stumm fehl (Exitcode 1, keine Ausgabe).
$python = Join-Path $venv "Scripts\python.exe"

$tessExe = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$deuData = Join-Path $quelle "backend\tessdata\deu.traineddata"
$regKey  = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ServiceName"
$winswUrl = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"

# ── 4. Betriebseinstellungen ──────────────────────────────────────────────────
# Dieselbe Datei liest auch die Anwendung (backend/app/server_config.py), damit
# Port und Zertifikat nicht an zwei Stellen gepflegt werden muessen. Sie liegt
# beim Datenordner und ueberlebt jedes Update.
$httpsAktiv = $false
$httpsPort  = "8443"
$certPfad   = ""
$keyPfad    = ""
if (Test-Path $cfgServer) {
    try {
        $srv = Get-Content $cfgServer -Raw | ConvertFrom-Json
        if (-not $Port -and $srv.port) { $Port = "$($srv.port)" }
        if ($srv.https) {
            $httpsPort  = "$($srv.https.port)"
            $certPfad   = "$($srv.https.zertifikat)"
            $keyPfad    = "$($srv.https.schluessel)"
            $httpsAktiv = $srv.https.aktiviert -and $certPfad -and $keyPfad
            if ($srv.https.aktiviert -and -not (Test-Path $certPfad)) {
                Write-Host "  HTTPS ist aktiviert, aber das Zertifikat fehlt: $certPfad" -ForegroundColor Yellow
                Write-Host "  Der Dienst startet vorerst ohne HTTPS." -ForegroundColor Yellow
                $httpsAktiv = $false
            }
        }
    } catch {
        Write-Host "  $cfgServer ist fehlerhaft, es gelten die Vorgaben." -ForegroundColor Yellow
    }
}
if (-not $Port) { $Port = "8000" }

# ── 5. Vorhandene Installation ────────────────────────────────────────────────
$installedVersion = $null
if (Test-Path $regKey) {
    $installedVersion = (Get-ItemProperty $regKey -ErrorAction SilentlyContinue).DisplayVersion
}
$serviceExists = [bool](Get-Service $ServiceName -ErrorAction SilentlyContinue)
$winswDa = Test-Path $winsw.Exe

# ── 6. Uebersicht und Bestaetigung ───────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor White
Write-Host "║        Haushaltsfinanzen - Installation aus Paket             ║" -ForegroundColor White
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor White
Write-Host ""
Write-Host "  Paket-Version:        $version"
if ($installedVersion) {
    $marker = if ($installedVersion -eq $version) { " (gleiche Version)" } else { " -> Update auf $version" }
    Write-Host "  Installiert:          $installedVersion$marker" -ForegroundColor $(if ($installedVersion -eq $version) { "Yellow" } else { "Cyan" })
} else {
    Write-Host "  Installiert:          - (Erstinstallation)" -ForegroundColor Gray
}
Write-Host ""
Write-Host "  Programmordner:       $Programm"
Write-Host "    diese Version ->    versionen\$version"
Write-Host "  Datenordner:          $Daten" -ForegroundColor Green
Write-Host "    wird nie ersetzt, auch nicht bei einem Update" -ForegroundColor DarkGray
Write-Host "  Dienst / Port:        $ServiceName / $Port"
Write-Host ""
Write-Host "  Erforderliche Komponenten:" -ForegroundColor Yellow
Write-Host ""

$components = [ordered]@{
    "Python $pyZiel"    = @{ OK = [bool]$pyZielExe;  Aktion = "winget install $pyWinget" }
    "Tesseract-OCR"     = @{ OK = Test-Path $tessExe; Aktion = "winget install UB-Mannheim.TesseractOCR" }
    "Tesseract-Deutsch" = @{ OK = Test-Path $deuData; Aktion = "fehlt im Paket (Abbruch)" }
    "Dienst-Wrapper"    = @{ OK = $winswDa;           Aktion = "WinSW von GitHub laden" }
}
# Node.js steht hier bewusst nicht mehr: das Frontend ist im Paket vorgebaut.

foreach ($name in $components.Keys) {
    $c = $components[$name]
    if ($c.OK) {
        Write-Host ("    [OK] {0,-22}" -f $name) -ForegroundColor Green -NoNewline
        Write-Host " vorhanden"
    } else {
        Write-Host ("    [--] {0,-22}" -f $name) -ForegroundColor Red -NoNewline
        Write-Host " $($c.Aktion)" -ForegroundColor DarkYellow
    }
}

Write-Host ""
Write-Host "  Geplante Aktionen:" -ForegroundColor Yellow
Write-Host ""
foreach ($name in $components.Keys) {
    if (-not $components[$name].OK) {
        Write-Host ("    - {0,-22} {1}" -f $name, $components[$name].Aktion) -ForegroundColor DarkYellow
    }
}
if (-not $istQuelleZiel) {
    Write-Host "    - Paket nach versionen\$version kopieren" -ForegroundColor Gray
}
Write-Host "    - Python-Umgebung offline aus wheels\ aufbauen (ohne Internet)" -ForegroundColor Gray
Write-Host "    - Datenordner anlegen bzw. weiterverwenden: $Daten" -ForegroundColor Gray
if ($dbIstNeu) {
    Write-Host "    - Neue Datenbank anlegen + Admin-Benutzer (interaktive Abfrage)" -ForegroundColor DarkYellow
} else {
    Write-Host "    - Vorhandene Datenbank sichern und auf das neue Schema bringen" -ForegroundColor Gray
}
if ($serviceExists) {
    Write-Host "    - Dienst '$ServiceName' stoppen und neu einrichten" -ForegroundColor DarkYellow
}
Write-Host "    - Junction current -> versionen\$version setzen" -ForegroundColor Gray
Write-Host "    - Dienst, Firewall-Regel und Registry-Eintrag einrichten" -ForegroundColor Gray
Write-Host ""

if (-not $components["Tesseract-Deutsch"].OK) {
    Abort "deu.traineddata fehlt im Paket (erwartet: $deuData). Paket neu erstellen."
}

if (-not $Unbeaufsichtigt) {
    $confirm = Read-Host "  Installation starten? [J/N]"
    if ($confirm -notmatch "^[JjYy]") { Write-Host "Abgebrochen." -ForegroundColor Yellow; exit 0 }
}

# ── 7. Programme via winget ───────────────────────────────────────────────────
Step "Installiere fehlende Programme…"

if (-not $pyZielExe) {
    Write-Host "  Python $pyZiel…" -ForegroundColor Yellow
    winget install --id $pyWinget --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { Abort "Python-Installation fehlgeschlagen" }
    RefreshPath
    $pyZielExe = FindPython $pyZiel
    if (-not $pyZielExe) { Abort "Python $pyZiel ist nach der Installation nicht auffindbar. Neue Shell oeffnen und erneut starten." }
}
Write-Host "  Python $pyZiel - $pyZielExe" -ForegroundColor Gray

if (-not (Test-Path $tessExe)) {
    Write-Host "  Tesseract-OCR…" -ForegroundColor Yellow
    winget install --id UB-Mannheim.TesseractOCR --silent --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { Abort "Tesseract-Installation fehlgeschlagen" }
    RefreshPath
} else { Write-Host "  Tesseract-OCR - bereits vorhanden." -ForegroundColor Gray }

New-Item -ItemType Directory -Force $winsw.Ordner | Out-Null
if (-not (Test-Path $winsw.Exe)) {
    Write-Host "  Dienst-Wrapper (WinSW)…" -ForegroundColor Yellow
    try {
        # Windows PowerShell 5.1 handelt je nach .NET-Konfiguration noch
        # TLS 1.0 aus; GitHub lehnt das ab. Und der Fortschrittsbalken von
        # Invoke-WebRequest bremst den Download dort um ein Vielfaches.
        $altTls = [System.Net.ServicePointManager]::SecurityProtocol
        $altPp  = $ProgressPreference
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $ProgressPreference = "SilentlyContinue"
        try {
            Invoke-WebRequest -Uri $winswUrl -OutFile $winsw.Exe -UseBasicParsing
        } finally {
            [System.Net.ServicePointManager]::SecurityProtocol = $altTls
            $ProgressPreference = $altPp
        }
    } catch {
        Abort "WinSW konnte nicht geladen werden: $_`n  Bitte WinSW-x64.exe manuell als $($winsw.Exe) ablegen."
    }
} else { Write-Host "  Dienst-Wrapper - vorhanden." -ForegroundColor Gray }

# ── 8. Laufenden Dienst stoppen ───────────────────────────────────────────────
# Vor allen Datei- und venv-Arbeiten: ein laufender Dienst haelt python.exe und
# die Pakete seiner venv offen, Loeschen/Ueberschreiben scheitert dann an
# Dateisperren.
if ($serviceExists) {
    Step "Stoppe bestehenden Dienst '$ServiceName'…"
    if (Test-Path $winsw.Xml) {
        & $winsw.Exe stop      $winsw.Xml 2>$null
        & $winsw.Exe uninstall $winsw.Xml 2>$null
    }
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) {
        sc.exe delete $ServiceName | Out-Null
    }
    Start-Sleep -Seconds 2
}

# ── 9. Paket an seinen Platz kopieren ─────────────────────────────────────────
if (-not $istQuelleZiel) {
    Step "Kopiere Paket nach versionen\$version…"
    if (Test-Path $zielVersion) {
        Write-Host "  Vorhandenen Ordner ersetzen…" -ForegroundColor Yellow
        Remove-Item $zielVersion -Recurse -Force
    }
    New-Item -ItemType Directory -Force $zielVersion | Out-Null
    Copy-Item "$quelle\*" $zielVersion -Recurse -Force
} else {
    Step "Paket liegt bereits an seinem Platz."
}

# ── 10. Python-Umgebung offline aufbauen ─────────────────────────────────────
Step "Baue Python-Umgebung (offline aus wheels\)…"
$wheels = Join-Path $zielVersion "wheels"
& $pyZielExe -m venv $venv
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $python)) { Abort "venv konnte nicht angelegt werden" }

# --no-index: ausschliesslich die mitgelieferten Wheels. Schlaegt das fehl, ist
# das Paket unvollstaendig - und nicht etwa das Internet schuld.
& $python -m pip install --no-index --find-links $wheels -r (Join-Path $zielVersion "backend\requirements.txt") -q
if ($LASTEXITCODE -ne 0) {
    Abort "Installation aus wheels\ fehlgeschlagen - das Paket ist unvollstaendig. Neu erstellen."
}
$venvVersion = PyVersion $python
if ($venvVersion -ne $pyZiel) { Abort "venv laeuft mit Python $venvVersion, erwartet war $pyZiel" }
Write-Host "  Umgebung bereit (Python $venvVersion)." -ForegroundColor Gray

# ── 11. Datenordner ──────────────────────────────────────────────────────────
Step "Richte Datenordner ein…"
foreach ($d in @($Daten, $cfgDir, (Join-Path $Daten "logs"), (Join-Path $Daten "backups"))) {
    New-Item -ItemType Directory -Force $d | Out-Null
}

if (-not (Test-Path $cfgServer)) {
    # Vorgaben wie in backend/app/server_config.py
    @{
        port  = [int]$Port
        https = @{ aktiviert = $false; port = 8443; zertifikat = ""; schluessel = "" }
        dev   = @{ backend_port = 8000; frontend_port = 5173 }
        zugriff = @{
            vertrauenswuerdige_netze  = @("127.0.0.1/32", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12")
            vertrauenswuerdige_proxys = @()
            mfa_immer_erforderlich    = $false
        }
    } | ConvertTo-Json -Depth 5 | Out-File $cfgServer -Encoding utf8
    Write-Host "  server.json angelegt: $cfgServer" -ForegroundColor Gray
} else {
    Write-Host "  Einstellungen uebernommen: $cfgDir" -ForegroundColor Gray
}

# Die Umgebung, unter der alle folgenden Python-Aufrufe und spaeter der Dienst
# laufen. datenbanken.json wird NICHT vorab geschrieben: fehlt sie, gilt
# FINANZ_DATEN_DIR\finanzen.db, und die Anwendung registriert sie beim ersten
# Zugriff selbst (app.db_registry.stelle_erstregistrierung_sicher).
$env:FINANZ_DATEN_DIR = $Daten
$env:PYTHONPATH       = Join-Path $zielVersion "backend"
$env:TESSDATA_PREFIX  = Join-Path $zielVersion "backend\tessdata"
Remove-Item Env:\FINANZ_AUTO_MIGRATE -ErrorAction SilentlyContinue

# ── 12. Datenbank ────────────────────────────────────────────────────────────
Step "Pruefe Datenbank…"
$seed = Join-Path $zielVersion "scripts\prod\seed_admin.py"

if (-not $dbIstNeu) {
    # Vor jeder Schema-Aenderung ein Backup - dieselbe Regel wie im Update.
    Step "Sichere vorhandene Datenbank…"
    $sicher = Join-Path $Daten "backups\vor-$version`_$(Get-Date -Format 'yyyyMMdd-HHmm').db"
    Copy-Item $dbPfad $sicher -Force
    Write-Host "  $sicher" -ForegroundColor Gray
}

if ($dbIstNeu) {
    Write-Host "  Keine Datenbank gefunden - Admin-Zugangsdaten fuer die Erstinstallation:" -ForegroundColor Yellow
    $adminName = Read-Host "    Admin-Benutzername [Standard: admin]"
    if (-not $adminName) { $adminName = "admin" }
    $securePw = Read-Host "    Admin-Passwort [Standard: admin123]" -AsSecureString
    if ($securePw.Length -eq 0) {
        $adminPw = "admin123"
    } else {
        $adminPw = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
            [Runtime.InteropServices.Marshal]::SecureStringToBSTR($securePw))
    }
    $dbOutput = $adminPw | & $python $seed --admin-name $adminName
    $adminPw = $null
    if ($LASTEXITCODE -ne 0) { Abort "Anlegen der Datenbank/des Admin-Benutzers fehlgeschlagen" }
} else {
    $dbOutput = & $python $seed
    if ($LASTEXITCODE -ne 0) { Abort "Datenbank-Migration fehlgeschlagen" }
}
$dbOutput | ForEach-Object { Write-Host "  $_" -ForegroundColor Gray }
$dbRevision = ($dbOutput | Where-Object { $_ -match "^ALEMBIC_REV=" }) -replace "^ALEMBIC_REV=", ""

# ── 13. Junction umlegen ─────────────────────────────────────────────────────
Step "Setze current -> versionen\$version…"
try { SetzeJunction $current $zielVersion } catch { Abort "$_" }

# ── 14. Dienst einrichten ────────────────────────────────────────────────────
Step "Richte Dienst '$ServiceName' ein…"

# Gestartet wird "python.exe -m uvicorn" statt uvicorn.exe: der Wrapper bleibt
# damit unabhaengig davon, ob die Konsolen-EXEn der venv zum Pfad passen.
# Alle Pfade zeigen auf current\, nie auf einen Versionsordner - sonst muesste
# die Dienst-Konfiguration bei jedem Update neu geschrieben werden.
$cPython = Join-Path $current "backend\.venv\Scripts\python.exe"
$uvArgs = "-m uvicorn app.main:app --host 0.0.0.0 --port $Port"
if ($httpsAktiv) {
    $uvArgs = "-m uvicorn app.main:app --host 0.0.0.0 --port $httpsPort --ssl-certfile `"$certPfad`" --ssl-keyfile `"$keyPfad`""
    Write-Host "  HTTPS aktiv auf Port $httpsPort" -ForegroundColor Gray
}

$xml = @"
<service>
  <id>$ServiceName</id>
  <name>$ServiceName</name>
  <description>Haushaltsfinanzen (FastAPI/uvicorn)</description>
  <executable>$cPython</executable>
  <arguments>$uvArgs</arguments>
  <workingdirectory>$current\backend</workingdirectory>
  <env name="PYTHONPATH" value="$current\backend" />
  <env name="TESSDATA_PREFIX" value="$current\backend\tessdata" />
  <env name="FINANZ_DATEN_DIR" value="$Daten" />
  <!-- Migrieren darf nur das Update-Skript, das vorher ein Backup anlegt.
       Der Dienst prueft das Schema und verweigert bei Abweichung den Start. -->
  <env name="FINANZ_AUTO_MIGRATE" value="0" />
  <logpath>$Daten\logs</logpath>
  <log mode="roll-by-size">
    <sizeThreshold>10240</sizeThreshold>
    <keepFiles>8</keepFiles>
  </log>
  <startmode>Automatic</startmode>
  <onfailure action="restart" delay="10 sec" />
  <serviceaccount>
    <username>LocalSystem</username>
  </serviceaccount>
</service>
"@
Set-Content -Path $winsw.Xml -Value $xml -Encoding UTF8
& $winsw.Exe install $winsw.Xml
if ($LASTEXITCODE -ne 0) { Abort "Dienst konnte nicht eingerichtet werden" }

# ── 15. Firewall ─────────────────────────────────────────────────────────────
$fwPort = if ($httpsAktiv) { $httpsPort } else { $Port }
$fwName = "Haushaltsfinanz :$fwPort"
if (-not (Get-NetFirewallRule -DisplayName $fwName -ErrorAction SilentlyContinue)) {
    Step "Lege Firewall-Regel '$fwName' an…"
    New-NetFirewallRule -DisplayName $fwName `
        -Direction Inbound -Action Allow -Protocol TCP -LocalPort $fwPort `
        -Profile Private | Out-Null
}

# ── 16. Registry ─────────────────────────────────────────────────────────────
Step "Schreibe Software-Eintrag in Registry…"
if (-not (Test-Path $regKey)) { New-Item -Path $regKey -Force | Out-Null }
Set-ItemProperty $regKey "DisplayName"     "$ServiceName"
Set-ItemProperty $regKey "DisplayVersion"  "$version"
Set-ItemProperty $regKey "Publisher"       "Haushaltsfinanz"
Set-ItemProperty $regKey "InstallLocation" "$Programm"
Set-ItemProperty $regKey "InstallDate"     (Get-Date -Format "yyyyMMdd")
Set-ItemProperty $regKey "UninstallString" "powershell -NoProfile -ExecutionPolicy Bypass -File `"$Programm\dienst\uninstall_service.ps1`""
Set-ItemProperty $regKey "NoModify"        1 -Type DWord
Set-ItemProperty $regKey "NoRepair"        1 -Type DWord
# Datenordner merken: Update, Rollback und Deinstallation finden ihn so wieder,
# ohne dass er jedes Mal uebergeben werden muss.
Set-ItemProperty $regKey "DatenOrdner"     "$Daten"
Write-Host "  Version $version eingetragen." -ForegroundColor Gray

# Deinstallation neben den Dienst-Wrapper legen: sie muss auch dann noch
# funktionieren, wenn kein Versionsordner mehr da ist.
Copy-Item (Join-Path $zielVersion "scripts\prod\uninstall_service.ps1") $winsw.Ordner -Force
Copy-Item (Join-Path $zielVersion "scripts\prod\pfade.ps1")             $winsw.Ordner -Force

# Doppelklick-Starter fuer das Update im Programmstamm. Erzeugt statt kopiert:
# er zeigt auf current\ und bleibt so ueber Updates hinweg gueltig. update.ps1
# frischt ihn bei jedem Update auf.
$starter = SchreibeUpdateStarter $Programm
Write-Host "  Update-Starter: $starter" -ForegroundColor Gray

# ── 17. Dienst starten ───────────────────────────────────────────────────────
Step "Starte Dienst…"
& $winsw.Exe start $winsw.Xml

Step "Health-Check (bis zu 90 s)…"
$schema = if ($httpsAktiv) { "https" } else { "http" }
try {
    $resp = WarteAufHealth "${schema}://localhost:${fwPort}/api/health" 90
    Write-Host "  OK: $($resp | ConvertTo-Json -Compress)" -ForegroundColor Green
} catch {
    Write-Host "  Health-Check fehlgeschlagen: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  Logs: $Daten\logs" -ForegroundColor Yellow
}

# ── 18. Backup-Aufgabe ──────────────────────────────────────────────────────
if (-not $Unbeaufsichtigt) {
    $cfgBackup = Join-Path $cfgDir "backup.json"
    $doBackup = Read-Host "`n  Taegliche Backup-Aufgabe im Aufgabenplaner einrichten? [J/N]"
    if ($doBackup -match "^[JjYy]") {
        $bUhrzeit = "02:00"; $bZiel = ""; $bTaskName = "HaushaltsfinanzBackup"
        if (Test-Path $cfgBackup) {
            try {
                $bJson = Get-Content $cfgBackup -Raw | ConvertFrom-Json
                if ($bJson.uhrzeit)     { $bUhrzeit  = $bJson.uhrzeit }
                if ($bJson.ziel_ordner) { $bZiel     = $bJson.ziel_ordner }
                if ($bJson.task_name)   { $bTaskName = $bJson.task_name }
            } catch {}
        }
        $eing = Read-Host "    Uhrzeit [Standard: $bUhrzeit]"; if ($eing) { $bUhrzeit = $eing }
        $eing = Read-Host "    Zielordner (leer = $Daten\backups)"; if ($eing) { $bZiel = $eing }

        @{
            aktiviert = $true; ziel_ordner = $bZiel; uhrzeit = $bUhrzeit
            behalten = 30; task_name = $bTaskName
        } | ConvertTo-Json | Out-File $cfgBackup -Encoding utf8

        Step "Registriere Backup-Aufgabe '$bTaskName' (taeglich $bUhrzeit)…"
        & (Join-Path $zielVersion "scripts\prod\register_backup_task.ps1") `
            -TaskName $bTaskName -Zeit $bUhrzeit -ZielOrdner $bZiel

        # Ein Netzwerkziel braucht Zugangsdaten, und die werden mit DPAPI unter
        # dem AUFRUFENDEN Benutzer verschluesselt. Der Dienst laeuft als
        # LocalSystem und koennte ein hier gesetztes Passwort nicht entschluesseln.
        if ($bZiel -match '^\\\\') {
            Write-Host ""
            Write-Host "  Hinweis: Das Backup-Ziel ist ein Netzwerkpfad." -ForegroundColor Yellow
            Write-Host "  Zugangsdaten muessen als derselbe Benutzer gesetzt werden, unter dem" -ForegroundColor Yellow
            Write-Host "  das Backup laeuft - sonst scheitert die Entschluesselung stumm:" -ForegroundColor Yellow
            Write-Host "    $python $current\scripts\netzlaufwerk.py --passwort-setzen" -ForegroundColor Gray
        }
    } else {
        Write-Host "  Uebersprungen - jederzeit nachholen:" -ForegroundColor Gray
        Write-Host "    $current\scripts\prod\register_backup_task.ps1" -ForegroundColor Gray
    }
}

# ── 19. Zusammenfassung ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Green
Write-Host "║   Haushaltsfinanzen $($version.PadRight(41))║" -ForegroundColor Green
Write-Host "║   Installation abgeschlossen                                 ║" -ForegroundColor Green
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Green
Write-Host ""
Write-Host "  App:    ${schema}://localhost:${fwPort}"
Write-Host "  API:    ${schema}://localhost:${fwPort}/api/docs"
$ip = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object {
    $_.IPAddress -notlike "169.254.*" -and $_.IPAddress -ne "127.0.0.1"
} | Select-Object -First 1).IPAddress
if ($ip) { Write-Host "  Netz:   ${schema}://${ip}:${fwPort}" }
if ($dbRevision) { Write-Host "  Schema: $dbRevision" }
Write-Host ""
Write-Host "  Programm: $Programm   (Updates ersetzen diesen Ordner)"
Write-Host "  Daten:    $Daten   (bleibt unberuehrt)" -ForegroundColor Green
Write-Host ""
Write-Host "  Update:        $Programm\update.cmd   (Doppelklick)" -ForegroundColor Cyan
Write-Host "  oder:          $current\scripts\prod\update.ps1 -Paket <zip>"
Write-Host "  Rollback:      $current\scripts\prod\rollback.ps1"
Write-Host "  Deinstallation: $Programm\dienst\uninstall_service.ps1"
Write-Host ""
