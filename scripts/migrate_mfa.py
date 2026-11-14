"""
migrate_mfa.py – Additive DB-Migration für den zweiten Faktor (TOTP).
Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_mfa.py
    python scripts/migrate_mfa.py --db pfad/zu/finanzen.db
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
    ("mfa_secret", "ALTER TABLE benutzer ADD COLUMN mfa_secret VARCHAR"),
    ("mfa_aktiv", "ALTER TABLE benutzer ADD COLUMN mfa_aktiv BOOLEAN NOT NULL DEFAULT 0"),
    ("mfa_recovery", "ALTER TABLE benutzer ADD COLUMN mfa_recovery TEXT"),
]


def spaltennamen(conn: sqlite3.Connection, tabelle: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({tabelle})").fetchall()}


def migrate(db_path: Path) -> None:
    print(bold(f"\nMigration MFA -> {db_path}"))
    conn = sqlite3.connect(db_path)
    vorhanden = spaltennamen(conn, "benutzer")
    applied = skipped = 0
    try:
        for spalte, sql in MIGRATIONS:
            if spalte in vorhanden:
                print(f"  {yellow('skip')} {spalte}")
                skipped += 1
            else:
                conn.execute(sql)
                conn.commit()
                print(f"  {green('ok  ')} {spalte}")
                applied += 1
    finally:
        conn.close()

    print()
    print(f"  Angewendet: {applied}  |  Übersprungen: {skipped}")
    print(bold("Fertig.\n"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MFA-Migration")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Pfad zur SQLite-DB")
    args = parser.parse_args()
    migrate(Path(args.db))
