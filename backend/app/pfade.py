"""Zentrale Auflösung der Ablage-Orte: Programm, Daten, Einstellungen, Vorlagen.

Hintergrund: In der Produktion liegen Programm und Daten in getrennten Ordnern,
damit ein Update den Programmordner restlos ersetzen kann, ohne Nutzerdaten
anzufassen (siehe docs/release-paket.md). In der Entwicklung liegt beides
weiterhin im Projektstamm — ohne gesetzte Umgebungsvariablen verhält sich dieses
Modul exakt wie die früheren, fest verdrahteten Pfade.

Vier Begriffe, die nicht verwechselt werden dürfen:

  programm_dir()      Der Code selbst (Projektstamm bzw. Versionsordner).
                      Read-only im Betrieb, wird beim Update ersetzt.
  daten_dir()         Datenbank, Belege, Logs, Backups. Wird nie ersetzt.
  einstellungen_dir() Maschinenspezifisch und von der App beschreibbar:
                      server.json, datenbanken.json, backup.json.
                      Liegt unter daten_dir(), wird nie ersetzt.
  vorlagen_dir()      Saat-Daten aus dem Repo, nur gelesen:
                      kategorien.json, kategorien_minimal.json, mapping.json.
                      Liegt beim Programm, wird mit jedem Update aktualisiert.

Faustregel für neue Konfigurationsdateien: Schreibt die App hinein, ist es eine
Einstellung. Liest sie nur daraus und steht die Datei im Repo, ist es eine
Vorlage.

Bewusst ohne Abhängigkeit von app.config oder sonstigen App-Modulen: sowohl
app.db_registry (das von app.config importiert wird) als auch die Skripte unter
scripts/ müssen dieses Modul gefahrlos importieren können.
"""

from __future__ import annotations

import os
from pathlib import Path

# backend/app/pfade.py -> parents[2] ist der Projektstamm bzw. der Versionsordner
_PROGRAMM = Path(__file__).resolve().parents[2]


def _aus_umgebung(name: str) -> Path | None:
    wert = os.environ.get(name, "").strip()
    return Path(wert) if wert else None


def programm_dir() -> Path:
    """Ordner des Anwendungscodes. Im Betrieb read-only."""
    return _PROGRAMM


def daten_dir() -> Path:
    """Ordner für Datenbank, Belege, Logs und Backups.

    Prod: FINANZ_DATEN_DIR, gesetzt von der Dienst-Konfiguration.
    Dev:  der Projektstamm, wie bisher.
    """
    return _aus_umgebung("FINANZ_DATEN_DIR") or _PROGRAMM


def einstellungen_dir() -> Path:
    """Ordner für server.json, datenbanken.json, backup.json.

    Prod: FINANZ_CONFIG_DIR (liegt unter dem Datenordner).
    Dev:  <Projektstamm>/config, wie bisher.

    Fehlt FINANZ_CONFIG_DIR, ist aber FINANZ_DATEN_DIR gesetzt, gilt
    <Datenordner>/config – so genügt in der Dienst-Konfiguration eine Variable.
    """
    gesetzt = _aus_umgebung("FINANZ_CONFIG_DIR")
    if gesetzt:
        return gesetzt
    return daten_dir() / "config"


def vorlagen_dir() -> Path:
    """Ordner der mitgelieferten Saat-Daten (nur lesend).

    Liegt beim Programm, nicht bei den Daten: Verbesserungen am Kategorienbaum
    oder am Mapping sollen mit einem Update auf dem Prod-PC ankommen. Lägen sie
    beim Datenordner, bliebe dort auf Dauer die Fassung der Erstinstallation.

    Rückfall auf <Programm>/config für Installationen aus der Zeit vor der
    Aufteilung, in denen Vorlagen und Einstellungen noch denselben Ordner
    geteilt haben.
    """
    gesetzt = _aus_umgebung("FINANZ_VORLAGEN_DIR")
    if gesetzt:
        return gesetzt
    neu = _PROGRAMM / "config-vorlagen"
    if neu.is_dir():
        return neu
    return _PROGRAMM / "config"


def version() -> str:
    """Version aus der VERSION-Datei des Pakets, 'dev' wenn sie fehlt.

    Die Datei schreibt der Paketbau aus `git describe --tags`; im
    Entwicklungsbetrieb existiert sie nicht.
    """
    datei = _PROGRAMM / "VERSION"
    try:
        # utf-8-sig, nicht utf-8: die VERSION-Datei entsteht unter Windows und
        # kann ein BOM tragen. str.strip() entfernt U+FEFF nicht, die Version
        # hiesse dann "﻿v1.2.3".
        wert = datei.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return "dev"
    return wert or "dev"


def auto_migration_erlaubt() -> bool:
    """Darf die Anwendung beim Start selbst migrieren?

    Dev: ja (Vorgabe) – bequem, weil jeder Start das Schema nachzieht.
    Prod: nein. Die Dienst-Konfiguration setzt FINANZ_AUTO_MIGRATE=0, dann
    prüft die Anwendung nur und verweigert bei Abweichung den Start.

    Grund: Migrationen gehören ins Update-Skript, das vorher ein Pflicht-Backup
    anlegt. Dürfte der Dienst selbst migrieren, würde jeder Neustart zu einem
    möglichen Schema-Änderer ohne Sicherungskopie – auch der Neustart nach dem
    Zurückspielen einer alten Datenbank.
    """
    wert = os.environ.get("FINANZ_AUTO_MIGRATE", "").strip().lower()
    if not wert:
        return True
    return wert not in {"0", "false", "nein", "no", "off"}


def betriebsart() -> str:
    """Wie die Anwendung betrieben wird: "docker" oder "standard".

    Das Container-Image setzt FINANZ_BETRIEBSART=docker, sonst ist die Variable
    nicht gesetzt. Gebraucht wird die Unterscheidung an drei Stellen, an denen
    sonst etwas Sichtbares ins Leere liefe oder - schlimmer - still das Falsche
    täte:

      * Der Update-Bereich nennt im Container `docker compose pull`, nicht
        update.ps1, und lädt kein Windows-ZIP mehr herunter.
      * Die Backup-Einstellungen blenden den Namen der Windows-Aufgabe aus; der
        Zielordner ist ein Pfad *im Container*.
      * Die Vorgabe der vertrauenswürdigen Netze lässt 172.16.0.0/12 weg - den
        Bereich, in dem Docker seine Container-Netze anlegt. Sonst gälte ein
        Reverse-Proxy im Nachbarcontainer als Heimnetz, ohne dass es jemand
        entschieden hätte. Siehe app.server_config.

    Bewusst eine Zeichenkette und kein `ist_docker()`: kommt später eine
    weitere Betriebsart dazu (etwa ein Linux-Dienst ohne Container), muss keine
    Aufrufstelle umgeschrieben werden.
    """
    wert = os.environ.get("FINANZ_BETRIEBSART", "").strip().lower()
    return wert if wert in {"docker"} else "standard"
