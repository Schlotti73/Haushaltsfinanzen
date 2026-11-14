"""
migrate_konten_darlehen.py – Additive DB-Migration für das Modul "Konten"
(Annuitäten-Darlehen: Loan-Felder am Konto + Tabelle sondertilgung).
Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_konten_darlehen.py
    python scripts/migrate_konten_darlehen.py --db pfad/zu/finanzen.db
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
    ("konten_darlehen_betrag", "ALTER TABLE konten ADD COLUMN darlehen_betrag FLOAT"),
    ("konten_zinssatz", "ALTER TABLE konten ADD COLUMN zinssatz FLOAT"),
    ("konten_effektiver_zinssatz", "ALTER TABLE konten ADD COLUMN effektiver_zinssatz FLOAT"),
    ("konten_tilgungssatz", "ALTER TABLE konten ADD COLUMN tilgungssatz FLOAT"),
    ("konten_rate", "ALTER TABLE konten ADD COLUMN rate FLOAT"),
    ("konten_tilgung_start", "ALTER TABLE konten ADD COLUMN tilgung_start VARCHAR"),
    ("konten_zinsbindung_bis", "ALTER TABLE konten ADD COLUMN zinsbindung_bis VARCHAR"),
    ("sondertilgung_tabelle", """
        CREATE TABLE IF NOT EXISTS sondertilgung (
            id        INTEGER PRIMARY KEY,
            konto_id  INTEGER NOT NULL REFERENCES konten(id) ON DELETE CASCADE,
            datum     VARCHAR NOT NULL,
            betrag    FLOAT   NOT NULL,
            notiz     TEXT
        )
    """),
    ("idx_sondertilgung_konto", """
        CREATE INDEX IF NOT EXISTS idx_sondertilgung_konto ON sondertilgung(konto_id)
    """),
]


def spaltennamen(conn: sqlite3.Connection, tabelle: str) -> set[str]:
    cur = conn.execute(f"PRAGMA table_info({tabelle})")
    return {row[1] for row in cur.fetchall()}


def tabelle_existiert(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def index_existiert(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,))
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
    print(bold(f"\nMigration Konten-Darlehen -> {db_path}"))
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
    parser = argparse.ArgumentParser(description="Konten-Darlehen-Migration")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Pfad zur SQLite-DB")
    args = parser.parse_args()
    migrate(Path(args.db))
