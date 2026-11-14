"""Schema-Erzeugung/-Migration für eine beliebige SQLite-Engine.

Extrahiert aus main.py, damit dieselbe Logik auch beim Anlegen einer
neuen Datenbank (Mehrfach-DB-Verwaltung) verwendet werden kann.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from app.database import Base

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
# Revision, ab der inkrementelle ADD-COLUMN-Migrationen beginnen.
# Bestehende DBs ohne alembic_version-Tabelle (via create_all erstellt)
# werden auf diesen Stand gestempelt, bevor upgrade head läuft.
_STAMP_REVISION = "0c7cbefa440b"


def _config(engine: Engine) -> Config:
    alembic_cfg = Config(str(_ALEMBIC_INI))
    # alembic.ini nennt bewusst keine Datenbank mehr (env.py fällt auf
    # app.config zurück). Hier wird die URL explizit auf die übergebene Engine
    # gesetzt, damit stamp()/upgrade() nicht gegen eine andere Datei laufen –
    # wichtig bei der Mehrfach-Datenbank-Verwaltung.
    alembic_cfg.set_main_option("sqlalchemy.url", str(engine.url))
    # alembic.ini hat "script_location = alembic" relativ zum ARBEITSVERZEICHNIS,
    # nicht zur ini-Datei. Der Dienst laeuft mit cwd=backend und findet den
    # Ordner damit zufaellig; jeder Aufruf aus einem anderen Verzeichnis
    # scheitert mit "Path doesn't exist". Deshalb hier absolut setzen.
    alembic_cfg.set_main_option("script_location", str(_ALEMBIC_INI.parent / "alembic"))
    return alembic_cfg


class SchemaAbweichung(RuntimeError):
    """Schema und mitgelieferte Migrationen passen nicht zusammen."""


def _meldung(*zeilen: str) -> str:
    return "\n".join(zeilen)


def pruefe_schema(engine: Engine) -> str:
    """Prüft, ohne zu migrieren. Gibt die Revision der Datenbank zurück.

    Das ist der Weg für den Produktionsdienst: migrieren darf nur das
    Update-Skript, das vorher ein Pflicht-Backup anlegt (siehe
    docs/release-paket.md). Würde der Dienst selbst migrieren, wäre jeder
    Neustart ein möglicher Schema-Änderer ohne Sicherungskopie – auch der
    Neustart nach dem Zurückspielen einer alten Datenbank.

    Wirft SchemaAbweichung mit einer Meldung, die sagt, was zu tun ist.
    """
    skript = ScriptDirectory.from_config(_config(engine))
    kopf = set(skript.get_heads())

    insp = inspect(engine)
    tabellen = set(insp.get_table_names())
    if "buchungen" not in tabellen:
        raise SchemaAbweichung(_meldung(
            "Die Datenbank ist leer oder fehlt. Sie wird bei der Installation "
            "angelegt, nicht beim Start des Dienstes.",
            "  Abhilfe: scripts/prod/seed_admin.py ausfuehren.",
        ))
    if "alembic_version" not in tabellen:
        raise SchemaAbweichung(_meldung(
            "Die Datenbank hat keine alembic_version-Tabelle und muss einmalig "
            "gestempelt und migriert werden.",
            "  Abhilfe: scripts/prod/seed_admin.py ausfuehren.",
        ))

    with engine.connect() as conn:
        vorhanden = set(MigrationContext.configure(conn).get_current_heads())

    if vorhanden == kopf:
        return ", ".join(sorted(vorhanden))

    # Revisionen, die diese Programmversion gar nicht kennt: typischerweise ein
    # zurueckgerollter Programmordner auf einer bereits migrierten Datenbank.
    unbekannt = []
    for rev in vorhanden:
        try:
            skript.get_revision(rev)
        except Exception:
            unbekannt.append(rev)

    if unbekannt:
        raise SchemaAbweichung(_meldung(
            "Die Datenbank steht auf einer Revision, die diese Programmversion "
            f"nicht kennt: {', '.join(sorted(unbekannt))}.",
            "  Die Datenbank ist neuer als das Programm – vermutlich wurde der "
            "Programmordner zurueckgerollt, die Datenbank aber nicht.",
            "  Abhilfe: scripts/prod/rollback.ps1 (legt Programm UND Datenbank "
            "zurueck) oder wieder auf die neuere Version wechseln.",
        ))

    raise SchemaAbweichung(_meldung(
        "Ausstehende Migrationen: Datenbank steht auf "
        f"{', '.join(sorted(vorhanden)) or '(leer)'}, erwartet wird "
        f"{', '.join(sorted(kopf))}.",
        "  Der Dienst migriert in der Produktion nicht selbst.",
        "  Abhilfe: scripts/prod/update.ps1 ausfuehren (legt vorher ein "
        "Backup an).",
    ))


def init_db_schema(engine: Engine) -> None:
    alembic_cfg = _config(engine)

    insp = inspect(engine)
    tables = set(insp.get_table_names())

    if "buchungen" not in tables:
        # Neue/leere DB: Alle Tabellen aus den Models anlegen, dann als Head stempeln
        Base.metadata.create_all(engine)
        command.stamp(alembic_cfg, "head")
    elif "alembic_version" not in tables:
        # Alte DB (via create_all ohne Alembic): auf Basis-Revision stempeln,
        # dann fehlende Migrationen (ADD COLUMN etc.) anwenden
        command.stamp(alembic_cfg, _STAMP_REVISION)
        command.upgrade(alembic_cfg, "head")
    else:
        # Bekannte DB: ausstehende Migrationen anwenden
        command.upgrade(alembic_cfg, "head")
