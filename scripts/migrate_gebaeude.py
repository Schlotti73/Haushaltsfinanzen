"""
migrate_gebaeude.py – Additive DB-Migration für das Gebäude-Modul
(Gebäude, Zähler, Ablesungen, Nebenkosten-Kategorien).
Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_gebaeude.py
    python scripts/migrate_gebaeude.py --db pfad/zu/finanzen.db
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
    ("gebaeude_tabelle", """
        CREATE TABLE IF NOT EXISTS gebaeude (
            id      INTEGER PRIMARY KEY,
            name    VARCHAR NOT NULL UNIQUE,
            strasse VARCHAR,
            plz     VARCHAR,
            ort     VARCHAR,
            notiz   TEXT,
            aktiv   BOOLEAN NOT NULL DEFAULT 1
        )
    """),
    ("zaehler_tabelle", """
        CREATE TABLE IF NOT EXISTS zaehler (
            id                        INTEGER PRIMARY KEY,
            gebaeude_id               INTEGER NOT NULL REFERENCES gebaeude(id) ON DELETE CASCADE,
            name                      VARCHAR NOT NULL,
            seriennummer              VARCHAR,
            art                       VARCHAR NOT NULL DEFAULT 'sonstige',
            einheit                   VARCHAR NOT NULL DEFAULT 'kWh',
            richtung                  VARCHAR NOT NULL DEFAULT 'bezug',
            sortierung                INTEGER NOT NULL DEFAULT 0,
            aktiv                     BOOLEAN NOT NULL DEFAULT 1,
            notiz                     TEXT,
            uebergeordneter_zaehler_id INTEGER REFERENCES zaehler(id) ON DELETE SET NULL,
            kategorie_id              INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
            gueltig_ab                VARCHAR,
            gueltig_bis               VARCHAR,
            ersetzt_zaehler_id        INTEGER REFERENCES zaehler(id) ON DELETE SET NULL,
            CONSTRAINT uq_zaehler_gebaeude_name_ab UNIQUE (gebaeude_id, name, gueltig_ab),
            CONSTRAINT ck_zaehler_art CHECK (art IN ('strom','wasser','abwasser','gas','waerme','sonstige')),
            CONSTRAINT ck_zaehler_richtung CHECK (richtung IN ('bezug','einspeisung'))
        )
    """),
    ("idx_zaehler_gebaeude", """
        CREATE INDEX IF NOT EXISTS idx_zaehler_gebaeude ON zaehler(gebaeude_id)
    """),
    ("zaehler_ablesung_tabelle", """
        CREATE TABLE IF NOT EXISTS zaehler_ablesung (
            id         INTEGER PRIMARY KEY,
            zaehler_id INTEGER NOT NULL REFERENCES zaehler(id) ON DELETE CASCADE,
            datum      VARCHAR NOT NULL,
            jahr       INTEGER NOT NULL,
            stand      FLOAT   NOT NULL,
            art        VARCHAR NOT NULL DEFAULT 'jahr',
            notiz      TEXT,
            CONSTRAINT uq_ablesung_zaehler_jahr_art UNIQUE (zaehler_id, jahr, art),
            CONSTRAINT ck_ablesung_art CHECK (art IN ('jahr','zwischen'))
        )
    """),
    ("idx_ablesung_zaehler", """
        CREATE INDEX IF NOT EXISTS idx_ablesung_zaehler ON zaehler_ablesung(zaehler_id, jahr)
    """),
    ("gebaeude_kostenkategorie_tabelle", """
        CREATE TABLE IF NOT EXISTS gebaeude_kostenkategorie (
            id           INTEGER PRIMARY KEY,
            gebaeude_id  INTEGER NOT NULL REFERENCES gebaeude(id) ON DELETE CASCADE,
            kategorie_id INTEGER NOT NULL REFERENCES kategorien(id) ON DELETE CASCADE,
            sortierung   INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_gebaeude_kategorie UNIQUE (gebaeude_id, kategorie_id)
        )
    """),
]


def tabelle_existiert(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,))
    return cur.fetchone() is not None


def index_existiert(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (name,))
    return cur.fetchone() is not None


def ist_erledigt(conn: sqlite3.Connection, key: str, sql: str) -> bool:
    sql_stripped = sql.strip().upper()
    if sql_stripped.startswith("CREATE TABLE"):
        return tabelle_existiert(conn, key.replace("_tabelle", ""))
    if sql_stripped.startswith("CREATE INDEX"):
        return index_existiert(conn, key)
    return False


def migrate(db_path: Path) -> None:
    print(bold(f"\nMigration Gebaeude -> {db_path}"))
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")
    applied = skipped = 0
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
    parser = argparse.ArgumentParser(description="Gebaeude-Migration")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Pfad zur SQLite-DB")
    args = parser.parse_args()
    migrate(Path(args.db))
