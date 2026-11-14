# Entfernt die Haushaltsfinanz-Installation.
#
# Der Datenordner wird NIE angetastet: Datenbank, Belege, Kontoauszuege und
# Einstellungen bleiben liegen, damit eine Neuinstallation sie wieder
# aufnehmen kann. Wer sie wirklich loswerden will, loescht den Ordner von Hand -
# das Skript nennt ihn am Ende.
#
# Liegt neben dem Dienst-Wrapper (<Programm>\dienst\), damit es auch dann noch
# funktioniert, wenn kein Versionsordner mehr vorhanden ist.

param(
    [string]$ServiceName = "Haushaltsfinanz",
    [string]$Programm    = "",
    [string]$Daten       = ""
)

$ErrorActionPreference = "Stop"
. "$PSScriptRoot\pfade.ps1"

if (-not (IstAdmin)) {
    Write-Host "Keine Adminrechte - starte neu als Administrator…" -ForegroundColor Yellow
    $shell = if (Cmd "pwsh") { "pwsh" } else { "powershell" }
    $argList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"",
                 "-ServiceName", "`"$ServiceName`"")
    if ($Programm) { $argList += @("-Programm", "`"$Programm`"") }
    if ($Daten)    { $argList += @("-Daten", "`"$Daten`"") }
    # -PassThru und .ExitCode, nicht $LASTEXITCODE: der bezieht sich allein auf
    # native Aufrufe im EIGENEN Prozess. Ohne das meldete ein gescheiterter
    # Lauf nach dem UAC-Neustart nach aussen Erfolg.
    $p = Start-Process $shell -Verb RunAs -ArgumentList $argList -Wait -PassThru
    exit $p.ExitCode
}

# ── 1. Installation finden ───────────────────────────────────────────────────
$regKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ServiceName"
$installedVersion = $null
if (Test-Path $regKey) {
    $reg = Get-ItemProperty $regKey -ErrorAction SilentlyContinue
    $installedVersion = $reg.DisplayVersion
    if (-not $Programm -and $reg.InstallLocation) { $Programm = $reg.InstallLocation }
    if (-not $Daten    -and $reg.DatenOrdner)     { $Daten    = $reg.DatenOrdner }
}
# Rueckfall: das Skript liegt in <Programm>\dienst\
if (-not $Programm) { $Programm = Split-Path $PSScriptRoot -Parent }
if (-not $Daten)    { $Daten    = $StandardDaten }

$winsw   = WinswPfade $Programm
$current = Join-Path $Programm "current"
$tessExe = "C:\Program Files\Tesseract-OCR\tesseract.exe"

$serviceExists  = [bool](Get-Service $ServiceName -ErrorAction SilentlyContinue)
$programmDa     = Test-Path $Programm
$tessInstalled  = Test-Path $tessExe
$fwRegeln       = @(Get-NetFirewallRule -DisplayName "Haushaltsfinanz :*" -ErrorAction SilentlyContinue)

# ── 2. Uebersicht ────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "╔══════════════════════════════════════════════════════════════╗" -ForegroundColor White
Write-Host "║          Haushaltsfinanzen - Deinstallation                  ║" -ForegroundColor White
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor White
Write-Host ""
if ($installedVersion) {
    Write-Host "  Installierte Version: $installedVersion" -ForegroundColor Yellow
} else {
    Write-Host "  Kein Software-Eintrag gefunden - Teildeinstallation moeglich." -ForegroundColor Yellow
}
Write-Host "  Programmordner:       $Programm"
if ($programmDa) {
    $vs = Versionsordner $Programm
    if ($vs) { Write-Host "    Versionen:          $(($vs | ForEach-Object { $_.Name }) -join ', ')" -ForegroundColor Gray }
}
Write-Host ""
Write-Host "  Datenordner:          $Daten" -ForegroundColor Green
Write-Host "    bleibt erhalten - Datenbank, Belege und Einstellungen" -ForegroundColor Green
Write-Host ""
Write-Host "  Waehlen Sie, was entfernt werden soll. Leere Eingabe = ueberspringen." -ForegroundColor Yellow
Write-Host ""

function Ask([string]$label, [bool]$vorhanden, [string]$hinweis = "") {
    if (-not $vorhanden) {
        Write-Host ("    {0,-34} nicht vorhanden - uebersprungen." -f $label) -ForegroundColor Gray
        return $false
    }
    $suffix = if ($hinweis) { " ($hinweis)" } else { "" }
    $eingabe = Read-Host ("    {0}{1} entfernen? [J/N]" -f $label, $suffix)
    return $eingabe -match "^[JjYy]"
}

$doService   = Ask "Windows-Dienst '$ServiceName'"  $serviceExists
$doFirewall  = Ask "Firewall-Regeln"                ([bool]$fwRegeln) (($fwRegeln | ForEach-Object { $_.DisplayName }) -join ', ')
$doRegistry  = Ask "Software-Eintrag (Registry)"    ($null -ne $installedVersion)
$doProgramm  = Ask "Programmordner samt Versionen"  $programmDa "$Programm - enthaelt keine Nutzerdaten"
$doTesseract = Ask "Tesseract-OCR"                  $tessInstalled "systemweite Deinstallation via winget"

Write-Host ""
$confirm = Read-Host "  Deinstallation jetzt starten? [J/N]"
if ($confirm -notmatch "^[JjYy]") { Write-Host "Abgebrochen." -ForegroundColor Yellow; exit 0 }

# ── 3. Dienst ────────────────────────────────────────────────────────────────
if ($doService) {
    Step "Stoppe und entferne Dienst '$ServiceName'…"
    if (Test-Path $winsw.Xml) {
        try { & $winsw.Exe stop $winsw.Xml 2>$null } catch {}
        Start-Sleep -Seconds 2
        try { & $winsw.Exe uninstall $winsw.Xml 2>$null } catch {}
    }
    if (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue) { sc.exe delete $ServiceName | Out-Null }
    Write-Host "  Dienst entfernt." -ForegroundColor Green
}

# ── 4. Firewall ──────────────────────────────────────────────────────────────
if ($doFirewall) {
    Step "Entferne Firewall-Regeln…"
    foreach ($r in $fwRegeln) {
        Remove-NetFirewallRule -DisplayName $r.DisplayName -ErrorAction SilentlyContinue
        Write-Host "  $($r.DisplayName)" -ForegroundColor Gray
    }
}

# ── 5. Registry ──────────────────────────────────────────────────────────────
if ($doRegistry) {
    Step "Entferne Software-Eintrag…"
    Remove-Item $regKey -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host "  Registry-Eintrag entfernt." -ForegroundColor Green
}

# ── 6. Programmordner ────────────────────────────────────────────────────────
if ($doProgramm) {
    if (-not $doService -and $serviceExists) {
        Write-Host "`n  Programmordner wird NICHT entfernt: der Dienst laeuft noch daraus." -ForegroundColor Yellow
    } else {
        Step "Entferne Programmordner…"
        # Die Junction zuerst und mit Directory.Delete: Remove-Item -Recurse
        # wuerde ihr folgen und den Inhalt des Zielordners mit loeschen.
        if (IstJunction $current) { [System.IO.Directory]::Delete($current, $false) }

        # Dieses Skript laeuft aus $Programm\dienst - der Ordner laesst sich
        # nicht unter den eigenen Fuessen wegziehen. Daher aufgeschoben per
        # getrenntem Prozess, der nach dem Ende dieses Skripts loescht.
        $rest = $Programm
        Get-ChildItem $Programm -Directory | Where-Object { $_.Name -ne "dienst" } |
            Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
        Get-ChildItem $Programm -File | Remove-Item -Force -ErrorAction SilentlyContinue
        Write-Host "  Versionen entfernt." -ForegroundColor Green

        $shell = if (Cmd "pwsh") { "pwsh" } else { "powershell" }
        Start-Process $shell -ArgumentList @(
            "-NoProfile", "-WindowStyle", "Hidden", "-Command",
            "Start-Sleep -Seconds 5; Remove-Item -LiteralPath '$rest' -Recurse -Force -ErrorAction SilentlyContinue"
        ) | Out-Null
        Write-Host "  $rest wird in wenigen Sekunden entfernt." -ForegroundColor Gray
    }
}

# ── 7. Tesseract ─────────────────────────────────────────────────────────────
if ($doTesseract) {
    Step "Deinstalliere Tesseract-OCR via winget…"
    winget uninstall --id UB-Mannheim.TesseractOCR --silent 2>$null
    Write-Host "  Tesseract-OCR deinstalliert." -ForegroundColor Green
}

# ── 8. Zusammenfassung ───────────────────────────────────────────────────────
Write-Host ""
Write-Host "Deinstallation abgeschlossen." -ForegroundColor Green
Write-Host ""
Write-Host "  Erhalten geblieben ist der Datenordner:" -ForegroundColor Yellow
Write-Host "    $Daten" -ForegroundColor Yellow
Write-Host ""
Write-Host "    finanzen.db      Datenbank"
Write-Host "    belege\          Belegfotos"
Write-Host "    kontoauszuege\   archivierte Kontoauszuege"
Write-Host "    backups\         Sicherungen, auch die von Updates"
Write-Host "    config\          Port, HTTPS, Backup-Ziel"
Write-Host "    logs\            Protokolle"
Write-Host ""
Write-Host "  Eine Neuinstallation nimmt diesen Ordner wieder auf." -ForegroundColor Gray
Write-Host "  Wer ihn wirklich loswerden will, loescht ihn von Hand." -ForegroundColor Gray
Write-Host ""
