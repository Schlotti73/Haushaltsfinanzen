from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Kategorie
from app.schemas import KategorieCreate, KategorieFlach, KategorieMitKindern, KategorieOut, KategorieUpdate

router = APIRouter(prefix="/kategorien", tags=["kategorien"])


def _to_tree(kategorien: list[Kategorie]) -> list[KategorieMitKindern]:
    """Flache Liste → verschachtelter Baum (beliebige Tiefe).

    Verlinkt jeden Knoten an seinen Elternknoten; Ebene 3+ (z. B.
    Nebenkosten → einzelne Zähler/Verträge) wird dadurch korrekt genestet.
    Wir bauen den Baum aus KategorieOut-Dicts auf, um zu vermeiden,
    dass model_validate die ORM-Relationship 'kinder' vorlädt und
    Unterkategorien dadurch doppelt erscheinen.
    """
    by_id: dict[int, KategorieMitKindern] = {}
    for k in kategorien:
        # KategorieOut hat kein 'kinder'-Feld → keine ORM-Relationship wird geladen
        d = KategorieOut.model_validate(k).model_dump()
        by_id[k.id] = KategorieMitKindern.model_validate(d)
    roots: list[KategorieMitKindern] = []
    for k in by_id.values():
        if k.uebergeordnet_id and k.uebergeordnet_id in by_id:
            by_id[k.uebergeordnet_id].kinder.append(k)
        else:
            roots.append(k)
    return roots


@router.get("", response_model=List[KategorieMitKindern])
def list_kategorien(nur_aktiv: bool = True, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Kategorie)
    if nur_aktiv:
        q = q.filter(Kategorie.aktiv == True)
    return _to_tree(q.order_by(Kategorie.uebergeordnet_id.nullsfirst(), Kategorie.name).all())


@router.get("/flach", response_model=List[KategorieFlach])
def list_kategorien_flach(nur_aktiv: bool = True, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Flache Liste in Baum-Reihenfolge, mit Ebene und vollem Pfad.

    Bewusst in Python statt per SQL-Join: ein Join auf den Elternknoten kennt
    nur eine Ebene, dadurch landeten Kategorien der 3. Ebene (z. B.
    Nebenkosten > Musterweg 1 > Strom EG) unter dem Namen ihres
    Ebene-2-Elternknotens und standen zwischen fremden Zweigen.
    """
    q = db.query(Kategorie)
    if nur_aktiv:
        q = q.filter(Kategorie.aktiv == True)
    alle = q.all()

    vorhanden = {k.id for k in alle}
    kinder: dict[int | None, list[Kategorie]] = {}
    for k in alle:
        # Ist der Elternknoten herausgefiltert (inaktiv), zaehlt das Kind als Wurzel
        eltern = k.uebergeordnet_id if k.uebergeordnet_id in vorhanden else None
        kinder.setdefault(eltern, []).append(k)

    ergebnis: list[KategorieFlach] = []

    def sammle(eltern_id: int | None, ebene: int, eltern_pfad: str) -> None:
        for k in sorted(kinder.get(eltern_id, []), key=lambda x: x.name.lower()):
            pfad = f"{eltern_pfad} / {k.name}" if eltern_pfad else k.name
            d = KategorieOut.model_validate(k).model_dump()
            ergebnis.append(KategorieFlach.model_validate({**d, "ebene": ebene, "pfad": pfad}))
            sammle(k.id, ebene + 1, pfad)

    sammle(None, 0, "")
    return ergebnis


@router.get("/{kat_id}", response_model=KategorieOut)
def get_kategorie(kat_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    k = db.get(Kategorie, kat_id)
    if not k:
        raise HTTPException(404, "Nicht gefunden")
    return k


@router.post("", response_model=KategorieOut, status_code=201)
def create_kategorie(body: KategorieCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    k = Kategorie(**body.model_dump())
    db.add(k)
    db.commit()
    db.refresh(k)
    return k


@router.patch("/{kat_id}", response_model=KategorieOut)
def update_kategorie(kat_id: int, body: KategorieUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    k = db.get(Kategorie, kat_id)
    if not k:
        raise HTTPException(404, "Nicht gefunden")
    for field, val in body.model_dump(exclude_none=True).items():
        setattr(k, field, val)
    db.commit()
    db.refresh(k)
    return k


@router.delete("/{kat_id}", status_code=204)
def delete_kategorie(kat_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    k = db.get(Kategorie, kat_id)
    if not k:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(k)
    db.commit()
