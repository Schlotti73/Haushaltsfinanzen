from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import WiederkehrendeBuchung
from app.schemas import WiederkehrendCreate, WiederkehrendOut, WiederkehrendUpdate

router = APIRouter(prefix="/wiederkehrend", tags=["wiederkehrend"])


@router.get("", response_model=list[WiederkehrendOut])
def list_wiederkehrend(nur_aktiv: bool = True, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(WiederkehrendeBuchung)
    if nur_aktiv:
        q = q.filter(WiederkehrendeBuchung.aktiv == True)
    return q.order_by(WiederkehrendeBuchung.empfaenger).all()


@router.get("/{wk_id}", response_model=WiederkehrendOut)
def get_wiederkehrend(wk_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    wk = db.get(WiederkehrendeBuchung, wk_id)
    if not wk:
        raise HTTPException(404, "Nicht gefunden")
    return wk


@router.post("", response_model=WiederkehrendOut, status_code=201)
def create_wiederkehrend(body: WiederkehrendCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    wk = WiederkehrendeBuchung(**body.model_dump())
    db.add(wk)
    db.commit()
    db.refresh(wk)
    return wk


@router.patch("/{wk_id}", response_model=WiederkehrendOut)
def update_wiederkehrend(wk_id: int, body: WiederkehrendUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    wk = db.get(WiederkehrendeBuchung, wk_id)
    if not wk:
        raise HTTPException(404, "Nicht gefunden")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(wk, field, val)
    db.commit()
    db.refresh(wk)
    return wk


@router.delete("/{wk_id}", status_code=204)
def delete_wiederkehrend(wk_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    wk = db.get(WiederkehrendeBuchung, wk_id)
    if not wk:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(wk)
    db.commit()
