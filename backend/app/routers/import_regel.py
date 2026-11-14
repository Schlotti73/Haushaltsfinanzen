"""
Import-Regeln (Phase 16): Pflege, Bestandslauf, Export/Import.

Die Regeln selbst werden in services/import_regel.py angewendet – hier liegen
nur CRUD und die beiden Massenoperationen.
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Buchung, Empfaenger, ImportRegel, Kategorie
from app.schemas import (
    BestandslaufAnfrage,
    BestandslaufErgebnis,
    BestandslaufZeile,
    ImportRegelCreate,
    ImportRegelOut,
    ImportRegelUpdate,
    RegelImportErgebnis,
)
from app.services.import_regel import RegelKatalog, normalisiere

router = APIRouter(prefix="/import-regeln", tags=["import-regeln"])

STUFEN = ("anbieter", "haendler")


def _out(regel: ImportRegel) -> ImportRegelOut:
    try:
        woerter = json.loads(regel.schluesselwoerter or "[]")
    except (ValueError, TypeError):
        woerter = []
    return ImportRegelOut(
        id=regel.id,
        name=regel.name,
        stufe=regel.stufe,
        schluesselwoerter=[str(w) for w in woerter],
        iban_muster=regel.iban_muster,
        empfaenger_id=regel.empfaenger_id,
        empfaenger_name=regel.empfaenger_obj.name if regel.empfaenger_obj else None,
        kategorie_id=regel.kategorie_id,
        notiz_text=regel.notiz_text,
        aktiv=regel.aktiv,
        notiz=regel.notiz,
    )


def _pruefe_stufe(stufe: str) -> None:
    if stufe not in STUFEN:
        raise HTTPException(400, f"Unbekannte Stufe „{stufe}“ (erlaubt: {', '.join(STUFEN)})")


def _pruefe_regel(stufe: str, schluesselwoerter: list[str], iban_muster: Optional[str]) -> None:
    """Eine Regel ohne greifendes Muster würde nie anschlagen – das ist ein Fehler,
    kein stiller Sonderfall."""
    hat_wort = any(len(normalisiere(w)) >= 3 for w in schluesselwoerter)
    if not hat_wort and not (stufe == "anbieter" and iban_muster):
        raise HTTPException(
            400,
            "Mindestens ein Schlüsselwort mit drei Zeichen angeben"
            + (" oder eine IBAN hinterlegen." if stufe == "anbieter" else "."),
        )


@router.get("", response_model=list[ImportRegelOut])
def liste(db: Session = Depends(get_db), _=Depends(get_current_user)):
    regeln = (
        db.query(ImportRegel)
        .options(selectinload(ImportRegel.empfaenger_obj))
        .order_by(ImportRegel.stufe, ImportRegel.name)
        .all()
    )
    return [_out(r) for r in regeln]


@router.post("", response_model=ImportRegelOut)
def anlegen(body: ImportRegelCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    _pruefe_stufe(body.stufe)
    _pruefe_regel(body.stufe, body.schluesselwoerter, body.iban_muster)
    regel = ImportRegel(
        name=body.name.strip(),
        stufe=body.stufe,
        schluesselwoerter=json.dumps([w.strip() for w in body.schluesselwoerter if w.strip()],
                                     ensure_ascii=False),
        iban_muster=(body.iban_muster or None),
        empfaenger_id=body.empfaenger_id,
        kategorie_id=body.kategorie_id,
        notiz_text=(body.notiz_text or None),
        aktiv=body.aktiv,
        notiz=body.notiz,
    )
    db.add(regel)
    db.commit()
    db.refresh(regel)
    return _out(regel)


@router.patch("/{regel_id}", response_model=ImportRegelOut)
def aendern(
    regel_id: int,
    body: ImportRegelUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    regel = db.get(ImportRegel, regel_id)
    if not regel:
        raise HTTPException(404, "Regel nicht gefunden")

    daten = body.model_dump(exclude_unset=True)
    if "stufe" in daten:
        _pruefe_stufe(daten["stufe"])
    stufe = daten.get("stufe", regel.stufe)
    if "schluesselwoerter" in daten or "iban_muster" in daten:
        try:
            bestand = json.loads(regel.schluesselwoerter or "[]")
        except (ValueError, TypeError):
            bestand = []
        woerter = daten.get("schluesselwoerter", bestand)
        _pruefe_regel(stufe, woerter, daten.get("iban_muster", regel.iban_muster))

    for feld, wert in daten.items():
        if feld == "schluesselwoerter":
            wert = json.dumps([w.strip() for w in wert if w.strip()], ensure_ascii=False)
        elif feld == "name" and isinstance(wert, str):
            wert = wert.strip()
        setattr(regel, feld, wert)

    db.commit()
    db.refresh(regel)
    return _out(regel)


@router.delete("/{regel_id}")
def loeschen(regel_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    regel = db.get(ImportRegel, regel_id)
    if not regel:
        raise HTTPException(404, "Regel nicht gefunden")
    db.delete(regel)
    db.commit()
    return {"ok": True}


# ── Bestandslauf ─────────────────────────────────────────────────────────────
@router.post("/bestandslauf", response_model=BestandslaufErgebnis)
def bestandslauf(
    body: BestandslaufAnfrage,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Wendet die Regeln auf bereits importierte Buchungen an.

    Ohne `anwenden` ist der Aufruf eine reine Vorschau – derselbe Ablauf wie
    beim PDF-Import selbst, denn ein zu breites Muster würde sonst hunderte
    Buchungen umschreiben, ohne dass jemand hinsieht. Ein Undo gibt es nicht.
    """
    katalog = RegelKatalog(db)
    buchungen = (
        db.query(Buchung)
        .filter(
            # Nur Importe: manuell erfasste Buchungen haben keinen Bankrohtext
            # und gehen die Regeln nichts an.
            Buchung.quelle == "import",
            Buchung.import_empfaenger.isnot(None),
        )
        .order_by(Buchung.datum.desc())
        .all()
    )

    zeilen: list[BestandslaufZeile] = []
    geaendert = 0
    for buch in buchungen:
        ergebnis = katalog.wende_an(
            buch.import_empfaenger, buch.import_verwendungszweck, buch.import_iban
        )
        if not ergebnis.hat_treffer:
            continue

        neu_empfaenger = buch.empfaenger
        neu_kategorie = buch.kategorie_id
        neu_notiz = buch.notiz
        neu_empfaenger_id = buch.empfaenger_id

        # Handkorrekturen bleiben stehen: der Empfänger wird nur ersetzt, wenn er
        # noch unverändert dem Bankrohtext entspricht.
        if ergebnis.empfaenger_name and (
            body.ueberschreiben
            or not buch.empfaenger
            or buch.empfaenger == buch.import_empfaenger
        ):
            neu_empfaenger = ergebnis.empfaenger_name
        if ergebnis.kategorie_id and (body.ueberschreiben or not buch.kategorie_id):
            neu_kategorie = ergebnis.kategorie_id
        if ergebnis.notiz and (body.ueberschreiben or not (buch.notiz or "").strip()):
            neu_notiz = ergebnis.notiz
        if ergebnis.empfaenger_id and (body.ueberschreiben or not buch.empfaenger_id):
            neu_empfaenger_id = ergebnis.empfaenger_id

        # Die Verknüpfung zählt hier mit: für Statistik und Abgleich ist sie
        # entscheidend, nicht der Text. Ohne sie in der Prüfung übersprang der
        # Lauf jede Buchung, bei der nur die fehlende `empfaenger_id` zu setzen
        # gewesen wäre – und genau die sind der Regelfall bei Buchungen, deren
        # Name bereits sauber war.
        if (
            neu_empfaenger == buch.empfaenger
            and neu_kategorie == buch.kategorie_id
            and neu_notiz == buch.notiz
            and neu_empfaenger_id == buch.empfaenger_id
        ):
            continue

        zeilen.append(BestandslaufZeile(
            buchung_id=buch.id,
            datum=buch.datum,
            betrag=buch.betrag,
            bank_empfaenger=buch.import_empfaenger,
            alt_empfaenger=buch.empfaenger,
            neu_empfaenger=neu_empfaenger,
            alt_kategorie_id=buch.kategorie_id,
            neu_kategorie_id=neu_kategorie,
            alt_notiz=buch.notiz,
            neu_notiz=neu_notiz,
            alt_empfaenger_id=buch.empfaenger_id,
            neu_empfaenger_id=neu_empfaenger_id,
            regel_hinweis=ergebnis.hinweis(),
        ))

        if body.anwenden:
            buch.empfaenger = neu_empfaenger
            buch.kategorie_id = neu_kategorie
            buch.notiz = neu_notiz
            buch.empfaenger_id = neu_empfaenger_id
            geaendert += 1

    if body.anwenden:
        db.commit()

    return BestandslaufErgebnis(
        geprueft=len(buchungen),
        betroffen=len(zeilen),
        geaendert=geaendert,
        zeilen=zeilen[:500],
    )


# ── Export / Import ──────────────────────────────────────────────────────────
@router.get("/export")
def export(db: Session = Depends(get_db), _=Depends(require_admin)):
    """Regeln als JSON, aufgelöst über Namen statt IDs.

    IDs bedeuten in jeder Datenbank etwas anderes; nur über Namen lässt sich ein
    Export auch in einer anderen Datenbank oder nach einem Restore einspielen.
    """
    regeln = (
        db.query(ImportRegel)
        .options(selectinload(ImportRegel.empfaenger_obj), selectinload(ImportRegel.kategorie))
        .order_by(ImportRegel.stufe, ImportRegel.name)
        .all()
    )
    return {
        "version": 1,
        "regeln": [
            {
                "name": r.name,
                "stufe": r.stufe,
                "schluesselwoerter": json.loads(r.schluesselwoerter or "[]"),
                "iban_muster": r.iban_muster,
                "empfaenger_name": r.empfaenger_obj.name if r.empfaenger_obj else None,
                "kategorie_name": r.kategorie.name if r.kategorie else None,
                "notiz_text": r.notiz_text,
                "aktiv": r.aktiv,
                "notiz": r.notiz,
            }
            for r in regeln
        ],
    }


@router.post("/import", response_model=RegelImportErgebnis)
def importieren(
    daten: dict,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    eintraege = daten.get("regeln")
    if not isinstance(eintraege, list):
        raise HTTPException(400, "Erwartet wird ein Objekt mit der Liste „regeln“")

    empfaenger_nach_name = {e.name.lower(): e.id for e in db.query(Empfaenger).all()}
    kategorie_nach_name: dict[str, int] = {}
    for k in db.query(Kategorie).all():
        kategorie_nach_name.setdefault(k.name.lower(), k.id)
    bestand = {(r.stufe, r.name.lower()): r for r in db.query(ImportRegel).all()}

    angelegt = aktualisiert = 0
    hinweise: list[str] = []

    for eintrag in eintraege:
        name = str(eintrag.get("name") or "").strip()
        stufe = str(eintrag.get("stufe") or "haendler")
        if not name or stufe not in STUFEN:
            hinweise.append(f"Übersprungen: ungültiger Eintrag „{name or '?'}“")
            continue

        woerter = [str(w).strip() for w in (eintrag.get("schluesselwoerter") or []) if str(w).strip()]

        # Unbekannte Empfänger/Kategorien werden bewusst nicht angelegt – ein
        # Import soll keine Stammdaten erfinden. Das Feld bleibt leer und wird
        # unten gemeldet.
        empf_name = eintrag.get("empfaenger_name")
        empfaenger_id = empfaenger_nach_name.get(str(empf_name).lower()) if empf_name else None
        if empf_name and not empfaenger_id:
            hinweise.append(f"„{name}“: Empfänger „{empf_name}“ nicht gefunden – Feld bleibt leer")

        kat_name = eintrag.get("kategorie_name")
        kategorie_id = kategorie_nach_name.get(str(kat_name).lower()) if kat_name else None
        if kat_name and not kategorie_id:
            hinweise.append(f"„{name}“: Kategorie „{kat_name}“ nicht gefunden – Feld bleibt leer")

        werte = {
            "schluesselwoerter": json.dumps(woerter, ensure_ascii=False),
            "iban_muster": eintrag.get("iban_muster") or None,
            "empfaenger_id": empfaenger_id,
            "kategorie_id": kategorie_id,
            "notiz_text": eintrag.get("notiz_text") or None,
            "aktiv": bool(eintrag.get("aktiv", True)),
            "notiz": eintrag.get("notiz") or None,
        }

        vorhanden = bestand.get((stufe, name.lower()))
        if vorhanden:
            for feld, wert in werte.items():
                setattr(vorhanden, feld, wert)
            aktualisiert += 1
        else:
            db.add(ImportRegel(name=name, stufe=stufe, **werte))
            angelegt += 1

    db.commit()
    return RegelImportErgebnis(angelegt=angelegt, aktualisiert=aktualisiert, hinweise=hinweise)


# ── Vorschläge aus dem Bestand ───────────────────────────────────────────────
@router.get("/vorschlaege")
def vorschlaege(
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Häufige Bankempfänger, für die es noch keine Regel gibt.

    Damit startest du nicht vor einer leeren Liste, ohne geseedete Regeln, die
    nie jemand geprüft hat.
    """
    katalog = RegelKatalog(db)
    zeilen = (
        db.query(Buchung.import_empfaenger)
        .filter(Buchung.quelle == "import", Buchung.import_empfaenger.isnot(None))
        .all()
    )

    haeufigkeit: dict[str, int] = {}
    beispiel: dict[str, str] = {}
    for (roh,) in zeilen:
        if not roh or katalog.wende_an(roh).hat_treffer:
            continue  # bereits von einer Regel abgedeckt
        # Die ersten beiden Wörter tragen den Anbieter-/Händlernamen; alles
        # danach ist Referenznummer und je Buchung verschieden.
        worte = normalisiere(roh).split()
        if not worte:
            continue
        schluessel = " ".join(worte[:2])
        haeufigkeit[schluessel] = haeufigkeit.get(schluessel, 0) + 1
        beispiel.setdefault(schluessel, roh)

    top = sorted(haeufigkeit.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    return [
        {"schluesselwort": schluessel, "anzahl": anzahl, "beispiel": beispiel[schluessel]}
        for schluessel, anzahl in top
    ]
