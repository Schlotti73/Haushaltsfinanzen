"""
migrate_konten_iban_bic.py – Fügt IBAN und BIC zur konten-Tabelle hinzu.
Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_konten_iban_bic.py
    python scripts/migrate_konten_iban_bic.py --db pfad/zu/finanzen.db
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_DEFAULT = ROOT / "finanzen.db"


def green(s): return f"\033[32m{s}\033[0m"
def yellow(s): return f"\033[33m{s}\033[0m"


MIGRATIONS: list[tuple[str, str]] = [
    ("konten_iban", "ALTER TABLE konten ADD COLUMN iban TEXT"),
    ("konten_bic",  "ALTER TABLE konten ADD COLUMN bic  TEXT"),
]


def run(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(konten)")}

    for name, sql in MIGRATIONS:
        col = name.split("_", 1)[1]  # "iban" or "bic"
        if col in existing_cols:
            print(yellow(f"  SKIP  {name} (Spalte existiert bereits)"))
        else:
            cur.execute(sql)
            print(green(f"  OK    {name}"))

    con.commit()
    con.close()
    print(green("Migration abgeschlossen."))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DB_DEFAULT))
    args = parser.parse_args()
    run(Path(args.db))
