"""Der Ausloeser fuer das naechtliche Backup im Container.

Auf Windows macht das die Aufgabenplanung (scripts/prod/register_backup_task.ps1).
Im Container uebernimmt es ein zweiter Container aus demselben Image: so bleibt
jeder Container einprozessig, die Backup-Ausgaben stehen getrennt in
`docker compose logs backup`, und - wichtiger - die Sicherung ist da, ohne dass
jemand am Host eine crontab pflegen muss. Das Backup ist kein Zubehoer: auf ihm
steht auch der Rollback-Weg (siehe docs/docker.md).

Massgeblich bleibt `config/backup.json`, also genau die Datei, die der Nutzer in
der Oberflaeche bearbeitet - `aktiviert`, `uhrzeit` und `behalten` wirken hier
unmittelbar. Deshalb wird sie bei jedem Durchlauf neu gelesen und nicht beim
Start zwischengespeichert: eine Aenderung in der Oberflaeche soll nicht erst
nach einem Neustart des Containers gelten.

Das Backup selbst laeuft bewusst als eigener Prozess (scripts/backup.py). Es
bestimmt die aktive Datenbank beim Import ueber app.config; liefe es im
Dauerprozess mit, wuerde ein Wechsel der aktiven Datenbank in der Oberflaeche
hier nie ankommen.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, datetime
from pathlib import Path

_PROGRAMM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROGRAMM / "backend"))

from app.pfade import daten_dir, einstellungen_dir  # noqa: E402

_CFG = einstellungen_dir() / "backup.json"
_BACKUP_PY = _PROGRAMM / "scripts" / "backup.py"
_TAKT_SEKUNDEN = 60
_WARTEN_NACH_FEHLER = 15 * 60


def _melde(text: str) -> None:
    print(f"[backup] {text}", flush=True)


def _cfg() -> dict:
    vorgabe = {"aktiviert": True, "uhrzeit": "02:00"}
    try:
        return {**vorgabe, **json.loads(_CFG.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError):
        return vorgabe


def _ziel_ordner(cfg: dict) -> Path:
    ziel = str(cfg.get("ziel_ordner", "")).strip()
    return Path(ziel) if ziel else daten_dir() / "backups"


def _schon_heute_gesichert(cfg: dict, heute: date) -> bool:
    """Liegt fuer heute schon eine Sicherung im Zielordner?

    Bewusst am Dateibestand abgelesen und nicht an einer Variablen im Prozess:
    ein Containerneustart - durch `up -d`, durch `restart: unless-stopped`
    nach einem Neustart des Hosts - wuerde die Variable zuruecksetzen, und der
    Waechter legte jedes Mal eine weitere Sicherung desselben Tages an. Die
    Dateinamen sind "YYYY-MM-DD_HH-MM.zip" (siehe scripts/backup.py), das
    Datum steht also vorn.
    """
    try:
        return any(p.name.startswith(f"{heute:%Y-%m-%d}_")
                   for p in _ziel_ordner(cfg).glob("*.zip"))
    except OSError:
        return False


def _faellig(uhrzeit: str, jetzt: datetime) -> bool:
    """Ist die eingestellte Uhrzeit heute erreicht?

    Kein Schlafen bis zur Zielzeit, sondern ein Vergleich je Takt: so wirkt eine
    in der Oberflaeche geaenderte Uhrzeit sofort, und ein Container, der ueber
    den Zeitpunkt hinweg gestanden hat (Host war aus), holt das Backup beim
    naechsten Start nach, statt einen Tag zu ueberspringen.
    """
    try:
        stunde, minute = (int(t) for t in uhrzeit.split(":"))
    except ValueError:
        stunde, minute = 2, 0
    return (jetzt.hour, jetzt.minute) >= (stunde, minute)


def main() -> None:
    _melde(f"Waechter gestartet. Einstellungen: {_CFG}")
    naechster_versuch = 0.0

    while True:
        cfg = _cfg()
        jetzt = datetime.now()

        if (cfg.get("aktiviert", True)
                and time.monotonic() >= naechster_versuch
                and _faellig(str(cfg.get("uhrzeit", "02:00")), jetzt)
                and not _schon_heute_gesichert(cfg, jetzt.date())):
            _melde(f"Starte Sicherung ({jetzt:%Y-%m-%d %H:%M}).")
            ergebnis = subprocess.run(
                [sys.executable, str(_BACKUP_PY)],
                cwd=str(_PROGRAMM), capture_output=True, text=True,
            )
            for zeile in (ergebnis.stdout or "").splitlines():
                _melde(zeile)
            if ergebnis.returncode == 0:
                _melde("Sicherung fertig.")
            else:
                # Es wird erneut versucht - im Zielordner liegt ja nichts. Ein einmal
                # fehlgeschlagenes Backup soll nicht den ganzen Tag ausfallen
                # lassen, etwa weil das Ziel kurz nicht da war. Aber auch nicht
                # im Minutentakt: ein dauerhafter Fehler (Platte voll) wuerde
                # sonst bis Mitternacht dasselbe ins Log schreiben.
                naechster_versuch = time.monotonic() + _WARTEN_NACH_FEHLER
                _melde(f"FEHLGESCHLAGEN (Code {ergebnis.returncode}), "
                       f"neuer Versuch in {_WARTEN_NACH_FEHLER // 60} Minuten:")
                for zeile in (ergebnis.stderr or "").splitlines()[-10:]:
                    _melde(f"  {zeile}")

        time.sleep(_TAKT_SEKUNDEN)


if __name__ == "__main__":
    main()
