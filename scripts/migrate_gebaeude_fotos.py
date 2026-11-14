"""
migrate_gebaeude_fotos.py – Belege koennen zusaetzlich an einem Gebaeude haengen.
Idempotent: kann beliebig oft ausgefuehrt werden.

Die Tabelle wird neu aufgebaut, weil SQLite eine bestehende CHECK-Bedingung
nicht aendern kann: bisher "genau eines von buchung_id/eintrag_id", kuenftig
"genau eines von buchung_id/eintrag_id/gebaeude_id".

Aufruf (aus Projektwurzel):
    python scripts/migrate_gebaeude_fotos.py
    python scripts/migrate_gebaeude_fotos.py --db pfad/zu/finanzen.db
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "finanzen.db"


def green(s): return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"
def bold(s): return f"\033[1m{s}\033[0m"


NEUE_TABELLE = """
CREATE TABLE belege_neu (
    id              INTEGER PRIMARY KEY,
    buchung_id      INTEGER REFERENCES buchungen(id) ON DELETE CASCADE,
    eintrag_id      INTEGER REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
    gebaeude_id     INTEGER REFERENCES gebaeude(id) ON DELETE CASCADE,
    dateiname       TEXT    NOT NULL,
    dateipfad       TEXT    NOT NULL,
    hochgeladen_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
    hochgeladen_am  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((buchung_id IS NOT NULL) + (eintrag_id IS NOT NULL) + (gebaeude_id IS NOT NULL) = 1)
)
"""


def spaltennamen(conn: sqlite3.Connection, tabelle: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()}


def migrate(db_path: Path) -> None:
    print(bold(f"\nMigration Gebäude-Fotos -> {db_path}"))
    conn = sqlite3.connect(db_path)
    try:
        if "gebaeude_id" in spaltennamen(conn, "belege"):
            print(f"  {yellow('skip')} belege.gebaeude_id ist bereits vorhanden")
            print(bold("Fertig.\n"))
            return

        anzahl = conn.execute("SELECT count(*) FROM belege").fetchone()[0]
        # Fremdschluessel waehrend des Umbaus aus, sonst reisst das DROP die
        # kopierten Zeilen ueber ON DELETE CASCADE wieder mit.
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN")
        conn.execute(NEUE_TABELLE)
        conn.execute(
            "INSERT INTO belege_neu (id, buchung_id, eintrag_id, dateiname, dateipfad, "
            "hochgeladen_von, hochgeladen_am) "
            "SELECT id, buchung_id, eintrag_id, dateiname, dateipfad, "
            "hochgeladen_von, hochgeladen_am FROM belege"
        )
        conn.execute("DROP TABLE belege")
        conn.execute("ALTER TABLE belege_neu RENAME TO belege")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_belege_eintrag ON belege(eintrag_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_belege_gebaeude ON belege(gebaeude_id)")
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        print(f"  {green('ok  ')} belege umgebaut, {anzahl} Datensätze übernommen")
    finally:
        conn.close()

    print(bold("Fertig.\n"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migration Gebäude-Fotos")
    parser.add_argument("--db", type=Path, default=DB_DEFAULT)
    args = parser.parse_args()
    migrate(args.db)
