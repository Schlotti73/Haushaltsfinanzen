"""
Generierung geplanter Buchungen aus wiederkehrende_buchungen.
POST /generierung/vorschau  – zeigt was generiert würde (dry-run)
POST /generierung/ausfuehren – schreibt tatsächlich in buchungen
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Buchung, WiederkehrendeBuchung

router = APIRouter(prefix="/generierung", tags=["generierung"])


def _naechste_daten(wb: WiederkehrendeBuchung, bis: date) -> list[date]:
    """Gibt alle Fälligkeitsdaten einer Vorlage bis zum Datum `bis` zurück."""
    start = wb.start_datum
    if start is None:
        return []
    if isinstance(start, str):
        start = date.fromisoformat(start)
    if isinstance(bis, str):
        bis = date.fromisoformat(str(bis))

    ende = wb.end_datum
    if isinstance(ende, str) and ende:
        ende = date.fromisoformat(ende)
    else:
        ende = None

    # Start aus der Vergangenheit: nur Termine ab heute generieren
    heute = date.today()
    rhythmus = wb.rhythmus  # 'monatlich', 'quartal', 'jaehrlich'

    termine: list[date] = []
    aktuell = start
    while aktuell <= bis:
        if ende and aktuell > ende:
            break
        if aktuell >= heute:
            termine.append(aktuell)
        if rhythmus == "monatlich":
            aktuell += relativedelta(months=1)
        elif rhythmus == "zweimonatlich":
            aktuell += relativedelta(months=2)
        elif rhythmus == "quartal":
            aktuell += relativedelta(months=3)
        elif rhythmus == "jaehrlich":
            aktuell += relativedelta(years=1)
        else:
            break
    return termine


def _bereits_geplant(db: Session, wb_id: int, datum: date) -> bool:
    """Prüft ob für diesen Termin bereits eine Buchung existiert.

    Vergleicht gegen `wiederkehrend_termin`, nicht gegen `datum`: Letzteres kann
    durch einen PDF-Kontoauszug-Abgleich auf das tatsächliche Bankdatum
    überschrieben worden sein (siehe import_pdf.py, Treffer-Verknüpfung). Würde
    hier gegen `datum` geprüft, fände der Check den ursprünglichen Termin nach
    so einer Verschiebung nicht mehr und es entstünde eine doppelte Buchung.
    """
    d_str = datum.isoformat()
    return (
        db.query(Buchung)
        .filter(
            Buchung.wiederkehrend_id == wb_id,
            Buchung.wiederkehrend_termin == d_str,
        )
        .first()
        is not None
    )


@router.post("/vorschau")
def vorschau(
    monate: int = Query(12, ge=1, le=24),
    konto_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Zeigt alle Buchungen, die generiert würden (Dry-Run)."""
    bis = date.today() + relativedelta(months=monate)
    q = db.query(WiederkehrendeBuchung).filter(WiederkehrendeBuchung.aktiv == True)
    if konto_id is not None:
        q = q.filter(WiederkehrendeBuchung.konto_id == konto_id)
    vorlagen = q.all()

    ergebnis = []
    for wb in vorlagen:
        for termin in _naechste_daten(wb, bis):
            if not _bereits_geplant(db, wb.id, termin):
                ergebnis.append({
                    "vorlage_id": wb.id,
                    "empfaenger": wb.empfaenger,
                    "datum": termin.isoformat(),
                    "betrag": wb.betrag,
                    "rhythmus": wb.rhythmus,
                    "konto_id": wb.konto_id,
                    "kategorie_id": wb.kategorie_id,
                })
    return {"anzahl": len(ergebnis), "buchungen": ergebnis}


@router.post("/ausfuehren")
def ausfuehren(
    monate: int = Query(12, ge=1, le=24),
    konto_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Generiert geplante Buchungen in der Datenbank."""
    bis = date.today() + relativedelta(months=monate)
    q = db.query(WiederkehrendeBuchung).filter(WiederkehrendeBuchung.aktiv == True)
    if konto_id is not None:
        q = q.filter(WiederkehrendeBuchung.konto_id == konto_id)
    vorlagen = q.all()

    erstellt = 0
    for wb in vorlagen:
        for termin in _naechste_daten(wb, bis):
            if _bereits_geplant(db, wb.id, termin):
                continue
            buch = Buchung(
                konto_id=wb.konto_id,
                datum=termin.isoformat(),
                betrag=wb.betrag,
                empfaenger=wb.empfaenger,
                kategorie_id=wb.kategorie_id,
                projekt_id=wb.projekt_id,
                status="geplant",
                quelle="wiederkehrend",
                wiederkehrend_id=wb.id,
                wiederkehrend_termin=termin.isoformat(),
            )
            db.add(buch)
            erstellt += 1

    db.commit()
    return {"erstellt": erstellt}
