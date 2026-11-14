"""
migrate_projekte_plan.py – Additive DB-Migration für die Projekte-Erweiterung
(geplante Ausgaben / Plan vs. Ist, Darlehenskonto-Verknüpfung).
Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_projekte_plan.py
    python scripts/migrate_projekte_plan.py --db pfad/zu/finanzen.db
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


MIGRATIONS: list[tuple[str, str]] = [
    ("geplante_ausgabe_tabelle", """
        CREATE TABLE IF NOT EXISTS geplante_ausgabe (
            id           INTEGER PRIMARY KEY,
            projekt_id   INTEGER NOT NULL REFERENCES projekte(id) ON DELETE CASCADE,
            bezeichnung  VARCHAR NOT NULL,
            betrag       FLOAT   NOT NULL,
            notiz        TEXT,
            kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
            sortierung   INTEGER NOT NULL DEFAULT 0,
            erledigt     BOOLEAN NOT NULL DEFAULT 0
        )
    """),
    ("idx_geplante_ausgabe_projekt", """
        CREATE INDEX IF NOT EXISTS idx_geplante_ausgabe_projekt ON geplante_ausgabe(projekt_id)
    """),
    ("buchungen_geplante_ausgabe_id", """
        ALTER TABLE buchungen ADD COLUMN geplante_ausgabe_id INTEGER
            REFERENCES geplante_ausgabe(id) ON DELETE SET NULL
    """),
    ("idx_buchungen_geplante_ausgabe", """
        CREATE INDEX IF NOT EXISTS idx_buchungen_geplante_ausgabe ON buchungen(geplante_ausgabe_id)
    """),
    ("projekte_darlehen_konto_id", """
        ALTER TABLE projekte ADD COLUMN darlehen_konto_id INTEGER
            REFERENCES konten(id) ON DELETE SET NULL
    """),
]


def spaltennamen(conn: sqlite3.Connection, tabelle: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({tabelle})")
    return {row[1] for row in cur.fetchall()}


def tabelle_existiert(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def index_existiert(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,)
    )
    return cur.fetchone() is not None


def ist_erledigt(conn: sqlite3.Connection, key: str, sql: str) -> bool:
    sql_stripped = sql.strip().upper()
    if sql_stripped.startswith("CREATE TABLE"):
        tbl = key.replace("_tabelle", "")
        return tabelle_existiert(conn, tbl)
    if sql_stripped.startswith("ALTER TABLE") and "ADD COLUMN" in sql_stripped:
        parts = sql.split()
        try:
            tbl = parts[parts.index("TABLE") + 1]
            col = parts[parts.index("COLUMN") + 1]
            return col in spaltennamen(conn, tbl)
        except (ValueError, IndexError):
            return False
    if sql_stripped.startswith("CREATE INDEX"):
        return index_existiert(conn, key)
    return False


def migrate(db_path: Path) -> None:
    print(bold(f"\nMigration Projekte-Plan -> {db_path}"))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    applied = 0
    skipped = 0
    try:
        for key, sql in MIGRATIONS:
            if ist_erledigt(conn, key, sql):
                print(f"  {yellow('skip')} {key}")
                skipped += 1
            else:
                conn.execute(sql)
                conn.commit()
                print(f"  {green('ok  ')} {key}")
                applied += 1
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

    print()
    print(f"  Angewendet: {applied}  |  Übersprungen: {skipped}")
    print(bold("Fertig.\n"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Projekte-Plan-Migration")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Pfad zur SQLite-DB")
    args = parser.parse_args()
    migrate(Path(args.db))
