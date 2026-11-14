"""
Empfänger-Stammdaten (Phase 7.4).
CRUD + Suche + Merge zweier Einträge.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Buchung, Empfaenger, Geschaeft
from app.schemas import EmpfaengerCreate, EmpfaengerOut, EmpfaengerUpdate
from app.services import empfaenger_match

router = APIRouter(prefix="/empfaenger", tags=["empfaenger"])


@router.get("", response_model=list[EmpfaengerOut])
def list_empfaenger(
    suche: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Empfaenger)
    if suche:
        like = f"%{suche}%"
        q = q.filter(or_(Empfaenger.name.ilike(like), Empfaenger.iban.ilike(like)))
    return q.order_by(Empfaenger.name).all()


@router.get("/vorschlaege", response_model=list[EmpfaengerOut])
def vorschlaege(
    q: str = Query(..., min_length=1),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Fuzzy-Vorschläge für Autocomplete im Buchungsformular."""
    return empfaenger_match.vorschlaege(db, q, limit)


@router.get("/match")
def match_empfaenger(
    text: str = Query(...),
    iban: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Gibt den besten Match zurück (oder null)."""
    e = empfaenger_match.match(db, text, iban)
    if e is None:
        return None
    return {"id": e.id, "name": e.name, "iban": e.iban, "kategorie_id": e.kategorie_id}


@router.get("/{empfaenger_id}", response_model=EmpfaengerOut)
def get_empfaenger(empfaenger_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    e = db.get(Empfaenger, empfaenger_id)
    if not e:
        raise HTTPException(404, "Nicht gefunden")
    return e


@router.post("", response_model=EmpfaengerOut, status_code=201)
def create_empfaenger(body: EmpfaengerCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    e = Empfaenger(**body.model_dump())
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


@router.patch("/{empfaenger_id}", response_model=EmpfaengerOut)
def update_empfaenger(empfaenger_id: int, body: EmpfaengerUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    e = db.get(Empfaenger, empfaenger_id)
    if not e:
        raise HTTPException(404, "Nicht gefunden")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(e, field, val)
    db.commit()
    db.refresh(e)
    return e


@router.post("/{empfaenger_id}/zusammenfuehren", response_model=EmpfaengerOut)
def zusammenfuehren(
    empfaenger_id: int,
    ziel_id: int = Query(..., description="ID des Empfängers, der übrig bleiben soll"),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Führt zwei Empfänger zusammen: Buchungen von empfaenger_id → ziel_id, dann löschen."""
    quelle = db.get(Empfaenger, empfaenger_id)
    ziel = db.get(Empfaenger, ziel_id)
    if not quelle or not ziel:
        raise HTTPException(404, "Empfänger nicht gefunden")
    if quelle.id == ziel.id:
        raise HTTPException(400, "Quelle und Ziel identisch")

    db.query(Buchung).filter(Buchung.empfaenger_id == empfaenger_id).update(
        {"empfaenger_id": ziel_id}
    )
    # Ohne dieses Umhängen würde ondelete="SET NULL" die Geschäfte still entkoppeln.
    db.query(Geschaeft).filter(Geschaeft.empfaenger_id == empfaenger_id).update(
        {"empfaenger_id": ziel_id}
    )
    db.delete(quelle)
    db.commit()
    db.refresh(ziel)
    return ziel


@router.delete("/{empfaenger_id}", status_code=204)
def delete_empfaenger(empfaenger_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    e = db.get(Empfaenger, empfaenger_id)
    if not e:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(e)
    db.commit()
