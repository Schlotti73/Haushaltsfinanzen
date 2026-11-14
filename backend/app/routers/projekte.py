from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Buchung, DarlehenRate, GeplanteAusgabe, Projekt
from app.schemas import (
    BuchungVerknuepfung,
    DarlehenRateOut,
    GeplanteAusgabeCreate,
    GeplanteAusgabeOut,
    GeplanteAusgabeUpdate,
    ProjektCreate,
    ProjektOut,
    ProjektUpdate,
)

router = APIRouter(prefix="/projekte", tags=["projekte"])


@router.get("", response_model=list[ProjektOut])
def list_projekte(nur_aktiv: bool = False, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Projekt)
    if nur_aktiv:
        q = q.filter(Projekt.aktiv == True)
    return q.order_by(Projekt.name).all()


@router.get("/{projekt_id}", response_model=ProjektOut)
def get_projekt(projekt_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    p = db.get(Projekt, projekt_id)
    if not p:
        raise HTTPException(404, "Nicht gefunden")
    return p


@router.get("/{projekt_id}/darlehen-raten", response_model=list[DarlehenRateOut])
def get_darlehen_raten(projekt_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return db.query(DarlehenRate).filter(DarlehenRate.projekt_id == projekt_id).order_by(DarlehenRate.datum).all()


@router.post("", response_model=ProjektOut, status_code=201)
def create_projekt(body: ProjektCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    p = Projekt(**body.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return p


@router.patch("/{projekt_id}", response_model=ProjektOut)
def update_projekt(projekt_id: int, body: ProjektUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    p = db.get(Projekt, projekt_id)
    if not p:
        raise HTTPException(404, "Nicht gefunden")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(p, field, val)
    db.commit()
    db.refresh(p)
    return p


@router.get("/{projekt_id}/budget-vs-ist")
def budget_vs_ist(projekt_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Ausgaben je Kategorie für ein Projekt vs. Projektbudget."""
    p = db.get(Projekt, projekt_id)
    if not p:
        raise HTTPException(404, "Nicht gefunden")

    sql = text("""
        SELECT
            COALESCE(k.name, 'Ohne Kategorie') AS kategorie,
            ROUND(SUM(b.betrag), 2)             AS ist_summe,
            COUNT(*)                             AS anzahl
        FROM buchungen b
        LEFT JOIN kategorien k ON b.kategorie_id = k.id
        WHERE b.projekt_id = :projekt_id AND b.status IN ('gebucht', 'geplant')
        GROUP BY b.kategorie_id
        ORDER BY ist_summe
    """)
    rows = db.execute(sql, {"projekt_id": projekt_id}).mappings().all()

    ist_gesamt = round(sum(r["ist_summe"] for r in rows), 2)
    return {
        "projekt": {"id": p.id, "name": p.name, "budget": p.budget, "typ": p.typ},
        "ist_gesamt": ist_gesamt,
        "budget": p.budget,
        "kategorien": [dict(r) for r in rows],
    }


# ── Geplante Ausgaben (Posten) ───────────────────────────────────────────────
def _get_projekt_or_404(projekt_id: int, db: Session) -> Projekt:
    p = db.get(Projekt, projekt_id)
    if not p:
        raise HTTPException(404, "Projekt nicht gefunden")
    return p


def _get_posten_or_404(projekt_id: int, ga_id: int, db: Session) -> GeplanteAusgabe:
    ga = db.get(GeplanteAusgabe, ga_id)
    if not ga or ga.projekt_id != projekt_id:
        raise HTTPException(404, "Geplante Ausgabe nicht gefunden")
    return ga


@router.get("/{projekt_id}/geplante-ausgaben", response_model=list[GeplanteAusgabeOut])
def list_geplante_ausgaben(projekt_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _get_projekt_or_404(projekt_id, db)
    return (
        db.query(GeplanteAusgabe)
        .filter(GeplanteAusgabe.projekt_id == projekt_id)
        .order_by(GeplanteAusgabe.sortierung, GeplanteAusgabe.id)
        .all()
    )


@router.post("/{projekt_id}/geplante-ausgaben", response_model=GeplanteAusgabeOut, status_code=201)
def create_geplante_ausgabe(
    projekt_id: int, body: GeplanteAusgabeCreate, db: Session = Depends(get_db), _=Depends(require_admin)
):
    _get_projekt_or_404(projekt_id, db)
    ga = GeplanteAusgabe(projekt_id=projekt_id, **body.model_dump())
    db.add(ga)
    db.commit()
    db.refresh(ga)
    return ga


@router.patch("/{projekt_id}/geplante-ausgaben/{ga_id}", response_model=GeplanteAusgabeOut)
def update_geplante_ausgabe(
    projekt_id: int, ga_id: int, body: GeplanteAusgabeUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    ga = _get_posten_or_404(projekt_id, ga_id, db)
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(ga, field, val)
    db.commit()
    db.refresh(ga)
    return ga


@router.delete("/{projekt_id}/geplante-ausgaben/{ga_id}", status_code=204)
def delete_geplante_ausgabe(
    projekt_id: int, ga_id: int, db: Session = Depends(get_db), _=Depends(require_admin)
):
    ga = _get_posten_or_404(projekt_id, ga_id, db)
    db.delete(ga)
    db.commit()


@router.post("/{projekt_id}/geplante-ausgaben/{ga_id}/verknuepfen", status_code=204)
def verknuepfe_buchungen(
    projekt_id: int, ga_id: int, body: BuchungVerknuepfung,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """Verknüpft die angegebenen Buchungen mit dem Posten und ordnet sie dem Projekt zu."""
    _get_posten_or_404(projekt_id, ga_id, db)
    if not body.buchung_ids:
        return
    buchungen = db.query(Buchung).filter(Buchung.id.in_(body.buchung_ids)).all()
    for b in buchungen:
        b.geplante_ausgabe_id = ga_id
        b.projekt_id = projekt_id
    db.commit()


@router.post("/{projekt_id}/geplante-ausgaben/{ga_id}/loesen", status_code=204)
def loese_buchungen(
    projekt_id: int, ga_id: int, body: BuchungVerknuepfung,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    """Löst die Verknüpfung der angegebenen Buchungen vom Posten (Projekt-Zuordnung bleibt)."""
    _get_posten_or_404(projekt_id, ga_id, db)
    if not body.buchung_ids:
        return
    buchungen = (
        db.query(Buchung)
        .filter(Buchung.id.in_(body.buchung_ids), Buchung.geplante_ausgabe_id == ga_id)
        .all()
    )
    for b in buchungen:
        b.geplante_ausgabe_id = None
    db.commit()


@router.get("/{projekt_id}/plan-vs-ist")
def plan_vs_ist(projekt_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Plan vs. Ist je geplantem Posten: geplant, ist (Summe verknüpfter Buchungen),
    Abweichung (Beträge, vorzeichenunabhängig: >0 = überschritten)."""
    p = _get_projekt_or_404(projekt_id, db)
    posten = (
        db.query(GeplanteAusgabe)
        .filter(GeplanteAusgabe.projekt_id == projekt_id)
        .order_by(GeplanteAusgabe.sortierung, GeplanteAusgabe.id)
        .all()
    )

    out = []
    geplant_gesamt = 0.0
    ist_gesamt = 0.0
    for ga in posten:
        buchungen = sorted(ga.buchungen, key=lambda b: b.datum)
        # Negate buchungen sum so it matches betrag convention (positive = Ausgabe)
        ist = -round(sum(b.betrag for b in buchungen), 2)
        geplant = ga.betrag or 0.0
        abweichung = round(ist - geplant, 2)
        geplant_gesamt += geplant
        ist_gesamt += ist
        out.append({
            "id": ga.id,
            "bezeichnung": ga.bezeichnung,
            "betrag": geplant,
            "notiz": ga.notiz,
            "kategorie_id": ga.kategorie_id,
            "erledigt": ga.erledigt,
            "sortierung": ga.sortierung,
            "darlehen_konto_id": ga.darlehen_konto_id,
            "ist": ist,
            "abweichung": abweichung,
            "anzahl_buchungen": len(buchungen),
            "buchungen": [
                {
                    "id": b.id,
                    "datum": b.datum,
                    "betrag": b.betrag,
                    "empfaenger": b.empfaenger,
                    "kategorie_id": b.kategorie_id,
                }
                for b in buchungen
            ],
        })

    return {
        "projekt": {"id": p.id, "name": p.name, "budget": p.budget, "typ": p.typ},
        "budget": p.budget,
        "geplant_gesamt": round(geplant_gesamt, 2),
        "ist_gesamt": round(ist_gesamt, 2),
        "posten": out,
    }


@router.delete("/{projekt_id}", status_code=204)
def delete_projekt(projekt_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    p = db.get(Projekt, projekt_id)
    if not p:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(p)
    db.commit()
