# Legt eine Dev-Kopie der produktiven Datenbank an und schaltet sie in der
# Registry (config/datenbanken.json) aktiv. Die Produktivdatei wird dabei nur
# gelesen, nie geschrieben.
#
#   .\scripts\dev\copy_prod_db.ps1                 Kopie dev_<Zeitstempel> anlegen + aktiv schalten
#   .\scripts\dev\copy_prod_db.ps1 -Name test      eigener Name (Datei dev-db\test.db)
#   .\scripts\dev\copy_prod_db.ps1 -Force          vorhandene Kopie gleichen Namens ueberschreiben
#   .\scripts\dev\copy_prod_db.ps1 -NurKopie       nur kopieren, Registry nicht umstellen
#   .\scripts\dev\copy_prod_db.ps1 -Zurueck        Registry wieder auf die Produktivdatenbank stellen
#   .\scripts\dev\copy_prod_db.ps1 -Liste          registrierte Datenbanken anzeigen

param(
    [string]$Quelle,
    [string]$Name,
    [switch]$Force,
    [switch]$NurKopie,
    [switch]$Zurueck,
    [switch]$Liste,
    [switch]$NichtStoppen
)

$ErrorActionPreference = "Stop"

$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$registryPfad = Join-Path $root "config\datenbanken.json"
$prodPfad = if ($Quelle) { $Quelle } else { Join-Path $root "finanzen.db" }
$devOrdner = Join-Path $root "dev-db"

function Read-Registry {
    if (-not (Test-Path $registryPfad)) { return @() }
    $daten = Get-Content $registryPfad -Raw -Encoding utf8 | ConvertFrom-Json
    if ($null -eq $daten.datenbanken) { return @() }
    return @($daten.datenbanken)
}

function Write-Registry($eintraege) {
    $json = [ordered]@{ datenbanken = @($eintraege) } | ConvertTo-Json -Depth 5
    $utf8 = New-Object System.Text.UTF8Encoding $false
    [System.IO.File]::WriteAllText($registryPfad, $json, $utf8)
}

function Show-Registry {
    foreach ($e in Read-Registry) {
        $marke = if ($e.aktiv) { "* aktiv " } else { "        " }
        $farbe = if ($e.aktiv) { "Green" } else { "Gray" }
        Write-Host ("{0}[{1}] {2}" -f $marke, $e.id, $e.name) -ForegroundColor $farbe
        Write-Host ("            {0}" -f $e.dateipfad) -ForegroundColor DarkGray
    }
}

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

# --- Nur anzeigen ---------------------------------------------------------
if ($Liste) {
    Show-Registry
    exit 0
}

# --- Zurueck auf Produktion ----------------------------------------------
if ($Zurueck) {
    $eintraege = Read-Registry
    $ziel = $eintraege | Where-Object { $_.dateipfad -eq (Resolve-Path $prodPfad).Path } | Select-Object -First 1
    if (-not $ziel) {
        Write-Host "FEHLER Kein Registry-Eintrag fuer $prodPfad gefunden." -ForegroundColor Red
        Show-Registry
        exit 1
    }
    foreach ($e in $eintraege) { $e.aktiv = ($e.id -eq $ziel.id) }
    Write-Registry $eintraege
    Write-Host "Aktive Datenbank: $($ziel.name) -> $($ziel.dateipfad)" -ForegroundColor Yellow
    Write-Host "ACHTUNG Das ist die produktive Datenbank - nicht zum Entwickeln benutzen." -ForegroundColor Red
    exit 0
}

# --- Kopie anlegen --------------------------------------------------------
if (-not (Test-Path $prodPfad)) {
    Write-Host "FEHLER Quelldatenbank nicht gefunden: $prodPfad" -ForegroundColor Red
    exit 1
}
$prodPfad = (Resolve-Path $prodPfad).Path

if (-not $Name) { $Name = "dev_" + (Get-Date -Format "yyyy-MM-dd_HHmm") }
if ($Name -notmatch '^[A-Za-z0-9._-]+$') {
    Write-Host "FEHLER Name darf nur Buchstaben, Ziffern, Punkt, Bindestrich und Unterstrich enthalten." -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Path $devOrdner -Force | Out-Null
$zielPfad = Join-Path $devOrdner "$Name.db"

if ($zielPfad -eq $prodPfad) {
    Write-Host "FEHLER Ziel ist die Produktivdatei selbst." -ForegroundColor Red
    exit 1
}
if ((Test-Path $zielPfad) -and -not $Force) {
    Write-Host "FEHLER Kopie existiert schon: $zielPfad  (mit -Force ueberschreiben)" -ForegroundColor Red
    exit 1
}

# Dev-Server beenden, damit die Quelle nicht mitten im Schreibvorgang kopiert wird
if (-not $NichtStoppen) {
    Write-Host "Beende laufende Dev-Server..." -ForegroundColor Yellow
    Stop-Port 8000
    Stop-Port 5173
    Start-Sleep -Seconds 1
}

Write-Host "Kopiere $prodPfad" -ForegroundColor Cyan
Write-Host "    ->  $zielPfad" -ForegroundColor Cyan
Copy-Item $prodPfad $zielPfad -Force
foreach ($endung in @("-wal", "-shm")) {
    $von = "$prodPfad$endung"
    if (Test-Path $von) {
        Copy-Item $von "$zielPfad$endung" -Force
        Write-Host "  $endung mitkopiert." -ForegroundColor Gray
    } else {
        Remove-Item "$zielPfad$endung" -ErrorAction SilentlyContinue
    }
}

# WAL in die Kopie einarbeiten und Kopie pruefen (nur die Kopie wird geschrieben)
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (Test-Path $python) {
    $pruefung = & $python -c @"
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
ok = con.execute('PRAGMA quick_check').fetchone()[0]
n = con.execute('SELECT count(*) FROM buchungen').fetchone()[0]
con.close()
print(f'{ok}|{n}')
"@ $zielPfad
    if ($LASTEXITCODE -eq 0 -and $pruefung) {
        $teile = ($pruefung | Select-Object -Last 1) -split '\|'
        Write-Host "Pruefung: quick_check=$($teile[0]), Buchungen=$($teile[1])" -ForegroundColor Gray
    } else {
        Write-Host "WARNUNG Kopie konnte nicht geprueft werden." -ForegroundColor Yellow
    }
} else {
    Write-Host "Hinweis: backend\.venv fehlt - Kopie wurde nicht geprueft." -ForegroundColor Yellow
}

$groesse = [math]::Round((Get-Item $zielPfad).Length / 1MB, 1)
Write-Host "Kopie angelegt ($groesse MB)." -ForegroundColor Green

# --- Registry umstellen ---------------------------------------------------
if ($NurKopie) {
    Write-Host "Registry unveraendert (-NurKopie)." -ForegroundColor Yellow
    exit 0
}

$eintraege = Read-Registry
if ($eintraege.Count -eq 0) {
    $eintraege = @([pscustomobject]@{ id = 1; name = "Standard"; dateipfad = $prodPfad; aktiv = $false })
}
$vorhanden = $eintraege | Where-Object { $_.dateipfad -eq $zielPfad } | Select-Object -First 1
if ($vorhanden) {
    $neueId = $vorhanden.id
} else {
    $neueId = [int]((($eintraege | ForEach-Object { [int]$_.id } | Measure-Object -Maximum).Maximum) + 1)
    $eintraege = @($eintraege) + [pscustomobject]@{ id = $neueId; name = $Name; dateipfad = $zielPfad; aktiv = $false }
}
foreach ($e in $eintraege) { $e.aktiv = ($e.id -eq $neueId) }
Write-Registry $eintraege

Write-Host ""
Show-Registry
Write-Host ""
Write-Host "OK  Dev-Kopie ist aktiv. Jetzt starten: .\scripts\dev\run.ps1" -ForegroundColor Green
Write-Host "    Zurueck auf Produktion: .\scripts\dev\copy_prod_db.ps1 -Zurueck" -ForegroundColor DarkGray
exit 0
