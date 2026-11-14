"""Was vor dem ersten Byte HTTP passieren muss: Saat, Schema, Sicherung.

Drei Faelle, und nur drei:

  1. Es gibt noch keine Datenbank. Dann legt dieses Skript sie an, saet einen
     minimalen Kategorienbaum und einen Administrator mit einem *zufaelligen*
     Passwort, das genau einmal im Log steht. Keine Konten: die mapping.json
     des Entwicklers gehoert nicht in fremde Installationen.

  2. Datenbank und Image passen zusammen (gleiche Alembic-Revision). Dann wird
     nichts angefasst - insbesondere wird keine Sicherung geschrieben, sonst
     laegen nach zehn Neustarts zehn gleiche Dateien im Backup-Ordner.

  3. Die Revisionen weichen ab. Dann erst eine Sicherung nach
     backups/vor-<version>-<zeit>.db, dann `upgrade head`. Das ist dieselbe
     Zusage wie bei Windows - "keine Migration ohne Sicherung", siehe
     docs/release-paket.md -, nur dass sie hier der Containerstart einloest
     statt update.ps1.

  Sonderfall zu 3: Steht die Datenbank auf einer Revision, die dieses Image
  nicht kennt, ist sie *neuer* als das Programm. Das ist der zurueckgerollte
  Tag auf einer bereits migrierten Datenbank. Migrieren waere hier falsch
  (alembic kaeme nicht einmal hin), Weiterlaufen auch - also sauberer Abbruch
  mit dem Hinweis, welche Sicherung dazugehoert.
"""

from __future__ import annotations

import os
import secrets
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# Der Programmordner wird aus dem eigenen Ort abgeleitet, nicht auf /app
# festgenagelt: so laesst sich dieses Skript auch auf dem Entwicklungsrechner
# gegen einen Wegwerf-Datenordner laufen lassen (FINANZ_DATEN_DIR setzen) -
# der Erststart ist sonst das einzige Stueck, das man nur im Container testen
# koennte, und genau er trifft jeden neuen Nutzer zuerst.
_PROGRAMM = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROGRAMM / "backend"))
# alembic.ini nennt "script_location = alembic" relativ zum Arbeitsverzeichnis.
# app.db_init setzt den Pfad zwar absolut, aber andere Einstiege (scripts/)
# verlassen sich auf das Verzeichnis - deshalb hier einheitlich.
os.chdir(_PROGRAMM / "backend")

from alembic.runtime.migration import MigrationContext  # noqa: E402
from alembic.script import ScriptDirectory  # noqa: E402
from sqlalchemy import inspect  # noqa: E402

from app.db_init import _config, init_db_schema  # noqa: E402
from app.pfade import daten_dir, einstellungen_dir, version as paket_version  # noqa: E402

# Ein Alphabet ohne 0/O und 1/l/I: das Passwort wird aus dem Log abgetippt.
_ALPHABET = "abcdefghijkmnopqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _melde(text: str) -> None:
    print(f"[start] {text}", flush=True)


def _neues_passwort(laenge: int = 16) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(laenge))


def _ist_leer(engine) -> bool:
    return "buchungen" not in set(inspect(engine).get_table_names())


def _revisionen(engine) -> tuple[set[str], set[str], list[str]]:
    """(Stand der Datenbank, Stand des Images, dem Image unbekannte Revisionen)."""
    skript = ScriptDirectory.from_config(_config(engine))
    kopf = set(skript.get_heads())

    if "alembic_version" not in set(inspect(engine).get_table_names()):
        return set(), kopf, []

    with engine.connect() as conn:
        vorhanden = set(MigrationContext.configure(conn).get_current_heads())

    unbekannt = []
    for rev in vorhanden:
        try:
            skript.get_revision(rev)
        except Exception:  # noqa: BLE001 - jede Stoerung heisst "kennt die Revision nicht"
            unbekannt.append(rev)
    return vorhanden, kopf, unbekannt


def _sichere(db_pfad: Path) -> Path:
    """Konsistente Kopie der Datenbank, auch bei offenem WAL.

    Nicht shutil.copy2: daneben liegen -wal und -shm, und eine Kopie der
    .db-Datei allein kann einen Stand ohne die zuletzt geschriebenen
    Transaktionen enthalten. Die Backup-API von SQLite schreibt eine in sich
    stimmige Einzeldatei.
    """
    ziel_ordner = daten_dir() / "backups"
    ziel_ordner.mkdir(parents=True, exist_ok=True)
    name = f"vor-{paket_version()}-{datetime.now():%Y-%m-%d_%H-%M}.db"
    ziel = ziel_ordner / name

    quelle = sqlite3.connect(str(db_pfad))
    try:
        sicherung = sqlite3.connect(str(ziel))
        try:
            quelle.backup(sicherung)
        finally:
            sicherung.close()
    finally:
        quelle.close()
    return ziel


def _erststart(engine, db_pfad: Path) -> None:
    from sqlalchemy.orm import sessionmaker

    from app.auth import hash_passwort
    from app.models import Benutzer
    from app.routers.datenbanken import _seed_minimal_kategorien

    _melde(f"Keine Datenbank unter {db_pfad} - lege sie an.")
    init_db_schema(engine)
    _seed_minimal_kategorien(engine)

    name = os.environ.get("FINANZ_ADMIN_BENUTZER", "").strip() or "Admin"
    passwort = os.environ.get("FINANZ_ADMIN_PASSWORT", "").strip()
    selbst_erzeugt = not passwort
    if selbst_erzeugt:
        passwort = _neues_passwort()

    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(Benutzer(name=name, passwort_hash=hash_passwort(passwort),
                        rolle="admin", aktiv=True))
        db.commit()
    finally:
        db.close()

    if selbst_erzeugt:
        # Genau einmal, beim Anlegen. Danach steht es nirgends mehr - weder in
        # einer Datei noch in der Datenbank, dort liegt nur der bcrypt-Hash.
        _melde("")
        # Bewusst nur ASCII: die Meldung landet auch dann richtig im Log,
        # wenn jemand `migrate` auf einer Windows-Konsole mit cp1252
        # ausfuehrt. Rahmenzeichen braechen dort mit UnicodeEncodeError ab -
        # ausgerechnet an der Stelle, an der das einzige Passwort steht.
        # Die Breite rechnet sich aus dem Inhalt: ein von Hand gezaehlter
        # Rahmen verrutscht beim ersten laengeren Benutzernamen.
        zeilen = [
            f"Benutzer:  {name}",
            f"Passwort:  {passwort}",
            "",
            "Dieses Passwort wird nie wieder angezeigt.",
            "Bitte nach der ersten Anmeldung aendern.",
        ]
        breite = max(len(z) for z in zeilen) + 4
        rahmen = "  +" + "-" * breite + "+"
        _melde("")
        _melde(rahmen)
        _melde("  |" + "  Erster Start".ljust(breite) + "|")
        _melde(rahmen)
        for zeile in zeilen:
            _melde("  |" + f"  {zeile}".ljust(breite) + "|")
        _melde(rahmen)
        _melde("")
    else:
        _melde(f"Administrator '{name}' aus FINANZ_ADMIN_PASSWORT angelegt.")


def _migriere_bei_bedarf(engine, db_pfad: Path) -> None:
    vorhanden, kopf, unbekannt = _revisionen(engine)

    if unbekannt:
        _melde("ABBRUCH: Die Datenbank ist neuer als dieses Image.")
        _melde(f"  Datenbank steht auf: {', '.join(sorted(unbekannt))}")
        _melde(f"  Image kennt zuletzt: {', '.join(sorted(kopf))}")
        _melde("  Vermutlich wurde auf ein aelteres Image zurueckgewechselt,")
        _melde("  die Datenbank aber nicht. Beides gehoert zusammen:")
        _melde("  entweder wieder das neuere Image starten, oder die Sicherung")
        _melde("  'vor-<version>-*.db' aus daten/backups zuruecklegen.")
        _melde("  Siehe docs/docker.md, Abschnitt Rollback.")
        sys.exit(1)

    if vorhanden == kopf:
        _melde(f"Schema aktuell ({', '.join(sorted(kopf))}) - nichts zu tun.")
        return

    _melde(f"Schema weicht ab: Datenbank {', '.join(sorted(vorhanden)) or '(ungestempelt)'}, "
           f"Image {', '.join(sorted(kopf))}.")
    sicherung = _sichere(db_pfad)
    _melde(f"Sicherung angelegt: {sicherung}")
    init_db_schema(engine)
    _melde("Migration abgeschlossen.")


def main() -> None:
    # Erst hier importieren: app.config legt beim Import die Ablage-Ordner an
    # und liest die Registry - das soll passieren, nachdem /daten gemountet ist.
    from app.config import settings
    from app.database import engine

    db_pfad = Path(settings.db_path)
    db_pfad.parent.mkdir(parents=True, exist_ok=True)
    # Die Ablagen legt app.config beim Import an. Diese beiden nicht: der
    # Einstellungsordner entstuende sonst erst, wenn die Anwendung zum ersten
    # Mal etwas hineinschreibt - wer vorher eine eigene server.json hinterlegen
    # will, faende im Datenordner gar kein config/ vor. Und der Backup-Ordner
    # soll sichtbar sein, auch bevor die erste Sicherung darin liegt.
    einstellungen_dir().mkdir(parents=True, exist_ok=True)
    (daten_dir() / "backups").mkdir(parents=True, exist_ok=True)

    _melde(f"Version {paket_version()}, Datenordner {daten_dir()}, Datenbank {db_pfad}")

    if _ist_leer(engine):
        _erststart(engine, db_pfad)
    else:
        _migriere_bei_bedarf(engine, db_pfad)

    engine.dispose()


if __name__ == "__main__":
    main()
