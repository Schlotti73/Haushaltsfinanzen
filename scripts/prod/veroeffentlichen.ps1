# Hebt den aktuellen Stand in das oeffentliche Repository.
#
# Dieses Repository hat eine Historie, die nicht an die Oeffentlichkeit soll:
# sie enthaelt Jahre echter Haushaltsdaten in Testdateien, Screenshots und
# Commit-Texten. Das oeffentliche Repository traegt deshalb keinen gemeinsamen
# Vorfahren, sondern beginnt mit einem elternlosen Commit. Beide Historien
# lassen sich damit nie zusammenfuehren - ein "git push public main" waere
# zurueckgewiesen, und ein erzwungener Push haette die ganze Vorgeschichte
# mitgenommen.
#
# Der Weg ist darum immer derselbe: den *Baum* des aktuellen Commits nehmen,
# ihn an die Spitze des oeffentlichen Zweiges haengen und nur den pushen. Was
# drueben ankommt, ist genau der Dateibestand von hier - ohne jeden Commit,
# der hier je gemacht wurde.
#
# Aufruf (aus dem Projektstamm):
#   .\scripts\prod\veroeffentlichen.ps1 -Trockenlauf
#   .\scripts\prod\veroeffentlichen.ps1 -Nachricht "Texterkennung im Image"

param(
    [string]$Nachricht = "",      # leer = interaktive Abfrage
    [string]$Repo      = "Schlotti73/Haushaltsfinanzen",
    [string]$Remote    = "public",
    [string]$Zweig     = "main",
    [switch]$Trockenlauf,         # alles pruefen und zeigen, nichts pushen
    [switch]$Unsauber,            # Aenderungen im Arbeitsverzeichnis zulassen
    [switch]$Trotzdem,            # Funde der Inhaltspruefung uebergehen
    # Absender des oeffentlichen Commits. Bewusst nicht die Git-Identitaet
    # dieses Rechners: die traegt eine private Mailadresse, und Autor und
    # Committer stehen bei GitHub offen in jedem Commit - an einer Stelle, die
    # keine Dateipruefung je zu sehen bekommt. Die noreply-Adresse von GitHub
    # weist den Commit demselben Konto zu, ohne die Adresse zu nennen.
    [string]$Absender = "Schlotti73 <281000650+Schlotti73@users.noreply.github.com>"
)

$ErrorActionPreference = "Stop"
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent

function Step([string]$msg) {
    Write-Host "`n[$([datetime]::Now.ToString('HH:mm:ss'))] $msg" -ForegroundColor Cyan
}

function Abort([string]$msg) {
    Write-Host "`nFEHLER: $msg" -ForegroundColor Red
    exit 1
}

Set-Location $root

# -- 1. Voraussetzungen ------------------------------------------------------
Step "Pruefe Voraussetzungen..."

git rev-parse --git-dir *> $null
if ($LASTEXITCODE -ne 0) { Abort "Kein Git-Repository: $root" }

$aktuellerZweig = (git rev-parse --abbrev-ref HEAD).Trim()
if ($aktuellerZweig -ne $Zweig) {
    Abort "Es ist '$aktuellerZweig' ausgecheckt, veroeffentlicht wird aber '$Zweig'."
}

# Ein unsauberes Arbeitsverzeichnis ist hier gefaehrlicher als sonst: gepusht
# wird der Baum des Commits, nicht der der Dateien auf der Platte. Der Abbruch
# verhindert, dass jemand eine Aenderung veroeffentlicht glaubt, die er nur
# gespeichert und nicht committet hat.
$dreck = git status --porcelain
if ($dreck -and -not $Unsauber) {
    Write-Host ($dreck -join "`n") -ForegroundColor DarkYellow
    Abort "Arbeitsverzeichnis nicht sauber. Erst committen - gepusht wird der letzte Commit, nicht die Dateien. (-Unsauber umgeht das.)"
}

# -- 2. Gegenstelle ----------------------------------------------------------
Step "Pruefe Gegenstelle '$Remote'..."

$remoteUrl = (git remote get-url $Remote 2>$null)
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Remote '$Remote' fehlt, wird angelegt." -ForegroundColor DarkGray
    git remote add $Remote "https://github.com/$Repo.git"
    if ($LASTEXITCODE -ne 0) { Abort "Konnte Remote '$Remote' nicht anlegen." }
    $remoteUrl = (git remote get-url $Remote).Trim()
}
if ($remoteUrl -notmatch [regex]::Escape($Repo)) {
    Abort "Remote '$Remote' zeigt auf '$remoteUrl', erwartet wurde '$Repo'."
}
Write-Host "  $remoteUrl" -ForegroundColor DarkGray

git fetch --quiet $Remote $Zweig 2>$null
$fremdCommit = if ($LASTEXITCODE -eq 0) { (git rev-parse FETCH_HEAD).Trim() } else { "" }

$baum = (git rev-parse "$Zweig^{tree}").Trim()

if ($fremdCommit) {
    $fremdBaum = (git rev-parse "$fremdCommit^{tree}").Trim()
    Write-Host "  drueben: $($fremdCommit.Substring(0,7))  Baum $($fremdBaum.Substring(0,7))" -ForegroundColor DarkGray
    if ($fremdBaum -eq $baum) {
        Write-Host "`nNichts zu tun: der veroeffentlichte Stand ist bereits dieser Baum." -ForegroundColor Green
        exit 0
    }
} else {
    Write-Host "  Noch kein '$Zweig' drueben - der erste Commit wird elternlos." -ForegroundColor DarkGray
    $fremdBaum = ""
}

# -- 3. Was wird oeffentlich -------------------------------------------------
Step "Unterschied zum veroeffentlichten Stand"

if ($fremdBaum) {
    git --no-pager diff --stat $fremdBaum $baum
} else {
    $anzahl = ((git ls-tree -r --name-only $baum) | Measure-Object).Count
    Write-Host "  (vollstaendiger Dateibestand, $anzahl Dateien)"
}

# -- 4. Inhaltspruefung ------------------------------------------------------
# Jede Veroeffentlichung ist endgueltig: was einmal auf GitHub lag, steckt in
# Forks, Caches und Suchmaschinen. Die Pruefung ist bewusst stumpf und laeuft
# ueber den ganzen Baum, nicht nur ueber die Aenderung - ein Personenbezug, der
# vor drei Commits hereingerutscht ist, faellt sonst nie auf.
Step "Pruefe den Baum auf Personenbezug..."

$muster = [ordered]@{
    # Nur ein *konkreter* Benutzerordner ist ein Fund. "C:\Users\<Benutzer>"
    # steht so in der Betriebsdoku und ist genau richtig dort.
    "Pfad im Benutzerprofil" = '[A-Za-z]:[\\/]Users[\\/][A-Za-z0-9._-]'
    "E-Mail-Adresse"         = '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'
}

# In der LICENSE steht der Rechteinhaber mit Klarnamen, und das ist der Sinn
# einer Lizenz. Ohne diese Ausnahme schlaegt jede Pruefung dort an, und eine
# Warnung, die immer kommt, liest nach dem dritten Mal niemand mehr.
$ausnahmen = @(":!LICENSE")

# Begriffe, die nur hier bekannt sind - Namen, Orte, Vertragsnummern. Sie
# stehen bewusst in einer Datei unter config\, denn config\ ist .gitignore't:
# eine Verbotsliste echter Daten darf selbst nicht veroeffentlicht werden.
$tabuDatei = Join-Path $root "config\veroeffentlichung-tabu.txt"
if (Test-Path $tabuDatei) {
    $i = 0
    foreach ($zeile in Get-Content $tabuDatei) {
        $z = $zeile.Trim()
        if ($z -and -not $z.StartsWith("#")) { $i++; $muster["Tabu-Begriff $i"] = $z }
    }
    Write-Host "  $i Begriffe aus config\veroeffentlichung-tabu.txt" -ForegroundColor DarkGray
} else {
    Write-Host "  Hinweis: config\veroeffentlichung-tabu.txt fehlt - es laufen nur die allgemeinen Muster." -ForegroundColor DarkYellow
}

# Eine noreply-Adresse von GitHub ist genau das Gegenteil eines Personenbezugs:
# sie steht da, damit die echte Adresse nicht dasteht. Ohne diese Ausnahme
# meldet die Pruefung den Absender dieses Skripts bei jedem Lauf.
$harmlos = 'users\.noreply\.github\.com'

$funde = 0
foreach ($name in $muster.Keys) {
    $treffer = @(git grep -n -I -E -i -e $muster[$name] $Zweig -- @ausnahmen 2>$null |
                 Where-Object { $_ -notmatch $harmlos })
    if ($treffer.Count -gt 0) {
        $funde++
        Write-Host "  [$name] $($treffer.Count) Treffer" -ForegroundColor Yellow
        $treffer | Select-Object -First 10 | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
        if ($treffer.Count -gt 10) { Write-Host "    ... und $($treffer.Count - 10) weitere" -ForegroundColor DarkYellow }
    }
}

if ($funde -gt 0) {
    if (-not $Trotzdem) {
        $verb = if ($funde -eq 1) { "hat" } else { "haben" }
        Abort "$funde Muster $verb angeschlagen. Pruefen und bereinigen - oder, wenn alle Treffer harmlos sind, mit -Trotzdem wiederholen."
    }
    Write-Host "  $funde Muster angeschlagen, wegen -Trotzdem uebergangen." -ForegroundColor Yellow
} else {
    Write-Host "  nichts gefunden" -ForegroundColor Green
}

# -- 5. Commit bauen und pushen ----------------------------------------------
if (-not $Nachricht) {
    $Nachricht = Read-Host "`nCommit-Text fuer das oeffentliche Repository"
    if (-not $Nachricht) { Abort "Ohne Commit-Text wird nicht veroeffentlicht." }
}

if ($Trockenlauf) {
    Write-Host "`nTrockenlauf - es wurde nichts gepusht." -ForegroundColor Green
    Write-Host "  Entstanden waere: ein Commit mit Baum $($baum.Substring(0,7)) auf $Repo ($Zweig)."
    exit 0
}

Step "Baue Commit und pushe..."

if ($Absender -notmatch '^\s*(.+?)\s*<([^>]+)>\s*$') {
    Abort "-Absender muss die Form 'Name <adresse>' haben, war: '$Absender'"
}
$absName = $Matches[1]
$absMail = $Matches[2]
Write-Host "  Absender: $absName <$absMail>" -ForegroundColor DarkGray

$merker = @{}
foreach ($v in "GIT_AUTHOR_NAME","GIT_AUTHOR_EMAIL","GIT_COMMITTER_NAME","GIT_COMMITTER_EMAIL") {
    $merker[$v] = [Environment]::GetEnvironmentVariable($v)
}
try {
    $env:GIT_AUTHOR_NAME     = $absName
    $env:GIT_AUTHOR_EMAIL    = $absMail
    $env:GIT_COMMITTER_NAME  = $absName
    $env:GIT_COMMITTER_EMAIL = $absMail

    $elternArg = if ($fremdCommit) { @("-p", $fremdCommit) } else { @() }
    $neu = ($Nachricht | git commit-tree $baum @elternArg)
    if ($LASTEXITCODE -ne 0 -or -not $neu) { Abort "git commit-tree ist fehlgeschlagen." }
    $neu = $neu.Trim()
}
finally {
    # Die Git-Identitaet dieses Rechners wieder herstellen - alles andere in
    # dieser Sitzung committet sonst unter dem falschen Absender.
    foreach ($v in $merker.Keys) {
        if ($null -eq $merker[$v]) { Remove-Item "env:$v" -ErrorAction SilentlyContinue }
        else { Set-Item "env:$v" $merker[$v] }
    }
}

git push $Remote "${neu}:refs/heads/$Zweig"
if ($LASTEXITCODE -ne 0) { Abort "Push nach $Repo fehlgeschlagen." }

Write-Host "`nVeroeffentlicht." -ForegroundColor Green
Write-Host "  Commit : $neu"
Write-Host "  Repo   : https://github.com/$Repo/commits/$Zweig"
Write-Host "  Seite  : https://schlotti73.github.io/Haushaltsfinanzen/demo/ (baut neu, sobald sich docs\ geaendert hat)"
