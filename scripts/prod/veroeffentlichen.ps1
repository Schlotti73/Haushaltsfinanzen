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
# Sitzt auf HEAD ein Versions-Tag (v*), wandert er mit - gesetzt auf den
# Baum-Commit, den dieses Skript baut. Drueben ist er kein Beiwerk: er loest
# .github/workflows/docker.yml aus, und daraus entsteht das Container-Image
# zur Version. Sitzt keiner auf HEAD, wird nur der Stand veroeffentlicht -
# eine Zwischenveroeffentlichung von Doku oder Rundgang braucht kein Image.
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

# Der Versions-Tag auf HEAD, oder "" wenn keiner da ist.
#
# Das Container-Image entsteht drueben: dort liegt
# .github/workflows/docker.yml, und ausgeloest wird sie von einem v*-Tag. Von
# hier kann der Tag nicht einfach mitwandern, denn er zeigt auf einen Commit,
# den es drueben nicht gibt - gepusht wird ja nur der Baum. Er wird deshalb an
# den Baum-Commit gehaengt, den dieses Skript baut.
#
# Mehrere Versions-Tags auf einem Commit sind ein Unfall (ein
# zurueckgenommener Tag, der liegen geblieben ist). Raten waere hier teuer:
# der Tag bestimmt die Version des Images.
function TagAufHead() {
    $tags = @(git tag --points-at HEAD 2>$null | Where-Object { $_ -match '^v\d' })
    if ($tags.Count -eq 0) { return "" }
    if ($tags.Count -gt 1) {
        Abort "Auf HEAD sitzen mehrere Versions-Tags ($($tags -join ', ')) - unklar, welche Version veroeffentlicht werden soll."
    }
    return $tags[0].Trim()
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

$tag = TagAufHead
if ($tag) {
    # Ein Release-Tag ist unveraenderlich: an ihm haengen das Image und das
    # Release mit dem Windows-Paket. Liegt er drueben schon, ist diese Version
    # veroeffentlicht - dann ist etwas anderes schiefgelaufen als dieser Lauf
    # vermutet, und ein zweiter Tag auf denselben Namen waere die falsche
    # Antwort darauf. Eine Korrektur braucht eine neue Version.
    git ls-remote --exit-code --tags $Remote "refs/tags/$tag" *> $null
    if ($LASTEXITCODE -eq 0) {
        Abort "Tag '$tag' liegt in $Repo schon - diese Version ist veroeffentlicht. Eine Korrektur braucht eine neue Versionsnummer."
    }
    Write-Host "  Tag: $tag - loest drueben den Image-Bau aus" -ForegroundColor DarkGray
} else {
    Write-Host "  Kein Versions-Tag auf HEAD - nur der Stand wird veroeffentlicht, kein Image gebaut." -ForegroundColor DarkGray
}

if ($fremdCommit) {
    $fremdBaum = (git rev-parse "$fremdCommit^{tree}").Trim()
    Write-Host "  drueben: $($fremdCommit.Substring(0,7))  Baum $($fremdBaum.Substring(0,7))" -ForegroundColor DarkGray
    if ($fremdBaum -eq $baum) {
        if (-not $tag) {
            Write-Host "`nNichts zu tun: der veroeffentlichte Stand ist bereits dieser Baum." -ForegroundColor Green
            exit 0
        }
        # Baum schon drueben, Tag noch nicht: der Stand war vorab
        # veroeffentlicht, jetzt kommt die Version dazu. Der Tag gehoert dann
        # an den bestehenden Commit - sonst gaebe es zur Version kein Image.
        # Die Inhaltspruefung entfaellt hier mit Absicht: oeffentlich wird
        # nichts Neues, dieser Baum liegt Zeichen fuer Zeichen schon drueben.
        Write-Host "  Baum liegt drueben schon - es fehlt nur der Tag '$tag'." -ForegroundColor DarkGray
        if ($Trockenlauf) {
            Write-Host "`nTrockenlauf - es wurde nichts gepusht." -ForegroundColor Green
            Write-Host "  Gesetzt wuerde: Tag $tag auf $($fremdCommit.Substring(0,7)) in $Repo."
            exit 0
        }
        Step "Setze Tag '$tag' auf den bestehenden Commit..."
        git push $Remote "${fremdCommit}:refs/tags/$tag"
        if ($LASTEXITCODE -ne 0) { Abort "Tag-Push nach $Repo fehlgeschlagen." }
        Write-Host "`nTag '$tag' gesetzt." -ForegroundColor Green
        Write-Host "  Image-Bau: https://github.com/$Repo/actions"
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
    if ($tag) { Write-Host "  Dazu der Tag $tag - er loest drueben den Image-Bau aus." }
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

    # Die Nachricht als Argument, nicht durch die Pipe: PowerShell schickt
    # einem externen Programm je nach Konsole und Fassung ein BOM voraus, und
    # das stuende dann unsichtbar am Anfang des oeffentlichen Commit-Textes.
    $elternArg = if ($fremdCommit) { @("-p", $fremdCommit) } else { @() }
    $neu = (git commit-tree $baum @elternArg -m $Nachricht)
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

# Der Tag erst nach dem Zweig: er zeigt auf denselben Commit, und ein Tag auf
# einen Commit, den drueben kein Zweig traegt, waere ein Fundstueck ohne
# Zusammenhang. Ein Fehlschlag hier ist ein Hinweis und kein Abbruch - der
# Stand ist dann schon veroeffentlicht, und ein rotes Ende wuerde das
# Gegenteil behaupten.
$tagGesetzt = $false
if ($tag) {
    Step "Setze Tag '$tag'..."
    git push $Remote "${neu}:refs/tags/$tag"
    if ($LASTEXITCODE -eq 0) {
        $tagGesetzt = $true
    } else {
        Write-Host "  Hinweis: Tag-Push fehlgeschlagen - von Hand nachziehen, sonst entsteht kein Image:" -ForegroundColor DarkYellow
        Write-Host "    git push $Remote ${neu}:refs/tags/$tag" -ForegroundColor DarkYellow
    }
}

Write-Host "`nVeroeffentlicht." -ForegroundColor Green
Write-Host "  Commit : $neu"
Write-Host "  Repo   : https://github.com/$Repo/commits/$Zweig"
Write-Host "  Seite  : https://schlotti73.github.io/Haushaltsfinanzen/demo/ (baut neu, sobald sich docs\ geaendert hat)"
if ($tagGesetzt) {
    Write-Host "  Tag    : $tag"
    Write-Host "  Image  : https://github.com/$Repo/actions (Bau laeuft an)"
    Write-Host "`nDanach: Update-Test auf dem Pruefstand, und erst dann das Release mit dem ZIP" -ForegroundColor Cyan
    Write-Host "anlegen - es ist das Signal, an dem die Installationen die Version erkennen." -ForegroundColor Cyan
}
