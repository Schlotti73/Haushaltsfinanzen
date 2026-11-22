# Beendet uvicorn (Port 8000) und Vite (Port 5173)
#
# Die Schleifenvariable heisst $procId und nicht $pid: $pid ist in PowerShell
# eine schreibgeschuetzte automatische Variable (die PID der eigenen Sitzung).
# Ein "foreach ($pid in ...)" laesst das Skript mit "Die Variable PID kann
# nicht ueberschrieben werden" abbrechen - und zwar bevor ein einziger Prozess
# beendet wurde, was wie ein stehengebliebener Server aussieht, der sich nicht
# abschiessen laesst. Gleiche Benennung wie in copy_prod_db.ps1.

$ports = @(8000, 5173)

function Get-ListenerPid([int]$port) {
    <#
      Nur echte Listener auf diesem Port.

      Das frueher benutzte "netstat -ano | Select-String ':$port\s'" trifft die
      Portnummer in jeder Spalte, also auch in der Gegenstelle: ein beliebiger
      Client, der gerade nach 8000 verbunden ist, waere mit beendet worden.
      Darum Get-NetTCPConnection -State Listen, und im Rueckfall auf netstat
      ausdruecklich nur die Spalte der lokalen Adresse.
    #>
    if (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue) {
        return @(
            Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue |
                Select-Object -ExpandProperty OwningProcess | Sort-Object -Unique
        )
    }
    return @(
        netstat -ano | ForEach-Object {
            $felder = $_.Trim() -split '\s+'
            if ($felder.Count -ge 5 -and $felder[0] -eq 'TCP' -and $felder[1].EndsWith(":$port")) {
                $felder[-1]
            }
        } | Sort-Object -Unique
    )
}

$offen = 0
foreach ($port in $ports) {
    $procIds = @(Get-ListenerPid $port | Where-Object {
        $_ -match '^\d+$' -and $_ -ne '0' -and [int]$_ -ne $PID
    })
    if ($procIds.Count -eq 0) {
        Write-Host "Port $port : kein Server." -ForegroundColor DarkGray
        continue
    }
    foreach ($procId in $procIds) {
        $name = (Get-Process -Id $procId -ErrorAction SilentlyContinue).ProcessName
        if (-not $name) { $name = "unbekannt" }
        try {
            Stop-Process -Id $procId -Force -ErrorAction Stop
            Write-Host "Port $port ($name, PID $procId) beendet." -ForegroundColor Green
        } catch {
            $offen++
            Write-Host "Port $port ($name, PID $procId) nicht beendet: $($_.Exception.Message)" -ForegroundColor Yellow
        }
    }
}

if ($offen -gt 0) {
    Write-Host ""
    Write-Host "$offen Prozess(e) laufen weiter. Ein Fenster mit Administratorrechten" -ForegroundColor Yellow
    Write-Host "kann meist mehr; gehoert der Prozess einem anderen Benutzerkonto," -ForegroundColor Yellow
    Write-Host "muss er dort beendet werden." -ForegroundColor Yellow
    exit 1
}

Write-Host "Fertig." -ForegroundColor Cyan
