"""
init_db.py – Erzeugt finanzen.db aus db/schema.sql und befüllt die
Stammdaten (Konten, Kategorie-Baum, Projekte).

Aufruf (aus Projektwurzel):
    python scripts/init_db.py            # legt finanzen.db an (Abbruch, falls vorhanden)
    python scripts/init_db.py --force    # überschreibt eine vorhandene finanzen.db

Phase 1: schafft eine lauffähige, korrekt strukturierte Datenbank mit
Stammdaten als Fundament für Import (Phase 3) und Backend (Phase 2).
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "backend"))
from app.pfade import daten_dir, vorlagen_dir  # noqa: E402 – Pfad muss vorher stehen

DB_PATH = daten_dir() / "finanzen.db"
# Schema und Saat-Daten gehoeren zum Programm, die Datenbank zu den Daten.
SCHEMA_PATH = ROOT / "db" / "schema.sql"
KATEGORIEN_JSON = vorlagen_dir() / "kategorien.json"
MAPPING_JSON = vorlagen_dir() / "mapping.json"


def create_schema(con: sqlite3.Connection) -> None:
    con.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def seed_konten(con: sqlite3.Connection) -> int:
    """Konten aus dem konten_mapping der mapping.json anlegen."""
    mapping = json.loads(MAPPING_JSON.read_text(encoding="utf-8"))
    konten = mapping["konten_mapping"]
    rows = [
        (name, cfg["typ"], cfg.get("bank"), i)
        for i, (name, cfg) in enumerate(konten.items())
    ]
    con.executemany(
        "INSERT INTO konten (name, typ, bank, sortierung) VALUES (?, ?, ?, ?)",
        rows,
    )
    return len(rows)


def seed_kategorien(con: sqlite3.Connection) -> int:
    """Zweistufigen Kategorie-Baum aus kategorien.json einlesen."""
    data = json.loads(KATEGORIEN_JSON.read_text(encoding="utf-8"))
    count = 0
    for top in data["kategorien"]:
        cur = con.execute(
            "INSERT INTO kategorien (name, art, uebergeordnet_id) VALUES (?, ?, NULL)",
            (top["name"], top["art"]),
        )
        parent_id = cur.lastrowid
        count += 1
        for kind in top.get("kinder", []):
            con.execute(
                "INSERT INTO kategorien (name, art, uebergeordnet_id) VALUES (?, ?, ?)",
                (kind["name"], kind["art"], parent_id),
            )
            count += 1
    return count


def seed_admin(con: sqlite3.Connection, passwort: str) -> None:
    """Legt den Admin-Benutzer 'admin' an (bcrypt-Hash)."""
    try:
        import bcrypt
        pw_hash = bcrypt.hashpw(passwort.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        # bcrypt nur im backend/.venv verfügbar; Fallback: SHA256 als Hinweis
        import hashlib
        pw_hash = "UNSECURE:" + hashlib.sha256(passwort.encode()).hexdigest()
        print("Warnung: bcrypt nicht gefunden – unsicherer Fallback-Hash verwendet.")
        print("         backend/.venv/Scripts/python.exe -m pip install bcrypt und dann erneut ausführen.")

    con.execute(
        "INSERT INTO benutzer (name, passwort_hash, rolle) VALUES (?, ?, 'admin')",
        ("admin", pw_hash),
    )


def seed_projekte(con: sqlite3.Connection) -> int:
    """Beispielprojekte, je eines pro Typ.

    Bewusst namenlos gehalten und ohne Budgets: dieses Skript steckt im
    Release-Paket, und das ist oeffentlich. Fruehere Fassungen haben hier die
    Ortsnamen und die echten Budgethoehen dieses Haushalts gesaet - Angaben,
    die einem fremden Nutzer nichts sagen und ihn nichts angehen.
    """
    projekte = [
        ("Projekt 1", "darlehen", None, None, None),
        ("Projekt 2", "bauprojekt", None, None, None),
        ("Projekt 3", "sonstiges", None, None, None),
        ("Projekt 4", "sonstiges", None, None, None),
    ]
    con.executemany(
        "INSERT INTO projekte (name, typ, budget, start_datum, ende_datum) "
        "VALUES (?, ?, ?, ?, ?)",
        projekte,
    )
    return len(projekte)


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialisiert finanzen.db")
    parser.add_argument("--force", action="store_true",
                        help="vorhandene finanzen.db löschen und neu anlegen")
    parser.add_argument("--passwort", default="admin123",
                        help="Passwort für den Admin-Benutzer 'admin' (Standard: admin123)")
    args = parser.parse_args()

    if DB_PATH.exists():
        if not args.force:
            raise SystemExit(
                f"{DB_PATH.name} existiert bereits. Mit --force überschreiben."
            )
        DB_PATH.unlink()

    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        create_schema(con)
        n_konten = seed_konten(con)
        n_kat = seed_kategorien(con)
        n_proj = seed_projekte(con)
        seed_admin(con, args.passwort)
        con.commit()
    finally:
        con.close()

    print(f"OK – {DB_PATH} angelegt.")
    print(f"  Konten:     {n_konten}")
    print(f"  Kategorien: {n_kat}")
    print(f"  Projekte:   {n_proj}")
    print(f"  Admin:      admin (Passwort: {args.passwort})")


if __name__ == "__main__":
    main()
