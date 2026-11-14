"""
Geschäfte-Stammdaten (Phase 8, erweitert Phase 15).
CRUD + Suche. Auswahlliste fürs Haushaltsbuch (Anf. 2).

Phase 15: Die Artikel-Kategorisierung (MwSt-Schlüssel→Kategorie) eines Geschäfts
wird über das 1:1 verknüpfte Kassenzettel-Muster gepflegt und hier direkt
mitgeliefert/gespeichert – damit ist die Geschäfte-Seite die eine Stelle für
„so werden meine Artikel kategorisiert". Die technischen OCR-Parser-Felder
(Marker, Regex, Beispielfoto) bleiben in den Einstellungen.
"""

from __future__ import annotations

import json
import re
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Geschaeft, KassenzettelMuster
from app.schemas import GeschaeftCreate, GeschaeftOut, GeschaeftUpdate, MwstKatEintrag

router = APIRouter(prefix="/geschaefte", tags=["geschaefte"])


# ── Helfer: Muster-Verknüpfung / MwSt-Map ─────────────────────────────────────

def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "geschaeft"


def _eindeutiger_key(db: Session, basis: str) -> str:
    key = _slug(basis)
    kandidat = key
    n = 2
    while db.query(KassenzettelMuster).filter(KassenzettelMuster.geschaeft_key == kandidat).first():
        kandidat = f"{key}-{n}"
        n += 1
    return kandidat


def _map_from_muster(m: KassenzettelMuster | None) -> list[MwstKatEintrag]:
    if not m or not m.mwst_kategorie_map:
        return []
    try:
        roh = json.loads(m.mwst_kategorie_map)
    except (ValueError, TypeError):
        return []
    ergebnis: list[MwstKatEintrag] = []
    for schluessel, kat_id in (roh or {}).items():
        try:
            ergebnis.append(MwstKatEintrag(schluessel=str(schluessel), kategorie_id=int(kat_id)))
        except (ValueError, TypeError):
            continue
    return ergebnis


def _out(g: Geschaeft) -> GeschaeftOut:
    m = g.kassenzettel_muster
    return GeschaeftOut(
        id=g.id,
        name=g.name,
        standard_kategorie_id=g.standard_kategorie_id,
        empfaenger_id=g.empfaenger_id,
        aktiv=g.aktiv,
        kassenzettel_muster_id=m.id if m else None,
        mwst_kategorie_map=_map_from_muster(m),
    )


def _apply_map(db: Session, g: Geschaeft, eintraege: list[MwstKatEintrag]) -> None:
    """Schreibt die MwSt→Kategorie-Zuordnung ins verknüpfte Muster.

    Legt bei Bedarf ein Muster an (mit Name/Keyword des Geschäfts), damit die
    Zuordnung auch für den OCR-Foto-Import greift. Eine leere Liste löscht die
    Zuordnung eines bestehenden Musters, legt aber keins an.
    """
    m = g.kassenzettel_muster
    if m is None:
        if not eintraege:
            return
        m = KassenzettelMuster(
            name=g.name,
            geschaeft_key=_eindeutiger_key(db, g.name),
            geschaeft_id=g.id,
            erkennung_keywords=json.dumps([g.name.lower()], ensure_ascii=False),
            skip_keywords="[]",
            mwst_kategorie_map="{}",
            aktiv=True,
            erstellt_am=datetime.utcnow(),
        )
        db.add(m)
    m.mwst_kategorie_map = json.dumps(
        {e.schluessel.strip(): e.kategorie_id for e in eintraege if e.schluessel.strip()},
        ensure_ascii=False,
    )


# ── CRUD ──────────────────────────────────────────────────────────────────────

@router.get("", response_model=list[GeschaeftOut])
def list_geschaefte(
    nur_aktiv: bool = Query(True),
    suche: str | None = Query(None),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Geschaeft).options(selectinload(Geschaeft.kassenzettel_muster))
    if nur_aktiv:
        q = q.filter(Geschaeft.aktiv == True)
    if suche:
        q = q.filter(Geschaeft.name.ilike(f"%{suche}%"))
    return [_out(g) for g in q.order_by(Geschaeft.name).all()]


@router.get("/{geschaeft_id}", response_model=GeschaeftOut)
def get_geschaeft(geschaeft_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    g = db.get(Geschaeft, geschaeft_id)
    if not g:
        raise HTTPException(404, "Nicht gefunden")
    return _out(g)


@router.post("", response_model=GeschaeftOut, status_code=201)
def create_geschaeft(body: GeschaeftCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if db.query(Geschaeft).filter(Geschaeft.name == body.name).first():
        raise HTTPException(400, "Geschäft mit diesem Namen existiert bereits")
    g = Geschaeft(**body.model_dump(exclude={"mwst_kategorie_map"}))
    db.add(g)
    db.flush()  # g.id für die Muster-Verknüpfung
    if body.mwst_kategorie_map is not None:
        _apply_map(db, g, body.mwst_kategorie_map)
    db.commit()
    db.refresh(g)
    return _out(g)


@router.patch("/{geschaeft_id}", response_model=GeschaeftOut)
def update_geschaeft(geschaeft_id: int, body: GeschaeftUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    g = db.get(Geschaeft, geschaeft_id)
    if not g:
        raise HTTPException(404, "Nicht gefunden")
    for field, val in body.model_dump(exclude_none=True, exclude={"mwst_kategorie_map"}).items():
        setattr(g, field, val)
    if body.mwst_kategorie_map is not None:
        _apply_map(db, g, body.mwst_kategorie_map)
    db.commit()
    db.refresh(g)
    return _out(g)


@router.delete("/{geschaeft_id}", status_code=204)
def delete_geschaeft(geschaeft_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    g = db.get(Geschaeft, geschaeft_id)
    if not g:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(g)
    db.commit()
