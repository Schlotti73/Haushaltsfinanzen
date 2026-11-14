"""
migrate_phase7.py – Additive DB-Migration für Phase 7.
Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_phase7.py
    python scripts/migrate_phase7.py --db pfad/zu/finanzen.db
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
    # ── 7.4 Empfänger-Stammdaten ─────────────────────────────────────────────
    ("empfaenger_tabelle", """
        CREATE TABLE IF NOT EXISTS empfaenger (
            id           INTEGER PRIMARY KEY,
            name         TEXT    NOT NULL UNIQUE,
            iban         TEXT,
            kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
            notiz        TEXT
        )
    """),
    ("buchungen_empfaenger_id", """
        ALTER TABLE buchungen ADD COLUMN empfaenger_id INTEGER
            REFERENCES empfaenger(id) ON DELETE SET NULL
    """),
    ("idx_buchungen_empfaenger", """
        CREATE INDEX IF NOT EXISTS idx_buchungen_empfaenger ON buchungen(empfaenger_id)
    """),

    # ── 7.3 Sparkonten-Transfers ─────────────────────────────────────────────
    ("buchungen_gegenbuchung_id", """
        ALTER TABLE buchungen ADD COLUMN gegenbuchung_id INTEGER
            REFERENCES buchungen(id) ON DELETE SET NULL
    """),
    ("buchungen_ist_transfer", """
        ALTER TABLE buchungen ADD COLUMN ist_transfer INTEGER NOT NULL DEFAULT 0
    """),
    ("idx_buchungen_transfer", """
        CREATE INDEX IF NOT EXISTS idx_buchungen_transfer ON buchungen(ist_transfer)
    """),

    # ── 7.1 Buchungen ↔ Haushaltsbuch ────────────────────────────────────────
    ("buchungen_verknuepft_mit_id", """
        ALTER TABLE buchungen ADD COLUMN verknuepft_mit_id INTEGER
            REFERENCES buchungen(id) ON DELETE SET NULL
    """),
    ("buchungen_verknuepfung_typ", """
        ALTER TABLE buchungen ADD COLUMN verknuepfung_typ TEXT
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
    """Prüft anhand des SQL-Typs ob die Migration schon angewendet wurde."""
    sql_stripped = sql.strip().upper()
    if sql_stripped.startswith("CREATE TABLE"):
        tbl = key.replace("_tabelle", "")
        return tabelle_existiert(conn, tbl)
    if sql_stripped.startswith("ALTER TABLE") and "ADD COLUMN" in sql_stripped:
        parts = sql.split()
        try:
            tbl_idx = parts.index("TABLE") + 1
            col_idx = parts.index("COLUMN") + 1
            tbl = parts[tbl_idx]
            col = parts[col_idx]
            return col in spaltennamen(conn, tbl)
        except (ValueError, IndexError):
            return False
    if sql_stripped.startswith("CREATE INDEX"):
        return index_existiert(conn, key)
    return False


def migrate(db_path: Path) -> None:
    print(bold(f"\nMigration Phase 7 -> {db_path}"))
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
    parser = argparse.ArgumentParser(description="Phase-7-Migration")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Pfad zur SQLite-DB")
    args = parser.parse_args()
    migrate(Path(args.db))
