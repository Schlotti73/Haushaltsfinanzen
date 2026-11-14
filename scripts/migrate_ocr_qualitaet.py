"""
migrate_ocr_qualitaet.py – Fügt Konfidenz/Hinweis zur OCR-Qualitätsbewertung
an haushaltsbuch_eintrag hinzu. Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_ocr_qualitaet.py
    python scripts/migrate_ocr_qualitaet.py --db pfad/zu/finanzen.db
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
    ("ocr_konfidenz", "ALTER TABLE haushaltsbuch_eintrag ADD COLUMN ocr_konfidenz REAL"),
    ("ocr_hinweis",   "ALTER TABLE haushaltsbuch_eintrag ADD COLUMN ocr_hinweis TEXT"),
]


def run(db_path: Path) -> None:
    con = sqlite3.connect(db_path)
    cur = con.cursor()

    existing_cols = {row[1] for row in cur.execute("PRAGMA table_info(haushaltsbuch_eintrag)")}

    for name, sql in MIGRATIONS:
        if name in existing_cols:
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
