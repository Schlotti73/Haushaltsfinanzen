"""
seed_admin.py - Schema sicherstellen und bei leerer DB einen ersten
Admin-Benutzer anlegen.

Nutzt denselben Weg wie der App-Start selbst (backend/app/main.py::_init_db):
init_db_schema() legt bei einer neuen finanzen.db das Schema direkt aus den
SQLAlchemy-Modellen an (+ Alembic-Stempel auf head), oder bringt eine
bestehende DB per "alembic upgrade head" auf den aktuellen Stand. Ein
Admin-Benutzer wird nur angelegt, wenn die Tabelle "benutzer" noch leer ist.

Aufruf (aus Projektwurzel, mit backend/.venv):
    backend\\.venv\\Scripts\\python.exe scripts\\prod\\seed_admin.py --admin-name admin
    (Passwort wird ueber stdin eingelesen; nur noetig, wenn noch kein
    Benutzer existiert)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))
# alembic.ini hat "script_location = alembic" relativ zum Arbeitsverzeichnis
# (nicht relativ zur ini-Datei) - der laufende Dienst hat via NSSM AppDirectory
# immer backend/ als cwd, das stellen wir hier fuer den Standalone-Aufruf
# ebenso sicher, sonst findet Alembic seinen versions/-Ordner nicht.
os.chdir(ROOT / "backend")

from app.database import engine, SessionLocal  # noqa: E402
from app.db_init import init_db_schema  # noqa: E402
from app.auth import hash_passwort  # noqa: E402
from app.models import Benutzer  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Schema anlegen/aktualisieren und ggf. ersten Admin-Benutzer anlegen"
    )
    parser.add_argument(
        "--admin-name",
        help="Benutzername fuer den Admin (nur erforderlich, wenn noch kein Benutzer existiert)",
    )
    args = parser.parse_args()

    init_db_schema(engine)

    with engine.connect() as conn:
        revision = conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar()
    print(f"Schema aktuell (Alembic-Revision: {revision}).")

    db = SessionLocal()
    try:
        anzahl = db.query(Benutzer).count()
        if anzahl > 0:
            print(f"Admin bereits vorhanden ({anzahl} Benutzer) - kein Seed noetig.")
            print(f"ALEMBIC_REV={revision}")
            return

        if not args.admin_name:
            raise SystemExit("Fehler: --admin-name erforderlich, da noch kein Benutzer existiert.")

        passwort = sys.stdin.readline().rstrip("\n")
        if not passwort:
            raise SystemExit("Fehler: kein Passwort ueber stdin erhalten.")

        db.add(Benutzer(
            name=args.admin_name,
            passwort_hash=hash_passwort(passwort),
            rolle="admin",
            aktiv=True,
        ))
        db.commit()
        print(f"Admin-Benutzer '{args.admin_name}' angelegt.")
    finally:
        db.close()

    print(f"ALEMBIC_REV={revision}")


if __name__ == "__main__":
    main()
