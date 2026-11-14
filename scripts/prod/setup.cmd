@echo off
rem Startpunkt der Installation aus einem entpackten Release-Paket.
rem Doppelklick genuegt; Adminrechte holt sich das PowerShell-Skript selbst.
rem Siehe docs\release-paket.md
setlocal

echo.
echo   Haushaltsfinanzen - Setup
echo.

rem Windows markiert Dateien aus einem heruntergeladenen ZIP (Mark-of-the-Web).
rem PowerShell verweigert sie dann, auch bei -ExecutionPolicy Bypass fuer
rem nachgeladene Skripte. Deshalb hier einmal entsperren - das ist der
rem haeufigste Stolperstein bei ZIP-ausgelieferten PowerShell-Skripten.
set "PS=powershell"
where pwsh >nul 2>&1 && set "PS=pwsh"

echo   Entsperre Skriptdateien (Mark-of-the-Web)...
%PS% -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-ChildItem -LiteralPath '%~dp0..\..' -Recurse -Include *.ps1,*.psm1,*.cmd -ErrorAction SilentlyContinue | Unblock-File -ErrorAction SilentlyContinue"

if errorlevel 1 (
  echo.
  echo   FEHLER: Die Skriptdateien konnten nicht entsperrt werden.
  echo   Abhilfe: Rechtsklick auf die ZIP-Datei, Eigenschaften, "Zulassen"
  echo            ankreuzen, erneut entpacken und setup.cmd nochmal starten.
  echo.
  pause
  exit /b 1
)

%PS% -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_service.ps1" %*
set RC=%ERRORLEVEL%

echo.
if not "%RC%"=="0" (
  echo   Setup mit Fehler beendet ^(Code %RC%^).
) else (
  echo   Setup beendet.
)
echo.
pause
exit /b %RC%
