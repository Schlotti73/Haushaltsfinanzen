"""Kontotyp 'kredit' (Ratenkredit) + laufzeit_monate

Erweitert den CHECK-Constraint auf konten.typ um 'kredit' und ergaenzt das Feld
`laufzeit_monate`. Ein Ratenkredit rechnet mit derselben Annuitaet wie ein
Darlehen; statt der Anfangstilgung gibt hier die Laufzeit die Monatsrate vor.

SQLite kann einen CHECK-Constraint weder aendern noch loeschen, daher wird die
Tabelle nach dem offiziellen SQLite-Rezept ("Making Other Kinds Of Table Schema
Changes") neu aufgebaut. Bewusst rohes SQL statt batch_alter_table: der CHECK
ist in der DB unbenannt und wird von der Reflection nicht zuverlaessig
uebernommen, hier ist die neue DDL explizit kontrolliert.

Zwei Punkte, die den Rebuild ungefaehrlich machen:
  * Reihenfolge DROP vor RENAME - die sechs Tabellen mit FK auf konten
    verweisen auf den Namen "konten", der erst am Ende wieder vergeben wird,
    sodass SQLite keine Fremdschluessel-Klauseln umschreibt.
  * foreign_keys muss AUS sein, sonst wuerde DROP TABLE die Buchungen per
    ON DELETE CASCADE mitloeschen. Alembic nutzt eine eigene Engine ohne den
    PRAGMA-Listener aus app/database.py; der Guard unten stellt das sicher.

Die tote Spalte `zinsbindung_bis` (in der DB vorhanden, im Modell nicht mehr)
wird absichtlich mitgenommen, damit diese Migration nur den CHECK aendert.

Revision ID: q8f9a0b1c2d3
Revises: p7e8f9a0b1c2
Create Date: 2026-07-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = "q8f9a0b1c2d3"
down_revision: Union[str, None] = "p7e8f9a0b1c2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Spalten der Alt-Tabelle, in genau dieser Reihenfolge uebernommen.
# laufzeit_monate steht bewusst NICHT hier: die Spalte existiert immer nur auf
# einer der beiden Seiten und bleibt beim Upgrade schlicht NULL.
_BESTAND = """
    id, name, typ, bank, iban, bic, startsaldo, startdatum, aktiv, sortierung,
    darlehen_betrag, zinssatz, rate, tilgung_start, zinsbindung_bis,
    effektiver_zinssatz, tilgungssatz, vollauszahlung_datum, zinsbindung_jahre
"""


def _pruefe_fk_aus() -> None:
    (fk_an,) = op.get_bind().exec_driver_sql("PRAGMA foreign_keys").fetchone()
    if fk_an:
        raise RuntimeError(
            "PRAGMA foreign_keys ist AN - der Rebuild von 'konten' wuerde per "
            "ON DELETE CASCADE alle Buchungen loeschen. Migration abgebrochen."
        )


def _rebuild(typen: str, mit_laufzeit: bool) -> None:
    """Baut `konten` mit der gegebenen Typ-Liste neu auf."""
    _pruefe_fk_aus()
    laufzeit_spalte = ",\n            laufzeit_monate INTEGER" if mit_laufzeit else ""

    op.execute(f"""
        CREATE TABLE konten_neu (
            id          INTEGER PRIMARY KEY,
            name        TEXT    NOT NULL UNIQUE,
            typ         TEXT    NOT NULL CHECK (typ IN ({typen})),
            bank        TEXT,
            iban        TEXT,
            bic         TEXT,
            startsaldo  REAL    NOT NULL DEFAULT 0,
            startdatum  TEXT,
            aktiv       INTEGER NOT NULL DEFAULT 1,
            sortierung  INTEGER NOT NULL DEFAULT 0,
            darlehen_betrag FLOAT,
            zinssatz FLOAT,
            rate FLOAT,
            tilgung_start VARCHAR,
            zinsbindung_bis VARCHAR,
            effektiver_zinssatz FLOAT,
            tilgungssatz FLOAT,
            vollauszahlung_datum VARCHAR,
            zinsbindung_jahre INTEGER{laufzeit_spalte}
        )
    """)
    op.execute(f"INSERT INTO konten_neu ({_BESTAND}) SELECT {_BESTAND} FROM konten")
    op.execute("DROP TABLE konten")
    op.execute("ALTER TABLE konten_neu RENAME TO konten")


def upgrade() -> None:
    _rebuild("'giro', 'spar', 'darlehen', 'kredit', 'depot'", mit_laufzeit=True)


def downgrade() -> None:
    # Kreditkonten wuerden den alten CHECK verletzen -> vorher auf 'darlehen' heben.
    op.execute("UPDATE konten SET typ = 'darlehen' WHERE typ = 'kredit'")
    _rebuild("'giro', 'spar', 'darlehen', 'depot'", mit_laufzeit=False)
