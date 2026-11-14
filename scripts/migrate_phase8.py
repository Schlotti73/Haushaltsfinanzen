"""
migrate_phase8.py – Additive DB-Migration für Phase 8 (Haushaltsbuch als eigenes Objekt).
Idempotent: kann beliebig oft ausgeführt werden.

Aufruf (aus Projektwurzel):
    python scripts/migrate_phase8.py
    python scripts/migrate_phase8.py --db pfad/zu/finanzen.db
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


# ── Schritt 1: Neue Tabellen + Spalten (generisches Muster wie Phase 7) ──────
MIGRATIONS: list[tuple[str, str]] = [
    ("geschaeft_tabelle", """
        CREATE TABLE IF NOT EXISTS geschaeft (
            id                    INTEGER PRIMARY KEY,
            name                  TEXT    NOT NULL UNIQUE,
            standard_kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL,
            empfaenger_id         INTEGER REFERENCES empfaenger(id) ON DELETE SET NULL,
            aktiv                 INTEGER NOT NULL DEFAULT 1
        )
    """),
    ("haushaltsbuch_eintrag_tabelle", """
        CREATE TABLE IF NOT EXISTS haushaltsbuch_eintrag (
            id              INTEGER PRIMARY KEY,
            datum           TEXT    NOT NULL,
            geschaeft_id    INTEGER REFERENCES geschaeft(id) ON DELETE SET NULL,
            betrag_gesamt   REAL    NOT NULL,
            bezahlart       TEXT    NOT NULL CHECK (bezahlart IN ('bar', 'karte', 'konto')),
            konto_id        INTEGER REFERENCES konten(id) ON DELETE SET NULL,
            buchung_id      INTEGER NOT NULL REFERENCES buchungen(id) ON DELETE CASCADE,
            abgleich_status TEXT    NOT NULL DEFAULT 'bar_ohne_konto'
                                    CHECK (abgleich_status IN ('bar_ohne_konto', 'offen', 'verknuepft')),
            ocr_status      TEXT    NOT NULL DEFAULT 'keine'
                                    CHECK (ocr_status IN ('keine', 'roh', 'geparst')),
            ocr_rohtext     TEXT,
            notiz           TEXT,
            erstellt_von    INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            erstellt_am     TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """),
    ("haushaltsbuch_position_tabelle", """
        CREATE TABLE IF NOT EXISTS haushaltsbuch_position (
            id           INTEGER PRIMARY KEY,
            eintrag_id   INTEGER NOT NULL REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
            bezeichnung  TEXT    NOT NULL,
            menge        REAL    NOT NULL DEFAULT 1,
            einzelpreis  REAL,
            gesamtpreis  REAL    NOT NULL,
            kategorie_id INTEGER REFERENCES kategorien(id) ON DELETE SET NULL
        )
    """),
    ("belege_eintrag_id", """
        ALTER TABLE belege ADD COLUMN eintrag_id INTEGER
            REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE
    """),
    ("idx_hhe_geschaeft", "CREATE INDEX IF NOT EXISTS idx_hhe_geschaeft ON haushaltsbuch_eintrag(geschaeft_id)"),
    ("idx_hhe_buchung", "CREATE INDEX IF NOT EXISTS idx_hhe_buchung ON haushaltsbuch_eintrag(buchung_id)"),
    ("idx_hhe_status", "CREATE INDEX IF NOT EXISTS idx_hhe_status ON haushaltsbuch_eintrag(abgleich_status)"),
    ("idx_hhp_eintrag", "CREATE INDEX IF NOT EXISTS idx_hhp_eintrag ON haushaltsbuch_position(eintrag_id)"),
    ("idx_belege_eintrag", "CREATE INDEX IF NOT EXISTS idx_belege_eintrag ON belege(eintrag_id)"),
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


# ── Schritt 2: belege.buchung_id nullable machen (Tabellen-Rebuild) ──────────
def belege_buchung_id_ist_nullable(conn: sqlite3.Connection) -> bool:
    cur = conn.execute("PRAGMA table_info(belege)")
    for row in cur.fetchall():
        if row[1] == "buchung_id":
            return row[3] == 0  # notnull-Flag
    return True


def rebuild_belege_nullable(conn: sqlite3.Connection) -> None:
    """SQLite kennt kein ALTER COLUMN -> Tabelle neu anlegen, Daten kopieren."""
    conn.execute("""
        CREATE TABLE belege_neu (
            id              INTEGER PRIMARY KEY,
            buchung_id      INTEGER REFERENCES buchungen(id) ON DELETE CASCADE,
            eintrag_id      INTEGER REFERENCES haushaltsbuch_eintrag(id) ON DELETE CASCADE,
            dateiname       TEXT    NOT NULL,
            dateipfad       TEXT    NOT NULL,
            hochgeladen_von INTEGER REFERENCES benutzer(id) ON DELETE SET NULL,
            hochgeladen_am  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CHECK ((buchung_id IS NULL) <> (eintrag_id IS NULL))
        )
    """)
    conn.execute("""
        INSERT INTO belege_neu (id, buchung_id, eintrag_id, dateiname, dateipfad, hochgeladen_von, hochgeladen_am)
        SELECT id, buchung_id, eintrag_id, dateiname, dateipfad, hochgeladen_von, hochgeladen_am FROM belege
    """)
    conn.execute("DROP TABLE belege")
    conn.execute("ALTER TABLE belege_neu RENAME TO belege")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_belege_eintrag ON belege(eintrag_id)")


# ── Schritt 3: bestehende HHB-Buchungen in das neue Modell ueberfuehren ──────
def migriere_bestehende_hhb(conn: sqlite3.Connection) -> tuple[int, int]:
    """
    Wrappt jede Buchung mit quelle='haushaltsbuch', die noch keinen
    haushaltsbuch_eintrag hat, in einen neuen Eintrag. Die Buchung selbst
    bleibt unverändert erhalten (Deckung) -> Saldo/Statistik unveraendert.
    Geschaefte werden aus den distinkten Empfaenger-Werten geseedet.
    """
    rows = conn.execute("""
        SELECT b.id, b.datum, b.betrag, b.empfaenger, b.konto_id, b.notiz, b.erstellt_von, b.erstellt_am
        FROM buchungen b
        WHERE b.quelle = 'haushaltsbuch'
          AND b.id NOT IN (SELECT buchung_id FROM haushaltsbuch_eintrag)
    """).fetchall()

    geschaeft_cache: dict[str, int] = {}
    eintraege = 0
    belege_umgehaengt = 0

    for buchung_id, datum, betrag, empfaenger, konto_id, notiz, erstellt_von, erstellt_am in rows:
        name = (empfaenger or "Unbekannt").strip() or "Unbekannt"
        geschaeft_id = geschaeft_cache.get(name)
        if geschaeft_id is None:
            cur = conn.execute("SELECT id FROM geschaeft WHERE name = ?", (name,))
            row = cur.fetchone()
            if row:
                geschaeft_id = row[0]
            else:
                cur = conn.execute("INSERT INTO geschaeft (name) VALUES (?)", (name,))
                geschaeft_id = cur.lastrowid
            geschaeft_cache[name] = geschaeft_id

        bezahlart = "bar" if konto_id is None else "konto"
        abgleich_status = "bar_ohne_konto" if konto_id is None else "verknuepft"

        cur = conn.execute("""
            INSERT INTO haushaltsbuch_eintrag
                (datum, geschaeft_id, betrag_gesamt, bezahlart, konto_id, buchung_id,
                 abgleich_status, notiz, erstellt_von, erstellt_am)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            datum, geschaeft_id, abs(betrag), bezahlart, konto_id, buchung_id,
            abgleich_status, notiz, erstellt_von, erstellt_am,
        ))
        eintrag_id = cur.lastrowid
        eintraege += 1

        cur = conn.execute(
            "UPDATE belege SET eintrag_id = ?, buchung_id = NULL WHERE buchung_id = ?",
            (eintrag_id, buchung_id),
        )
        belege_umgehaengt += cur.rowcount

    return eintraege, belege_umgehaengt


def migrate(db_path: Path) -> None:
    print(bold(f"\nMigration Phase 8 -> {db_path}"))
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

        if belege_buchung_id_ist_nullable(conn):
            print(f"  {yellow('skip')} belege_buchung_id_nullable")
            skipped += 1
        else:
            rebuild_belege_nullable(conn)
            conn.commit()
            print(f"  {green('ok  ')} belege_buchung_id_nullable")
            applied += 1

        eintraege, belege_umgehaengt = migriere_bestehende_hhb(conn)
        conn.commit()
        if eintraege:
            print(f"  {green('ok  ')} daten_migration ({eintraege} Eintraege, {belege_umgehaengt} Belege umgehaengt)")
            applied += 1
        else:
            print(f"  {yellow('skip')} daten_migration (nichts zu tun)")
            skipped += 1
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()

    print()
    print(f"  Angewendet: {applied}  |  Übersprungen: {skipped}")
    print(bold("Fertig.\n"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Phase-8-Migration")
    parser.add_argument("--db", default=str(DB_DEFAULT), help="Pfad zur SQLite-DB")
    args = parser.parse_args()
    migrate(Path(args.db))
