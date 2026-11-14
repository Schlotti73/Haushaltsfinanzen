# Gemeinsame Pfad- und Dienst-Hilfen fuer Installation, Update und Rollback.
# Wird von install_service.ps1, update.ps1, rollback.ps1 und status.ps1 geladen
# (dot-sourcing), damit die Struktur nur an einer Stelle definiert ist.
# Siehe docs/release-paket.md.

# Windows PowerShell 5.1 gibt per Default in der Codepage der Konsole aus
# (meist 850). Umlaute und die Rahmenzeichen der Zusammenfassung werden dabei
# zu Fragezeichen. Das aendert nichts an der Funktion, sieht aber nach Fehler
# aus - gerade in dem Moment, in dem das Setup "fertig" meldet.
try {
    [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
} catch { }

# Standard-Ablageorte, beide frei ueberschreibbar (-Programm / -Daten).
#
# Programm unter "Program Files": der uebliche Ort fuer installierte Software,
# und er funktioniert hier, weil der Dienst als LocalSystem schreiben darf und
# 64-Bit-Python nicht virtualisiert wird. Nicht fest verdrahtet, sondern ueber
# $env:ProgramFiles - der Ordner heisst nicht auf jedem Windows gleich und
# liegt nicht immer auf C:.
#
# Daten unter ProgramData: maschinenweit, nicht an ein Benutzerprofil
# gebunden, und von einem Update nie angefasst.
#
# Beide Pfade enthalten ein Leerzeichen bzw. koennen eines enthalten - alle
# Skripte muessen damit umgehen, siehe NormalisierePfad.
$script:StandardProgramm = "$env:ProgramFiles\Haushaltsfinanzen"
$script:StandardDaten    = "$env:ProgramData\Haushaltsfinanzen"

function NormalisierePfad([string]$pfad) {
    # Ein in Anfuehrungszeichen uebergebener Pfad mit abschliessendem
    # Backslash kommt beschaedigt an: in
    #   -Programm "C:\Program Files\App\"
    # hebt der Backslash das schliessende Anfuehrungszeichen auf, und das
    # Skript bekommt  C:\Program Files\App"  zu sehen. Beides steht am Ende
    # und laesst sich gefahrlos abschneiden.
    if (-not $pfad) { return $pfad }
    return ($pfad.Trim() -replace '[\\"]+$', '')
}

function Step([string]$msg) {
    Write-Host "`n[$([datetime]::Now.ToString('HH:mm:ss'))] $msg" -ForegroundColor Cyan
}

function IstAdmin {
    return ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Cmd([string]$name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

function RefreshPath {
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path","User")
}

# Minor-Version eines Interpreters ("3.11"), $null wenn er nicht laeuft
function PyVersion([string]$exe) {
    if (-not $exe) { return $null }
    try { $out = & $exe -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    return ("$out" | Select-Object -Last 1).Trim()
}

# Interpreter der Zielversion suchen: erst der py-Launcher (findet auch
# Installationen, die nicht im PATH stehen), dann python aus dem PATH.
function FindPython([string]$ziel) {
    if (Cmd "py") {
        $p = & py "-$ziel" -c "import sys; print(sys.executable)" 2>$null
        if ($LASTEXITCODE -eq 0 -and $p) { return ("$p" | Select-Object -Last 1).Trim() }
    }
    if ((Cmd "python") -and (PyVersion "python") -eq $ziel) {
        return (Get-Command python).Source
    }
    return $null
}

function IstJunction([string]$pfad) {
    if (-not (Test-Path $pfad)) { return $false }
    $i = Get-Item $pfad -Force
    return [bool]($i.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function JunctionZiel([string]$pfad) {
    if (-not (IstJunction $pfad)) { return $null }
    return (Get-Item $pfad -Force).Target | Select-Object -First 1
}

# Junction setzen oder umlegen.
#
# Wichtig: eine bestehende Junction wird mit Directory.Delete entfernt, nicht
# mit Remove-Item -Recurse. Letzteres folgt je nach PowerShell-Fassung dem
# Reparse-Point und loescht den INHALT des Zielordners - also die Version, auf
# die gerade gezeigt wird. Directory.Delete(pfad, $false) entfernt nur den
# Reparse-Point selbst und laesst das Ziel unberuehrt.
function SetzeJunction([string]$pfad, [string]$ziel) {
    if (-not (Test-Path $ziel)) { throw "Junction-Ziel fehlt: $ziel" }
    if (Test-Path $pfad) {
        if (-not (IstJunction $pfad)) {
            throw "$pfad existiert und ist keine Junction - bitte von Hand pruefen."
        }
        [System.IO.Directory]::Delete($pfad, $false)
        if (Test-Path $pfad) { throw "Junction konnte nicht entfernt werden: $pfad" }
    }
    New-Item -ItemType Junction -Path $pfad -Target $ziel | Out-Null
}

# Alle installierten Versionen, neueste zuerst (nach Schreibzeit, nicht nach
# Namen: ein Vorabpaket wie v1.4.2-11-gbdc3156-vorab sortiert sonst falsch).
function Versionsordner([string]$programm) {
    $v = Join-Path $programm "versionen"
    if (-not (Test-Path $v)) { return @() }
    return @(Get-ChildItem $v -Directory | Sort-Object LastWriteTime -Descending)
}

function LeseVersion([string]$ordner) {
    $f = Join-Path $ordner "VERSION"
    if (Test-Path $f) { return (Get-Content $f -Raw).Trim() }
    return Split-Path $ordner -Leaf
}

# Der Dienst-Wrapper liegt ausserhalb der Versionsordner: er darf beim
# Umschalten nicht ausgetauscht werden, und seine Konfiguration zeigt dauerhaft
# auf current\. WinSW erwartet die XML unter gleichem Basisnamen wie die EXE.
function WinswPfade([string]$programm) {
    $dir = Join-Path $programm "dienst"
    return [pscustomobject]@{
        Ordner = $dir
        Exe    = Join-Path $dir "Haushaltsfinanzen.exe"
        Xml    = Join-Path $dir "Haushaltsfinanzen.xml"
    }
}

# Doppelklick-Starter fuer das Update, direkt im Programmordner.
#
# Er wird erzeugt und nicht aus dem Paket kopiert: so zeigt er dauerhaft auf
# current\ und ueberlebt jedes Update - dasselbe Muster wie dienst\backup.cmd.
# Geschrieben wird er von install_service.ps1 UND von update.ps1: eine
# Installation aus der Zeit vor diesem Starter bekommt ihn damit beim ersten
# Update nachgereicht, und eine Verbesserung am Starter verteilt sich von
# selbst.
#
# ASCII und CRLF: eine .cmd mit Umlauten faellt der Konsolen-Codepage zum
# Opfer, und cmd.exe stolpert bei reinen LF-Zeilenenden ueber Bloecke.
function SchreibeUpdateStarter([string]$programm) {
    $ziel = Join-Path $programm "update.cmd"
    $zeilen = @(
        '@echo off'
        'rem Erzeugt von install_service.ps1 bzw. update.ps1 - nicht von Hand aendern.'
        'rem Ruft die Update-Logik der installierten Fassung auf. Der Pfad zeigt auf'
        'rem current\ und bleibt darum ueber Updates hinweg gueltig.'
        'setlocal'
        'set "LOGIK=%~dp0current\scripts\prod\update.cmd"'
        'if not exist "%LOGIK%" ('
        '  echo.'
        '  echo   Die Update-Logik fehlt in der installierten Fassung:'
        '  echo     %LOGIK%'
        '  echo   Das kommt nach einem Rollback auf eine Version von vor diesem'
        '  echo   Starter vor. Dann von Hand aktualisieren:'
        '  echo     %~dp0current\scripts\prod\update.ps1 -Paket ^<zip^>'
        '  echo.'
        '  pause'
        '  exit /b 1'
        ')'
        'call "%LOGIK%" /aus-updates %*'
        'exit /b %ERRORLEVEL%'
    )
    [System.IO.File]::WriteAllText($ziel, ($zeilen -join "`r`n") + "`r`n",
        (New-Object System.Text.ASCIIEncoding))
    return $ziel
}

function AlembicRevision([string]$python, [string]$versionsOrdner) {
    # Laeuft bewusst ohne Migration (siehe app.db_init.pruefe_schema): nur die
    # Revision der Datenbank wird gelesen.
    $code = @"
import sys
from app.database import engine
try:
    with engine.connect() as c:
        print(c.exec_driver_sql('SELECT version_num FROM alembic_version').scalar())
except Exception:
    print('')
"@
    $alt = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $versionsOrdner "backend"
    try {
        $out = & $python -c $code 2>$null
    } finally {
        $env:PYTHONPATH = $alt
    }
    if ($LASTEXITCODE -ne 0) { return "" }
    return ("$out" | Select-Object -Last 1).Trim()
}

# Auf den Dienst warten, statt einmal nach fester Frist zu fragen.
#
# Ein einzelner Versuch nach 5 Sekunden reicht nicht: beim ersten Start einer
# frisch gebauten venv laedt Python erst saemtliche Abhaengigkeiten, das dauert
# auf einem beschaeftigten Rechner deutlich laenger. Der Health-Check schlug
# dann fehl, obwohl die Anwendung Sekunden spaeter lief - und update.ps1 stieg
# vor Registry-Eintrag, Starter und Aufraeumen aus.
function WarteAufHealth([string]$url, [int]$MaxSekunden = 90) {
    $ende = (Get-Date).AddSeconds($MaxSekunden)
    $letzter = $null
    $punkte = 0
    while ((Get-Date) -lt $ende) {
        try {
            $resp = HealthAbfrage $url -TimeoutSec 5
            if ($punkte) { Write-Host "" }
            return $resp
        } catch {
            $letzter = $_
            Start-Sleep -Seconds 2
            Write-Host "." -NoNewline -ForegroundColor Gray
            $punkte++
        }
    }
    if ($punkte) { Write-Host "" }
    throw $letzter
}

function HealthAbfrage([string]$url, [int]$TimeoutSec = 10) {
    # Invoke-RestMethod kennt -SkipCertificateCheck erst ab PowerShell 7.
    # Auf einem frischen Windows ist aber nur Windows PowerShell 5.1 da, und
    # dort laesst sich die Zertifikatspruefung nur ueber den globalen Callback
    # abschalten. Betrifft ausschliesslich diesen Prozess und wird danach
    # wieder zurueckgesetzt.
    if ($PSVersionTable.PSVersion.Major -ge 6) {
        return Invoke-RestMethod $url -TimeoutSec $TimeoutSec -SkipCertificateCheck
    }
    $altCb  = [System.Net.ServicePointManager]::ServerCertificateValidationCallback
    $altTls = [System.Net.ServicePointManager]::SecurityProtocol
    try {
        if ($url -like "https://*") {
            [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
            # 5.1 bietet von Haus aus noch SSL3/TLS 1.0 an - unser Server nicht.
            [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        }
        return Invoke-RestMethod $url -TimeoutSec $TimeoutSec
    } finally {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = $altCb
        [System.Net.ServicePointManager]::SecurityProtocol = $altTls
    }
}
