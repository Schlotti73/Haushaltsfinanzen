# Erstellt ein Release-Paket der Haushaltsfinanz-App.
#
# Das Paket ist der einzige Weg in die Produktion: es enthaelt das vorgebaute
# Frontend und alle Python-Wheels, damit der Ziel-PC weder Git noch Node.js
# noch Internet braucht. Siehe docs/release-paket.md.
#
# Aufruf (aus dem Projektstamm, nach "npm run build"):
#   .\scripts\prod\create_prod_zip.ps1
#   .\scripts\prod\create_prod_zip.ps1 -Version v1.5.0      # ohne Rueckfrage
#   .\scripts\prod\create_prod_zip.ps1 -OhneTag             # Vorabpaket zum Testen

param(
    [string]$OutputDir = "",      # leer = Projektstamm
    [string]$Version   = "",      # leer = interaktive Abfrage
    [switch]$OhneTag,             # kein Tag anlegen (Vorabpaket)
    [switch]$Unsauber,            # Aenderungen im Arbeitsverzeichnis zulassen
    # Das oeffentliche Repository, aus dem die laufenden Installationen ihr
    # Update holen - dasselbe, das den Quellstand und das Container-Image
    # traegt. Dieses Skript laedt nichts hoch, es nennt am Ende nur den
    # passenden gh-Befehl; die Voreinstellung muss aber zu der in
    # backend/app/services/update.py passen.
    [string]$ReleaseRepo = "Schlotti73/Haushaltsfinanzen"
)

$ErrorActionPreference = "Stop"
$root   = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$python = "$root\backend\.venv\Scripts\python.exe"

function Step([string]$msg) {
    Write-Host "`n[$([datetime]::Now.ToString('HH:mm:ss'))] $msg" -ForegroundColor Cyan
}

function Abort([string]$msg) {
    Write-Host "`nFEHLER: $msg" -ForegroundColor Red
    exit 1
}

# ── 1. Voraussetzungen ───────────────────────────────────────────────────────
Step "Pruefe Voraussetzungen…"

# Das Frontend ist Paketinhalt und kann auf dem Ziel-PC nicht gebaut werden.
# Fehlt es, waere das Paket installierbar und faellt erst dort mit einer leeren
# Seite auf - deshalb harter Abbruch, keine Warnung.
#
# Zielordner ist backend\static (frontend\vite.config.js: outDir), nicht
# frontend\dist - denselben Ort liest backend\app\main.py.
if (-not (Test-Path "$root\backend\static\index.html")) {
    Abort @"
backend\static\index.html fehlt - das Paket haette kein Frontend.
  Abhilfe:  cd frontend; npm run build
"@
}

if (-not (Test-Path $python)) {
    Abort "Python-venv fehlt: $python`n  Abhilfe: scripts\prod\install_service.ps1 oder 'python -m venv backend\.venv'"
}

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Abort "git nicht gefunden - die Versionsnummer kommt aus den Git-Tags."
}

# Windows PowerShell 5.1 - das einzige, was auf einem frischen Windows sicher
# vorhanden ist - liest eine .ps1 ohne BOM als Windows-1252. Aus den Umlauten
# und Rahmenzeichen werden dann Zeichen wie ” , und das ist in PowerShell ein
# gueltiges Zeichenkettenende: das Skript bricht schon beim Parsen ab, lange
# bevor irgendetwas laeuft. Unter pwsh 7 faellt das nie auf, dort ist UTF-8 der
# Standard. Deshalb hier pruefen und nicht erst auf dem Ziel-PC.
$ohneBom = @(Get-ChildItem "$root\scripts" -Recurse -Filter *.ps1 | Where-Object {
    $kopf = [System.IO.File]::ReadAllBytes($_.FullName) | Select-Object -First 3
    -not ($kopf.Count -eq 3 -and $kopf[0] -eq 0xEF -and $kopf[1] -eq 0xBB -and $kopf[2] -eq 0xBF)
})
if ($ohneBom) {
    $ohneBom | ForEach-Object { Write-Host "    $($_.FullName.Substring($root.Length + 1))" -ForegroundColor Gray }
    Abort @"
Diese Skripte haben kein UTF-8-BOM.
  Windows PowerShell 5.1 liest sie dann falsch und bricht mit einem
  Parserfehler ab - das Setup startet auf dem Ziel-PC gar nicht erst.
  Abhilfe (je Datei):
    `$p = 'scripts\prod\beispiel.ps1'
    [System.IO.File]::WriteAllText(`$p, (Get-Content `$p -Raw), (New-Object Text.UTF8Encoding `$true))
"@
}

$dirty = (git -C $root status --porcelain)
if ($dirty -and -not $Unsauber) {
    Write-Host "  Nicht eingecheckte Aenderungen:" -ForegroundColor Yellow
    $dirty | Select-Object -First 15 | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
    Abort @"
Das Arbeitsverzeichnis ist nicht sauber.
  Ein Paket muss sich einem Commit zuordnen lassen, sonst ist der Quellstand
  spaeter nicht mehr rekonstruierbar - und genau den braucht ein Rollback.
  Abhilfe: committen, oder -Unsauber fuer ein Wegwerf-Paket.
"@
}

# ── 2. Version bestimmen ─────────────────────────────────────────────────────
$letztesTag = (git -C $root describe --tags --abbrev=0 2>$null)
if ($LASTEXITCODE -ne 0) { $letztesTag = "" }

# Neue Alembic-Migrationen seit dem letzten Tag. Sie entscheiden, ob ein
# Rollback verlustfrei moeglich waere - und damit ueber die Versionsstufe.
$neueMigrationen = @()
if ($letztesTag) {
    $neueMigrationen = @(git -C $root diff --name-only --diff-filter=A "$letztesTag..HEAD" -- "backend/alembic/versions/" |
        Where-Object { $_ -match '\.py$' })
    $abstand = (git -C $root rev-list --count "$letztesTag..HEAD")
} else {
    $neueMigrationen = @(git -C $root ls-files "backend/alembic/versions/*.py")
    $abstand = (git -C $root rev-list --count HEAD)
}

function NaechsteVersion([string]$tag, [string]$stufe) {
    if ($tag -notmatch '^v?(\d+)\.(\d+)\.(\d+)') { return "v0.1.0" }
    $ma = [int]$Matches[1]; $mi = [int]$Matches[2]; $pa = [int]$Matches[3]
    switch ($stufe) {
        "major" { return "v$($ma + 1).0.0" }
        "minor" { return "v$ma.$($mi + 1).0" }
        default { return "v$ma.$mi.$($pa + 1)" }
    }
}

if (-not $Version -and -not $OhneTag) {
    $vPatch = NaechsteVersion $letztesTag "patch"
    $vMinor = NaechsteVersion $letztesTag "minor"
    $vMajor = NaechsteVersion $letztesTag "major"
    $mitMigration = $neueMigrationen.Count -gt 0
    $empfohlen = if ($mitMigration) { 2 } else { 1 }

    Write-Host ""
    if ($letztesTag) {
        Write-Host "  Letztes Release:  $letztesTag  (vor $abstand Commits)"
    } else {
        Write-Host "  Letztes Release:  - (noch kein Tag vorhanden)" -ForegroundColor Yellow
    }
    Write-Host "  Arbeitsverzeichnis: $(if ($dirty) { 'mit Aenderungen' } else { 'sauber' })"
    Write-Host ""
    if ($mitMigration) {
        Write-Host "  Neue Alembic-Migrationen: $($neueMigrationen.Count)" -ForegroundColor Yellow
        $neueMigrationen | ForEach-Object { Write-Host "    $(Split-Path $_ -Leaf)" -ForegroundColor Gray }
        Write-Host "    -> Empfehlung: Minor, weil ein Rollback nicht verlustfrei waere" -ForegroundColor Yellow
    } else {
        Write-Host "  Neue Alembic-Migrationen: keine" -ForegroundColor Green
        Write-Host "    -> Empfehlung: Patch, ein Rollback bleibt verlustfrei" -ForegroundColor Gray
    }
    Write-Host ""
    $m = if ($empfohlen -eq 1) { "   (empfohlen)" } else { "" }
    Write-Host "    [1] $($vPatch.PadRight(9)) Patch  - Fehlerkorrekturen, kein Schema-Wechsel$m"
    $m = if ($empfohlen -eq 2) { "   (empfohlen)" } else { "" }
    Write-Host "    [2] $($vMinor.PadRight(9)) Minor  - neue Funktion und/oder Migration$m"
    Write-Host "    [3] $($vMajor.PadRight(9)) Major  - Installation braucht manuellen Eingriff"
    Write-Host "    [4] eigene Nummer eingeben"
    Write-Host "    [5] ohne Tag bauen (Vorabpaket zum Testen)"
    Write-Host ""

    $wahl = Read-Host "  Auswahl [$empfohlen]"
    if (-not $wahl) { $wahl = "$empfohlen" }

    switch ($wahl) {
        "1" {
            if ($mitMigration) {
                Abort @"
Patch passt nicht: seit $letztesTag sind $($neueMigrationen.Count) Migrationen dazugekommen.
  Die Stufe sagt auf dem Prod-PC, was ein Rollback kostet - eine Patch-Nummer
  wuerde dort einen verlustfreien Rueckweg versprechen, den es nicht gibt.
  Abhilfe: Minor waehlen, oder -Version $vPatch erzwingen.
"@
            }
            $Version = $vPatch
        }
        "2" { $Version = $vMinor }
        "3" { $Version = $vMajor }
        "4" {
            $Version = (Read-Host "    Versionsnummer (z. B. v1.5.0)").Trim()
            if ($Version -notmatch '^v\d+\.\d+\.\d+') { Abort "Unerwartete Versionsnummer: '$Version' (erwartet: v<major>.<minor>.<patch>)" }
        }
        "5" { $OhneTag = $true }
        default { Abort "Unerwartete Auswahl: '$wahl'" }
    }
}

if ($OhneTag) {
    # git describe liefert dann z. B. v1.4.2-11-gbdc3156 - ein Zwischenstand
    # bleibt damit auch Monate spaeter als solcher erkennbar.
    $paketVersion = (git -C $root describe --tags --always 2>$null)
    if (-not $paketVersion) { $paketVersion = "0.0.0-$(git -C $root rev-parse --short HEAD)" }
    $paketVersion = "$paketVersion-vorab"
    Write-Host "`n  Vorabpaket: $paketVersion (kein Tag wird angelegt)" -ForegroundColor Yellow
} else {
    if (git -C $root tag --list $Version) {
        Abort "Das Tag $Version existiert bereits.`n  Abhilfe: andere Nummer waehlen, oder 'git tag -d $Version'."
    }
    Step "Lege Tag $Version an…"
    git -C $root tag -a $Version -m "Release $Version"
    if ($LASTEXITCODE -ne 0) { Abort "Tag konnte nicht angelegt werden" }
    $paketVersion = $Version
}

# ── 3. Staging aufbauen ──────────────────────────────────────────────────────
$timestamp = Get-Date -Format "yyyyMMdd-HHmm"
$staging   = Join-Path ([System.IO.Path]::GetTempPath()) "haushaltsfinanz-paket-$timestamp"
New-Item -ItemType Directory -Force $staging | Out-Null

Step "Sammle Paketinhalt…"

# Nur Programmteile. Keine Einstellungen (config\) und keine Nutzerdaten: die
# config\*.json dieses Rechners enthalten absolute Pfade und wuerden auf dem
# Ziel-PC die dortige Konfiguration zerstoeren. Siehe docs/release-paket.md.
$include = @(
    "backend\app",
    "backend\alembic",
    "backend\alembic.ini",
    "backend\requirements.txt",
    "backend\tessdata",
    "config-vorlagen",           # Saat-Daten, nur lesend
    "db\schema.sql",
    "scripts\prod",
    "scripts\init_db.py",
    "scripts\backup.py",
    "scripts\netzlaufwerk.py",   # von backup.py importiert
    "backend\static",            # vorgebautes Frontend (vite outDir)
    # Nur die Betriebsanleitungen, nicht der ganze docs-Ordner. Die uebrigen
    # Dokumente sind Entwicklungsunterlagen - Datenmodell, Phasenplan,
    # Mapping-Tabellen. Einem fremden Nutzer sagen sie nichts, und das Paket
    # soll klein bleiben.
    "docs\betrieb.md",
    "docs\docker.md"
)

foreach ($rel in $include) {
    $src = Join-Path $root $rel
    if (-not (Test-Path $src)) { Abort "Paketinhalt fehlt: $rel" }
    $dst = Join-Path $staging $rel
    New-Item -ItemType Directory -Force (Split-Path $dst -Parent) | Out-Null
    Copy-Item $src $dst -Recurse -Force
}

# Weder die Wheels des Build-Rechners noch Bytecode gehoeren ins Paket
Get-ChildItem $staging -Recurse -Directory -Filter "__pycache__" |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ascii, nicht utf8: Out-File -Encoding utf8 setzt unter Windows PowerShell 5.1
# ein BOM davor, und das landet dann in der Versionsnummer. Versionsnummern
# sind ohnehin ASCII.
$paketVersion | Out-File (Join-Path $staging "VERSION") -Encoding ascii -NoNewline

# Starter im Paketstamm: nach dem Entpacken soll ein Doppelklick genuegen,
# ohne dass man erst nach scripts\prod navigieren muss.
@"
@echo off
rem Startpunkt nach dem Entpacken - ruft scripts\prod\setup.cmd auf.
call "%~dp0scripts\prod\setup.cmd" %*
"@ | Out-File (Join-Path $staging "setup.cmd") -Encoding ascii

# Dasselbe fuer das Update: wer das Paket entpackt hat, soll es per Doppelklick
# einspielen koennen. Ohne Argument nimmt scripts\prod\update.cmd diesen
# entpackten Ordner als Quelle (-Ordner) - es wird nichts noch einmal entpackt.
@"
@echo off
rem Startpunkt nach dem Entpacken - ruft scripts\prod\update.cmd auf.
call "%~dp0scripts\prod\update.cmd" %*
exit /b %ERRORLEVEL%
"@ | Out-File (Join-Path $staging "update.cmd") -Encoding ascii

# ── 4. Wheels laden ──────────────────────────────────────────────────────────
Step "Lade Python-Wheels (fuer die Offline-Installation)…"
$wheels = Join-Path $staging "wheels"
New-Item -ItemType Directory -Force $wheels | Out-Null

# --only-binary erzwingt fertige Wheels: eine Quellverteilung muesste auf dem
# Ziel-PC kompiliert werden, und dort stehen keine Build-Werkzeuge.
& $python -m pip download -r "$root\backend\requirements.txt" -d $wheels --only-binary=:all: -q
if ($LASTEXITCODE -ne 0) {
    Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
    Abort "pip download fehlgeschlagen - ohne die Wheels waere das Paket nicht offline installierbar."
}
$anzahl = (Get-ChildItem $wheels -File).Count
$wheelMB = [math]::Round((Get-ChildItem $wheels -File | Measure-Object -Sum Length).Sum / 1MB, 1)
Write-Host "  $anzahl Wheels, $wheelMB MB" -ForegroundColor Gray

# ── 5. ZIP schreiben ─────────────────────────────────────────────────────────
Step "Schreibe ZIP…"
$destDir = if ($OutputDir) { $OutputDir } else { $root }
New-Item -ItemType Directory -Force $destDir | Out-Null
$zipPath = Join-Path $destDir "Haushaltsfinanz_${paketVersion}.zip"

if (Test-Path $zipPath) { Remove-Item $zipPath -Force }

# Nicht Compress-Archive: unter Windows PowerShell 5.1 schreibt es (wie
# ZipFile.CreateFromDirectory im .NET Framework) Backslashes als Pfadtrenner.
# Die ZIP-Spezifikation verlangt "/". Explorer und Expand-Archive verzeihen
# das, viele andere Werkzeuge nicht - und ein Paket, das sich nur mit dem
# Windows-Explorer oeffnen laesst, ist unnoetig waehlerisch.
Add-Type -AssemblyName System.IO.Compression
Add-Type -AssemblyName System.IO.Compression.FileSystem
$basis = (Resolve-Path $staging).Path.TrimEnd('\')
$archiv = [System.IO.Compression.ZipFile]::Open($zipPath, "Create")
try {
    foreach ($datei in Get-ChildItem $basis -Recurse -File) {
        $eintrag = $datei.FullName.Substring($basis.Length).TrimStart('\').Replace('\', '/')
        [void][System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
            $archiv, $datei.FullName, $eintrag,
            [System.IO.Compression.CompressionLevel]::Optimal)
    }
} finally {
    $archiv.Dispose()
}
Remove-Item $staging -Recurse -Force

$sizeMB = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)

# ── 6. Zusammenfassung ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "  Paket erstellt: $zipPath ($sizeMB MB)" -ForegroundColor Green
Write-Host ""
Write-Host "  Weiter auf dem Ziel-PC:" -ForegroundColor Yellow
Write-Host "    Erstinstallation: ZIP freigeben (Rechtsklick > Eigenschaften > Zulassen),"
Write-Host "                      entpacken, setup.cmd starten"
Write-Host "    Update:           entpacken, update.cmd starten"
Write-Host "                      (oder .\scripts\prod\update.ps1 -Paket <pfad zur zip>)"
if (-not $OhneTag) {
    Write-Host ""
    Write-Host "  Tag $paketVersion ist nur lokal - noch zu veroeffentlichen:" -ForegroundColor Yellow
    Write-Host "    git push origin main --follow-tags"
    Write-Host "    .\scripts\prod\veroeffentlichen.ps1 -Nachricht `"...`"   # nimmt den Tag mit und"
    Write-Host "                                                         # loest den Image-Bau aus"
    Write-Host ""

    # Die Release-Beschreibung steht in docs\aenderungen.md, also im Baum -
    # nur so laeuft sie durch dieselbe Pruefung auf Personenbezug wie der
    # Quelltext. Hier wird der Abschnitt dieser Version herausgeschnitten.
    #
    # Die Datei dafuer liegt im TEMP-Ordner und nicht neben dem ZIP: eine neue
    # Datei im Arbeitsbaum liesse veroeffentlichen.ps1 mit "nicht sauber"
    # abbrechen, und zwar an der Stelle, an der dieser Ablauf gerade ist.
    $hinweisDatei = Join-Path $env:TEMP "Haushaltsfinanz_${paketVersion}_hinweise.md"
    $aenderungen  = Join-Path $root "docs\aenderungen.md"
    $abschnitt = @()
    if (Test-Path $aenderungen) {
        $drin = $false
        foreach ($zeile in (Get-Content $aenderungen -Encoding UTF8)) {
            if ($zeile -match '^##\s') {
                if ($drin) { break }
                $drin = ($zeile -match ('^##\s+' + [regex]::Escape($paketVersion) + '(\s|$)'))
                continue
            }
            if ($drin) { $abschnitt += $zeile }
        }
    }

    if ($abschnitt.Count -gt 0) {
        # Ohne BOM: gh nimmt die Datei Byte fuer Byte als Beschreibung, und ein
        # BOM stuende als unsichtbares Zeichen am Anfang des Release-Textes.
        [IO.File]::WriteAllText($hinweisDatei,
                                (($abschnitt -join "`r`n").Trim() + "`r`n"),
                                (New-Object Text.UTF8Encoding($false)))
        Write-Host "  Beschreibung aus docs\aenderungen.md: $hinweisDatei" -ForegroundColor DarkGray
        $notizen = "--notes-file `"$hinweisDatei`""
    } else {
        Write-Host "  Hinweis: docs\aenderungen.md hat keinen Abschnitt '## $paketVersion' -" -ForegroundColor DarkYellow
        Write-Host "           erst dort eintragen, sonst steht das Release ohne Beschreibung da" -ForegroundColor DarkYellow
        Write-Host "           (sie ist es, die die Anwendung unter Programm-Update anzeigt)." -ForegroundColor DarkYellow
        $notizen = "--notes-file <abschnitt aus docs\aenderungen.md>"
    }
    Write-Host ""
    Write-Host "  Zuletzt - erst nach dem Image-Bau und dem Pruefstand-Test:" -ForegroundColor Yellow
    Write-Host "    gh release create $paketVersion `"$zipPath`" ``"
    Write-Host "       --repo $ReleaseRepo ``"
    Write-Host "       --title $paketVersion $notizen"
}
Write-Host ""
