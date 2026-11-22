"""Laden, Wiedererkennen und Speichern der CSV-Profile."""

from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models import CsvProfil


class ProfilFehlt(Exception):
    """Für diese Datei gibt es noch kein Profil.

    Trägt den Erkennungsvorschlag mit, damit der Aufrufer die Zuordnungsmaske
    gefüllt anzeigen kann statt nur einen Fehler.
    """

    def __init__(self, vorschlag: dict):
        super().__init__("Kein CSV-Profil für diese Datei")
        self.vorschlag = vorschlag


def als_dict(p: CsvProfil) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "bank_key": p.bank_key,
        "struktur": json.loads(p.struktur or "{}"),
        "zuordnung": json.loads(p.zuordnung or "{}"),
        "kopf_signatur": json.loads(p.kopf_signatur or "[]"),
        "aktiv": p.aktiv,
        "notiz": p.notiz,
        "erstellt_am": p.erstellt_am.isoformat(timespec="seconds"),
    }


def bank_key_bilden(name: str, db: Session, eigene_id: Optional[int] = None) -> str:
    """Kleingeschriebener Name ohne Sonderzeichen, bei Kollision mit Zähler."""
    basis = re.sub(r"[^a-z0-9]+", "-", (name or "csv").lower()).strip("-") or "csv"
    kandidat, n = basis, 1
    while True:
        treffer = db.query(CsvProfil).filter(CsvProfil.bank_key == kandidat).first()
        if not treffer or treffer.id == eigene_id:
            return kandidat
        n += 1
        kandidat = f"{basis}-{n}"


def _normalisiert(kopf: list) -> list[str]:
    return [str(k).strip().lower() for k in kopf if str(k).strip()]


def profil_finden(db: Session, kopf: list) -> tuple[Optional[dict], float]:
    """Profil zu einer Spaltenzeile, plus Trefferquote.

    Zuerst die genaue Übereinstimmung der Spaltennamen. Fehlt die, wird das
    Profil mit der größten Überdeckung zurückgegeben – eine Bank, die eine
    Spalte umbenennt oder hinzufügt, soll ihr Profil nicht verlieren, sondern
    es zur Bestätigung vorgelegt bekommen.
    """
    ziel = set(_normalisiert(kopf))
    if not ziel:
        return None, 0.0

    bestes, beste_quote = None, 0.0
    for p in db.query(CsvProfil).filter(CsvProfil.aktiv.is_(True)).order_by(CsvProfil.id):
        signatur = set(_normalisiert(json.loads(p.kopf_signatur or "[]")))
        if not signatur:
            continue
        if signatur == ziel:
            return als_dict(p), 1.0
        quote = len(signatur & ziel) / len(signatur | ziel)
        if quote > beste_quote:
            bestes, beste_quote = als_dict(p), quote
    # Unter zwei Dritteln Überdeckung ist es eine andere Bank, kein geändertes
    # Format: dann lieber ein neues Profil anlegen als ein fremdes verbiegen.
    return (bestes, beste_quote) if beste_quote >= 0.66 else (None, beste_quote)


def profil_laden(db: Session, profil_id: int) -> dict:
    p = db.get(CsvProfil, profil_id)
    if not p:
        raise ProfilFehlt({"fehler": f"Profil {profil_id} gibt es nicht."})
    return als_dict(p)
