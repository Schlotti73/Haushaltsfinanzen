"""Mehrfach-Datenbank-Verwaltung: registrierte DBs anlegen, wechseln, entfernen."""

import json
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.auth import hash_passwort, require_admin
from app.config import settings
from app.db_init import init_db_schema
from app.db_registry import naechste_id, schreibe_eintraege, stelle_erstregistrierung_sicher
from app.models import Benutzer, Kategorie
from app.routers.einstellungen import _slug, fuehre_backup_aus
from app.pfade import daten_dir, vorlagen_dir

router = APIRouter(prefix="/einstellungen/datenbanken", tags=["datenbanken"])

_DATEN = daten_dir()
_DB_ORDNER = _DATEN / "databases"
# Vorlage, nicht Einstellung: wird nur gelesen und kommt aus dem Paket.
_KATEGORIEN_MINIMAL = vorlagen_dir() / "kategorien_minimal.json"
_STANDARD_ADMIN_NAME = "Admin"
_STANDARD_ADMIN_PASSWORT = "admin123"


class DatenbankEintrag(BaseModel):
    id: int
    name: str
    dateipfad: str
    aktiv: bool
    groesse: Optional[int] = None


class DatenbankErstellen(BaseModel):
    name: str


class DatenbankErgebnis(BaseModel):
    ok: bool
    meldung: Optional[str] = None


def _mit_groesse(eintrag: dict) -> DatenbankEintrag:
    pfad = Path(eintrag["dateipfad"])
    groesse = pfad.stat().st_size if pfad.exists() else None
    return DatenbankEintrag(
        id=eintrag["id"], name=eintrag["name"], dateipfad=eintrag["dateipfad"],
        aktiv=bool(eintrag["aktiv"]), groesse=groesse,
    )


def _finde(eintraege: list[dict], eintrag_id: int) -> dict:
    ziel = next((e for e in eintraege if e["id"] == eintrag_id), None)
    if ziel is None:
        raise HTTPException(404, "Datenbank nicht gefunden")
    return ziel


def _seed_minimal_kategorien(engine) -> None:
    daten = json.loads(_KATEGORIEN_MINIMAL.read_text(encoding="utf-8"))
    Session = sessionmaker(bind=engine)
    db = Session()

    def einfuegen(eintraege: list[dict], parent_id: Optional[int] = None) -> None:
        for e in eintraege:
            k = Kategorie(name=e["name"], art=e["art"], uebergeordnet_id=parent_id, aktiv=True)
            db.add(k)
            db.flush()
            if e.get("kinder"):
                einfuegen(e["kinder"], k.id)

    try:
        einfuegen(daten["kategorien"])
        db.commit()
    finally:
        db.close()


def _seed_admin(engine) -> None:
    """Legt den Standard-Admin-Benutzer an – ohne ihn könnte sich nach dem
    Wechsel auf die neue, leere DB niemand mehr einloggen."""
    Session = sessionmaker(bind=engine)
    db = Session()
    try:
        db.add(Benutzer(
            name=_STANDARD_ADMIN_NAME,
            passwort_hash=hash_passwort(_STANDARD_ADMIN_PASSWORT),
            rolle="admin",
            aktiv=True,
        ))
        db.commit()
    finally:
        db.close()


@router.get("", response_model=list[DatenbankEintrag])
def liste(_: Benutzer = Depends(require_admin)):
    eintraege = stelle_erstregistrierung_sicher(settings.db_path)
    return [_mit_groesse(e) for e in eintraege]


@router.post("", response_model=DatenbankEintrag)
def erstellen(body: DatenbankErstellen, _: Benutzer = Depends(require_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(400, "Name darf nicht leer sein")

    eintraege = stelle_erstregistrierung_sicher(settings.db_path)
    bekannte_pfade = {str(Path(e["dateipfad"]).resolve()) for e in eintraege}

    _DB_ORDNER.mkdir(parents=True, exist_ok=True)
    basis = _slug(name)
    dateiname = f"{basis}.db"
    ziel = _DB_ORDNER / dateiname
    n = 2
    while str(ziel.resolve()) in bekannte_pfade or ziel.exists():
        dateiname = f"{basis}-{n}.db"
        ziel = _DB_ORDNER / dateiname
        n += 1

    neue_engine = create_engine(f"sqlite:///{ziel}", connect_args={"check_same_thread": False})
    try:
        init_db_schema(neue_engine)
        _seed_minimal_kategorien(neue_engine)
        _seed_admin(neue_engine)
    finally:
        neue_engine.dispose()

    eintrag = {"id": naechste_id(eintraege), "name": name, "dateipfad": str(ziel), "aktiv": False}
    eintraege.append(eintrag)
    schreibe_eintraege(eintraege)
    return _mit_groesse(eintrag)


@router.post("/{eintrag_id}/wechseln", response_model=DatenbankErgebnis)
def wechseln(eintrag_id: int, _: Benutzer = Depends(require_admin)):
    eintraege = stelle_erstregistrierung_sicher(settings.db_path)
    ziel = _finde(eintraege, eintrag_id)
    if ziel.get("aktiv"):
        raise HTTPException(400, "Diese Datenbank ist bereits aktiv")

    try:
        backup_ergebnis = fuehre_backup_aus()
    except HTTPException as exc:
        return DatenbankErgebnis(ok=False, meldung=f"Backup fehlgeschlagen, Wechsel abgebrochen: {exc.detail}")
    if not backup_ergebnis.ok:
        return DatenbankErgebnis(
            ok=False,
            meldung=f"Backup fehlgeschlagen, Wechsel abgebrochen: {backup_ergebnis.meldung}",
        )

    for e in eintraege:
        e["aktiv"] = (e["id"] == eintrag_id)
    schreibe_eintraege(eintraege)

    name = ziel["name"]
    return DatenbankErgebnis(ok=True, meldung=f"Umgestellt auf „{name}“. Bitte Server neu starten.")


@router.delete("/{eintrag_id}", response_model=DatenbankErgebnis)
def entfernen(eintrag_id: int, _: Benutzer = Depends(require_admin)):
    eintraege = stelle_erstregistrierung_sicher(settings.db_path)
    ziel = _finde(eintraege, eintrag_id)
    if ziel.get("aktiv"):
        raise HTTPException(400, "Aktive Datenbank kann nicht entfernt werden")
    eintraege = [e for e in eintraege if e["id"] != eintrag_id]
    schreibe_eintraege(eintraege)
    return DatenbankErgebnis(ok=True)


@router.delete("/{eintrag_id}/datei", response_model=DatenbankErgebnis)
def datei_loeschen(eintrag_id: int, _: Benutzer = Depends(require_admin)):
    eintraege = stelle_erstregistrierung_sicher(settings.db_path)
    ziel = _finde(eintraege, eintrag_id)
    if ziel.get("aktiv"):
        raise HTTPException(400, "Aktive Datenbank kann nicht gelöscht werden")

    pfad = Path(ziel["dateipfad"]).resolve()
    if _DB_ORDNER.resolve() not in pfad.parents:
        raise HTTPException(400, "Nur Datenbanken im databases/-Ordner können gelöscht werden")

    for kandidat in (pfad, pfad.with_suffix(".db-wal"), pfad.with_suffix(".db-shm")):
        kandidat.unlink(missing_ok=True)

    # Zugehörige Datei-Ablagen (Belege, Kontoauszug-/Kassenzettel-Muster) dieser
    # DB entfernen – siehe app.config für die db-<id>-Unterordner-Konvention.
    # id 1 (Standard) landet hier nie, da ihre Datei außerhalb von databases/
    # liegt und oben bereits abgelehnt worden wäre.
    unterordner = f"db-{eintrag_id}"
    for basis in ("belege", "kontoauszug_muster", "kassenzettel_muster"):
        shutil.rmtree(_DATEN / basis / unterordner, ignore_errors=True)

    eintraege = [e for e in eintraege if e["id"] != eintrag_id]
    schreibe_eintraege(eintraege)
    return DatenbankErgebnis(ok=True)
