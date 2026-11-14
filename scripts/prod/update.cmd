@echo off
rem Update per Doppelklick - der Weg ohne Administrator-Konsole.
rem
rem Eine .cmd und keine .exe: Stapelverarbeitungsdateien unterliegen weder der
rem ExecutionPolicy noch einer Signaturpruefung, duerfen PowerShell also mit
rem -ExecutionPolicy Bypass aufrufen. Eine unsignierte .exe loeste dasselbe
rem Problem nicht, sie handelte sich nur zusaetzlich SmartScreen ein.
rem
rem Drei Aufrufarten:
rem   update.cmd                  aus einem entpackten Paket: dieser Ordner
rem                               IST die Quelle (-Ordner), kein zweites
rem                               Entpacken von rund 80 MB.
rem   update.cmd /aus-updates     vom erzeugten Starter im Programmordner:
rem                               nimmt die neueste ZIP aus <Daten>\updates.
rem   update.cmd <pfad.zip>       ein mitgegebener Pfad gewinnt immer, auch
rem                               per Drag und Drop auf diese Datei.
rem
rem Siehe docs/betrieb.md, Abschnitt "Updates einspielen".
setlocal

set "PAKETSTAMM=%~dp0..\.."
set "SKRIPT=%~dp0update.ps1"
set "ARGS=%*"

rem -- Adminrechte ---------------------------------------------------------
rem Die .cmd erhoeht sich selbst, statt das update.ps1 das tun zu lassen.
rem Sonst gaebe es zwei Fenster: ein wartendes ohne Ausgabe und ein erhoehtes,
rem das sich am Ende sofort schliesst - das pause unten stuende im falschen.
net session >nul 2>&1
if not errorlevel 1 goto :alsAdmin

echo.
echo   Haushaltsfinanzen - Update
echo   Fordere Administratorrechte an...
if defined ARGS goto :erhoeheMitArgs

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $p = Start-Process -Verb RunAs -FilePath '%~f0' -WorkingDirectory '%~dp0' -Wait -PassThru; exit $p.ExitCode } catch { Write-Host '  Abgebrochen - ohne Administratorrechte laesst sich nicht aktualisieren.' -ForegroundColor Yellow; exit 1 }"
exit /b %ERRORLEVEL%

:erhoeheMitArgs
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $p = Start-Process -Verb RunAs -FilePath '%~f0' -WorkingDirectory '%~dp0' -ArgumentList '%ARGS%' -Wait -PassThru; exit $p.ExitCode } catch { Write-Host '  Abgebrochen - ohne Administratorrechte laesst sich nicht aktualisieren.' -ForegroundColor Yellow; exit 1 }"
exit /b %ERRORLEVEL%

:alsAdmin
set "PS=powershell"
where pwsh >nul 2>&1 && set "PS=pwsh"

if not exist "%SKRIPT%" (
  echo.
  echo   FEHLER: update.ps1 fehlt neben dieser Datei:
  echo     %SKRIPT%
  echo.
  pause
  exit /b 1
)

rem -- Quelle bestimmen ----------------------------------------------------
rem Ein mitgegebener Pfad gewinnt vor dem Modus-Schalter: wer eine ZIP vom
rem USB-Stick auflegt, meint genau diese.
set "FLAG=%~1"
set "ZIP=%~1"
if /i "%FLAG%"=="/aus-updates" set "ZIP=%~2"

if defined ZIP goto :ausZip
if /i "%FLAG%"=="/aus-updates" goto :ausUpdates

rem -- Entpacktes Paket ----------------------------------------------------
rem Windows markiert Dateien aus einem heruntergeladenen ZIP (Mark-of-the-Web).
rem -ExecutionPolicy Bypass deckt das aufgerufene Skript ab, nicht aber das von
rem ihm nachgeladene pfade.ps1 - deshalb hier entsperren, wie in setup.cmd.
echo.
echo   Entsperre Skriptdateien (Mark-of-the-Web)...
%PS% -NoProfile -ExecutionPolicy Bypass -Command "Get-ChildItem -LiteralPath '%PAKETSTAMM%' -Recurse -Include *.ps1,*.psm1,*.cmd -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"
%PS% -NoProfile -ExecutionPolicy Bypass -File "%SKRIPT%" -Ordner "%PAKETSTAMM%"
goto :fertig

:ausZip
%PS% -NoProfile -ExecutionPolicy Bypass -File "%SKRIPT%" -Paket "%ZIP%"
goto :fertig

:ausUpdates
%PS% -NoProfile -ExecutionPolicy Bypass -File "%SKRIPT%" -AusUpdates
goto :fertig

:fertig
set RC=%ERRORLEVEL%
echo.
if not "%RC%"=="0" (
  echo   Update mit Fehler beendet ^(Code %RC%^).
)
pause
exit /b %RC%
