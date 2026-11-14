"""
setup_fresh.py – Neue leere Datenbank für Neuinstallationen anlegen.

Liest Kategorien und Muster aus einer bestehenden Quell-DB und überträgt
sie als Vorbelegung in eine neue leere Zieldatenbank (Schema + Admin-Benutzer).
Transaktionsdaten (Buchungen, Konten, Projekte) werden NICHT übertragen.

Aufruf (aus Projektwurzel):
    python scripts/setup_fresh.py
    python scripts/setup_fresh.py --ziel pfad/zu/finanzen_neu.db
    python scripts/setup_fresh.py --quelle finanzen.db --passwort "geheim"
    python scripts/setup_fresh.py --force   # Ziel überschreiben falls vorhanden
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "db" / "schema.sql"


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def seed_admin(con: sqlite3.Connection, benutzer: str, passwort: str) -> None:
    try:
        import bcrypt
        pw_hash = bcrypt.hashpw(passwort.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        import hashlib
        pw_hash = "UNSECURE:" + hashlib.sha256(passwort.encode()).hexdigest()
        print("Warnung: bcrypt nicht gefunden – unsicherer Fallback-Hash.")
        print("         backend/.venv/Scripts/python.exe -m pip install bcrypt und erneut ausführen.")

    con.execute(
        "INSERT INTO benutzer (name, passwort_hash, rolle) VALUES (?, ?, 'admin')",
        (benutzer, pw_hash),
    )


def copy_kategorien(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    """Kategorie-Baum (zweistufig) übertragen; IDs werden neu vergeben."""
    rows = src.execute(
        "SELECT id, name, art, uebergeordnet_id, aktiv FROM kategorien ORDER BY id"
    ).fetchall()

    id_map: dict[int, int] = {}

    # Zwei Pässe: erst Eltern, dann Kinder – damit IDs beim INSERT bekannt sind
    for parent_only in (True, False):
        for old_id, name, art, parent_old, aktiv in rows:
            if parent_only and parent_old is not None:
                continue
            if not parent_only and parent_old is None:
                continue
            new_parent = id_map.get(parent_old) if parent_old else None
            cur = dst.execute(
                "INSERT INTO kategorien (name, art, uebergeordnet_id, aktiv) VALUES (?, ?, ?, ?)",
                (name, art, new_parent, aktiv),
            )
            id_map[old_id] = cur.lastrowid

    return len(rows)


def copy_kontoauszug_muster(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    try:
        rows = src.execute(
            "SELECT name, bank_key, parser_key, erkennung_keywords, "
            "feld_markierungen, aktiv, notiz "
            "FROM kontoauszug_muster ORDER BY id"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0

    dst.executemany(
        "INSERT INTO kontoauszug_muster "
        "(name, bank_key, parser_key, erkennung_keywords, feld_markierungen, aktiv, notiz) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def copy_kassenzettel_muster(src: sqlite3.Connection, dst: sqlite3.Connection) -> int:
    try:
        rows = src.execute(
            "SELECT name, geschaeft_key, erkennung_keywords, start_marker, stop_marker, "
            "skip_keywords, preis_regex, mwst_kategorie_map, aktiv, notiz "
            "FROM kassenzettel_muster ORDER BY id"
        ).fetchall()
    except sqlite3.OperationalError:
        return 0

    try:
        dst.executemany(
            "INSERT INTO kassenzettel_muster "
            "(name, geschaeft_key, erkennung_keywords, start_marker, stop_marker, "
            "skip_keywords, preis_regex, mwst_kategorie_map, aktiv, notiz) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
    except sqlite3.OperationalError:
        return 0

    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Neue leere DB für Neuinstallation anlegen (Kategorien + Muster als Vorbelegung)"
    )
    parser.add_argument(
        "--quelle", default=str(ROOT / "finanzen.db"),
        help="Bestehende DB als Quelle für Kategorien/Muster (Standard: finanzen.db)",
    )
    parser.add_argument(
        "--ziel", default=str(ROOT / "finanzen_neu.db"),
        help="Pfad der neuen Ziel-DB (Standard: finanzen_neu.db)",
    )
    parser.add_argument(
        "--benutzer", default="admin",
        help="Admin-Benutzername (Standard: admin)",
    )
    parser.add_argument(
        "--passwort", default="admin123",
        help="Admin-Passwort (Standard: admin123 – bitte vor Produktivbetrieb ändern!)",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Ziel-DB überschreiben falls sie bereits existiert",
    )
    args = parser.parse_args()

    src_path = Path(args.quelle)
    dst_path = Path(args.ziel)

    if not src_path.exists():
        raise SystemExit(f"Quell-DB nicht gefunden: {src_path}")

    if dst_path.exists():
        if not args.force:
            raise SystemExit(
                f"{dst_path.name} existiert bereits. Mit --force überschreiben."
            )
        dst_path.unlink()

    src = sqlite3.connect(src_path)
    dst = sqlite3.connect(dst_path)
    dst.execute("PRAGMA foreign_keys = ON")

    try:
        create_schema(dst)
        seed_admin(dst, args.benutzer, args.passwort)
        n_kat = copy_kategorien(src, dst)
        n_km = copy_kontoauszug_muster(src, dst)
        n_kzm = copy_kassenzettel_muster(src, dst)
        dst.commit()
    except Exception:
        dst_path.unlink(missing_ok=True)
        raise
    finally:
        src.close()
        dst.close()

    print(f"OK – {dst_path} angelegt.")
    print(f"  Admin-Benutzer:        {args.benutzer}")
    print(f"  Kategorien:            {n_kat}")
    print(f"  Kontoauszug-Muster:    {n_km}")
    print(f"  Kassenzettel-Muster:   {n_kzm}")
    print()
    print("Nächste Schritte:")
    print(f"  1. {dst_path.name} nach finanzen.db umbenennen (oder Ziel-Pfad direkt setzen)")
    print("  2. Backend starten und Admin-Passwort ändern")


if __name__ == "__main__":
    main()
