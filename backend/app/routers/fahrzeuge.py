"""Fahrzeuge als Kostenstelle.

Dasselbe Gerüst wie beim Gebäude, nur ohne Zähler-Tabelle: ein Fahrzeug hat
genau einen Zähler.

Gespeichert wird der **Kilometerstand**, nie die Fahrleistung. Die ist immer
die Differenz zweier Stände, und ein korrigierter Stand kann so nie zu einer
widersprüchlichen Fahrleistung führen. Stände kommen aus drei Quellen, und
alle drei sind nur Zeilen mit einem Stand: Tankungen, abgelesene Stände
(31.12. und zwischendurch) und erledigte Termine — ein Werkstattbesuch ist
eine Ablesung.

Die Kosten kommen aus den Buchungen, über die Kategorien am Fahrzeug. Es gibt
keine zweite Buchführung neben den Buchungen.

Gerechnet und nirgends gespeichert wird: Fahrleistung, Verbrauch, Kosten je
Kilometer, der nächste Termin und seine Prognose. Nichts davon bleibt richtig,
wenn man es speichert — nach der ersten Fahrt ist es veraltet.
"""

import shutil
from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.models import (
    Buchung, Fahrzeug, FahrzeugKostenkategorie, FahrzeugStand, FahrzeugTankung,
    FahrzeugTermin, FahrzeugTerminErledigung, Gebaeude, GebaeudeKostenkategorie,
    Kategorie, Vertrag, Zaehler,
)
from app.schemas import (
    FahrzeugErledigungCreate, FahrzeugErledigungOut, FahrzeugJahresreihe,
    FahrzeugKostenkategorieOut, FahrzeugCreate, FahrzeugOut, FahrzeugStandCreate,
    FahrzeugStandOut, FahrzeugTankungCreate, FahrzeugTankungOut, FahrzeugTankungUpdate,
    FahrzeugTerminCreate, FahrzeugTerminOut, FahrzeugTerminUpdate, FahrzeugUebersicht,
    FahrzeugUpdate, FahrzeugVertragZeile,
)

router = APIRouter(prefix="/fahrzeuge", tags=["fahrzeuge"])

# Vorlauf der Erinnerungen, wenn in den Einstellungen nichts steht.
VORLAUF_TAGE = 60
VORLAUF_KM = 2000

# Welche Einheit der Antrieb tankt. Der Plug-in-Hybrid tankt beides und
# entscheidet je Tankung.
_EINHEIT = {
    "benzin": "liter",
    "diesel": "liter",
    "hybrid": "liter",
    "elektro": "kwh",
    "plugin": "liter",
}


# ── Kleine Helfer ───────────────────────────────────────────────────────────
def _als_datum(wert: Optional[str]) -> Optional[date]:
    if not wert:
        return None
    try:
        return date.fromisoformat(wert[:10])
    except ValueError:
        return None


def _geladen(db: Session):
    return db.query(Fahrzeug).options(
        selectinload(Fahrzeug.tankungen),
        selectinload(Fahrzeug.staende),
        selectinload(Fahrzeug.kostenkategorien).selectinload(FahrzeugKostenkategorie.kategorie),
        selectinload(Fahrzeug.termine).selectinload(FahrzeugTermin.erledigungen),
        selectinload(Fahrzeug.vertraege),
        selectinload(Fahrzeug.konto),
    )


def _fahrzeug(db: Session, fahrzeug_id: int) -> Fahrzeug:
    f = _geladen(db).filter(Fahrzeug.id == fahrzeug_id).first()
    if not f:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
    return f


@dataclass(frozen=True)
class _Punkt:
    """Ein Kilometerstand mit Datum, egal woher er kommt."""

    datum: date
    km: int


def punkte(fahrzeug: Fahrzeug) -> List[_Punkt]:
    """Alle bekannten Kilometerstände, nach Datum und Stand sortiert.

    Tankung, Ablesung und erledigter Termin sind hier dasselbe: ein Stand zu
    einem Datum. Wer eine Auswertung nur auf die Tankungen stützt, verliert
    bei einem Fahrzeug ohne Tankungserfassung die ganze Historie.
    """
    gesammelt: dict[tuple[date, int], _Punkt] = {}

    def merken(datum: Optional[str], km: Optional[int]) -> None:
        d = _als_datum(datum)
        if d is None or km is None:
            return
        gesammelt[(d, int(km))] = _Punkt(d, int(km))

    for t in fahrzeug.tankungen:
        merken(t.datum, t.km)
    for s in fahrzeug.staende:
        merken(s.datum, s.km)
    for termin in fahrzeug.termine:
        for e in termin.erledigungen:
            merken(e.datum, e.km)

    return sorted(gesammelt.values(), key=lambda p: (p.datum, p.km))


def _letzte_je_jahr(reihe: List[_Punkt]) -> dict[int, _Punkt]:
    letzte: dict[int, _Punkt] = {}
    for p in reihe:
        letzte[p.datum.year] = p
    return letzte


def _erste_je_jahr(reihe: List[_Punkt]) -> dict[int, _Punkt]:
    erste: dict[int, _Punkt] = {}
    for p in reihe:
        erste.setdefault(p.datum.year, p)
    return erste


def fahrleistung_je_jahr(reihe: List[_Punkt]) -> dict[int, int]:
    """Gefahrene Kilometer je Jahr, als Differenz zum Vorjahresende.

    Fehlt der Stand zum 31.12., wird der letzte bekannte Stand des Jahres
    genommen — das Jahr ist dann zu kurz gerechnet, und genau darum mahnt das
    Dashboard den fehlenden Jahresstand an.

    Gibt es kein Vorjahr, aber mehrere Stände im Jahr selbst (das erste Jahr
    eines neu angelegten Fahrzeugs), gilt die Spanne innerhalb des Jahres.
    Sonst gibt es keine Zahl: aus einem einzigen Stand lässt sich keine
    Fahrleistung folgern.
    """
    letzte = _letzte_je_jahr(reihe)
    erste = _erste_je_jahr(reihe)
    aus: dict[int, int] = {}
    for jahr, ende in letzte.items():
        vorjahr = letzte.get(jahr - 1)
        if vorjahr:
            aus[jahr] = ende.km - vorjahr.km
        else:
            start = erste.get(jahr)
            if start and start.km != ende.km:
                aus[jahr] = ende.km - start.km
    return {j: k for j, k in aus.items() if k >= 0}


def km_pro_tag(reihe: List[_Punkt], heute: date) -> Optional[float]:
    """Durchschnitt der letzten zwölf Monate, hilfsweise der ganzen Historie.

    Grundlage der Termin-Prognose. Weniger als zwei Stände ergeben keinen
    Durchschnitt — dann gibt es auch keine Prognose, und das ist richtiger als
    eine erfundene.
    """
    if len(reihe) < 2:
        return None
    grenze = heute - relativedelta(months=12)
    fenster = [p for p in reihe if p.datum >= grenze]
    if len(fenster) < 2:
        fenster = reihe
    tage = (fenster[-1].datum - fenster[0].datum).days
    strecke = fenster[-1].km - fenster[0].km
    if tage <= 0 or strecke <= 0:
        return None
    return strecke / tage


# ── Verbrauch ───────────────────────────────────────────────────────────────
def _verbrauch_je_tankung(fahrzeug: Fahrzeug) -> tuple[dict[int, dict], dict[int, tuple[float, int]]]:
    """Verbrauch je Tankung und Mengen je Jahr.

    Gerechnet wird nur zwischen zwei **Volltankungen**: nur dann ist bekannt,
    wie viel auf die gefahrenen Kilometer wirklich hineingegangen ist. Eine
    Teilbetankung sammelt ihre Menge an und bekommt selbst keinen Wert.

    Liter und kWh laufen in getrennten Ketten — beim Plug-in-Hybrid sind das
    zwei Verbräuche auf dieselbe Strecke, und so werden sie auch angezeigt.

    Rückgabe: {tankung_id: {"gefahren", "verbrauch"}} und je Jahr und Einheit
    die Summe aus Menge und Kilometern für den Jahresverbrauch.
    """
    je_tankung: dict[int, dict] = {}
    je_jahr: dict[int, tuple[float, int]] = {}

    sortiert = sorted(fahrzeug.tankungen, key=lambda t: (t.datum or "", t.km))
    for einheit in ("liter", "kwh"):
        kette = [t for t in sortiert if t.einheit == einheit]
        letzte_voll: Optional[FahrzeugTankung] = None
        offene_menge = 0.0
        for i, t in enumerate(kette):
            vorige = kette[i - 1] if i > 0 else None
            gefahren = (t.km - vorige.km) if vorige and t.km > vorige.km else None
            je_tankung[t.id] = {"gefahren": gefahren, "verbrauch": None}

            offene_menge += t.menge or 0.0
            if not t.voll:
                continue
            if letzte_voll and t.km > letzte_voll.km:
                strecke = t.km - letzte_voll.km
                je_tankung[t.id]["verbrauch"] = round(offene_menge / strecke * 100, 2)
                jahr = (_als_datum(t.datum) or date.today()).year
                menge_vor, km_vor = je_jahr.get(jahr, (0.0, 0))
                je_jahr[jahr] = (menge_vor + offene_menge, km_vor + strecke)
            letzte_voll = t
            offene_menge = 0.0

    return je_tankung, je_jahr


# ── Kosten ──────────────────────────────────────────────────────────────────
def _kosten_je_jahr(db: Session, kategorie_ids) -> dict[int, float]:
    """Kosten dieser Kategorien je Jahr, aus den gebuchten Buchungen.

    Wie beim Gebäude wird das Vorzeichen gedreht, nicht entfernt: Ausgaben
    stehen negativ in den Buchungen und sind hier positive Kosten, eine
    Erstattung bleibt eine negative Kostenposition und mindert das Jahr. Ein
    abs() hier machte aus einer Erstattung eine Ausgabe.

    Nur `status='gebucht'`: geplante Buchungen gehören nicht in eine
    Kostenrechnung.
    """
    ids = [k for k in kategorie_ids if k]
    if not ids:
        return {}
    rows = (
        db.query(func.substr(Buchung.datum, 1, 4), func.sum(Buchung.betrag))
        .filter(Buchung.kategorie_id.in_(ids), Buchung.status == "gebucht")
        .group_by(func.substr(Buchung.datum, 1, 4))
        .all()
    )
    return {int(j): round(-(s or 0.0), 2) for j, s in rows if j}


def _kategorie_frei(db: Session, kategorie_id: int, fahrzeug_id: int) -> None:
    """Eine Kategorie gehört an genau eine Kostenstelle.

    „Kraftstoff" an zwei Fahrzeugen zählte jede Tankstellenbuchung zweimal und
    verdürbe beide Kosten je Kilometer. Geprüft wird gegen die anderen
    Fahrzeuge, gegen die Gebäude und gegen die Zähler — dieselbe Gegenprobe
    wie zwischen Zähler und Gebäude.
    """
    anderes = (
        db.query(Fahrzeug)
        .join(FahrzeugKostenkategorie, FahrzeugKostenkategorie.fahrzeug_id == Fahrzeug.id)
        .filter(
            FahrzeugKostenkategorie.kategorie_id == kategorie_id,
            Fahrzeug.id != fahrzeug_id,
        )
        .first()
    )
    if anderes:
        raise HTTPException(
            400,
            f"Diese Kategorie gehört schon zum Fahrzeug „{anderes.name}“ und ist dort "
            "in den Kosten enthalten.",
        )

    gebaeude = (
        db.query(Gebaeude)
        .join(GebaeudeKostenkategorie, GebaeudeKostenkategorie.gebaeude_id == Gebaeude.id)
        .filter(GebaeudeKostenkategorie.kategorie_id == kategorie_id)
        .first()
    )
    if gebaeude:
        raise HTTPException(
            400,
            f"Diese Kategorie gehört schon zum Gebäude „{gebaeude.name}“ und ist dort "
            "in den Nebenkosten enthalten.",
        )

    zaehler = db.query(Zaehler).filter(Zaehler.kategorie_id == kategorie_id).first()
    if zaehler:
        raise HTTPException(
            400,
            f"Diese Kategorie hängt am Zähler „{zaehler.name}“ und ist dort in den "
            "Verbrauchskosten enthalten.",
        )


# ── Termine ─────────────────────────────────────────────────────────────────
def termin_lage(
    termin: FahrzeugTermin,
    stand: Optional[int],
    schnitt: Optional[float],
    heute: date,
) -> dict:
    """Wann dieser Termin fällig ist — gerechnet, nicht gespeichert.

    Das Datumsintervall zählt ab der letzten Durchführung; ohne eine gibt es
    keinen Anker und damit kein Datum. Das Kilometer-Intervall zählt ab dem
    Stand der letzten Durchführung, und ohne eine ab 0 — „Zahnriemen alle
    180.000 km" ist dann der Stand 180.000.

    Aus dem Kilometerrest und dem Tagesdurchschnitt wird ein voraussichtlicher
    Monat. Fährt man weniger, rutscht er beim nächsten Abruf von selbst nach
    hinten.
    """
    letzte = None
    for e in termin.erledigungen:
        d = _als_datum(e.datum)
        if d and (letzte is None or d > _als_datum(letzte.datum)):
            letzte = e

    lage = {
        "zuletzt_am": letzte.datum if letzte else None,
        "zuletzt_km": letzte.km if letzte else None,
        "faellig_am": None,
        "faellig_km": None,
        "rest_tage": None,
        "rest_km": None,
        "prognose_monat": None,
        "ueberfaellig": False,
    }

    if termin.intervall_monate and letzte:
        anker = _als_datum(letzte.datum)
        if anker:
            faellig = anker + relativedelta(months=termin.intervall_monate)
            lage["faellig_am"] = faellig.isoformat()
            lage["rest_tage"] = (faellig - heute).days

    if termin.intervall_km:
        basis = letzte.km if (letzte and letzte.km is not None) else 0
        faellig_km = basis + termin.intervall_km
        lage["faellig_km"] = faellig_km
        if stand is not None:
            rest = faellig_km - stand
            lage["rest_km"] = rest
            if schnitt and schnitt > 0:
                ziel = heute + relativedelta(days=int(max(rest, 0) / schnitt))
                lage["prognose_monat"] = ziel.strftime("%Y-%m")

    lage["ueberfaellig"] = bool(
        (lage["rest_tage"] is not None and lage["rest_tage"] < 0)
        or (lage["rest_km"] is not None and lage["rest_km"] < 0)
    )
    return lage


# ── Zusammenstellung für die Liste ──────────────────────────────────────────
def _hinaus(db: Session, fahrzeuge: List[Fahrzeug], heute: Optional[date] = None) -> List[FahrzeugOut]:
    heute = heute or date.today()
    aus: List[FahrzeugOut] = []

    dok_anzahl = _dokument_anzahl(db, [f.id for f in fahrzeuge])

    for f in fahrzeuge:
        reihe = punkte(f)
        leistung = fahrleistung_je_jahr(reihe)
        kosten = _kosten_je_jahr(db, [k.kategorie_id for k in f.kostenkategorien])
        _, mengen = _verbrauch_je_tankung(f)
        schnitt = km_pro_tag(reihe, heute)

        jahr = heute.year
        fahrleistung = leistung.get(jahr)
        kosten_jahr = kosten.get(jahr, 0.0)
        menge, strecke = mengen.get(jahr, (0.0, 0))

        # Nächster Termin: der mit dem kleinsten Rest, überfällige zuerst.
        naechster = None
        for t in f.termine:
            if not t.aktiv:
                continue
            lage = termin_lage(t, reihe[-1].km if reihe else None, schnitt, heute)
            reste = [r for r in (lage["rest_tage"], lage["rest_km"]) if r is not None]
            if not reste:
                continue
            kennzahl = min(reste)
            if naechster is None or kennzahl < naechster[0]:
                naechster = (kennzahl, t, lage)

        aus.append(FahrzeugOut(
            **{sp: getattr(f, sp) for sp in (
                "id", "name", "kennzeichen", "fahrgestellnummer", "hersteller_modell",
                "antrieb", "erstzulassung", "konto_id", "tankungen_erfassen", "notiz", "aktiv",
            )},
            stand_km=reihe[-1].km if reihe else None,
            stand_datum=reihe[-1].datum.isoformat() if reihe else None,
            fahrleistung_jahr=fahrleistung,
            kosten_jahr=kosten_jahr,
            je_km=round(kosten_jahr / fahrleistung, 4) if fahrleistung and kosten_jahr else None,
            verbrauch=round(menge / strecke * 100, 2) if strecke else None,
            verbrauch_einheit=_EINHEIT.get(f.antrieb) if strecke else None,
            naechster_termin=(
                naechster[2]["faellig_am"] or naechster[2]["prognose_monat"]
            ) if naechster else None,
            naechster_termin_name=naechster[1].name if naechster else None,
            konto_name=f.konto.name if f.konto else None,
            dokumente_anzahl=dok_anzahl.get(f.id, 0),
        ))
    return aus


def _dokument_anzahl(db: Session, fahrzeug_ids: List[int]) -> dict[int, int]:
    if not fahrzeug_ids:
        return {}
    from app.models import Beleg
    rows = (
        db.query(Beleg.fahrzeug_id, func.count(Beleg.id))
        .filter(Beleg.fahrzeug_id.in_(fahrzeug_ids))
        .group_by(Beleg.fahrzeug_id)
        .all()
    )
    return {fid: anzahl for fid, anzahl in rows}


# ── Fahrzeuge ───────────────────────────────────────────────────────────────
@router.get("", response_model=List[FahrzeugOut])
def list_fahrzeuge(
    nur_aktiv: bool = Query(True),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = _geladen(db)
    if nur_aktiv:
        q = q.filter(Fahrzeug.aktiv.is_(True))
    return _hinaus(db, q.order_by(Fahrzeug.name).all())


@router.get("/{fahrzeug_id}", response_model=FahrzeugOut)
def get_fahrzeug(fahrzeug_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _hinaus(db, [_fahrzeug(db, fahrzeug_id)])[0]


@router.post("", response_model=FahrzeugOut, status_code=201)
def create_fahrzeug(
    daten: FahrzeugCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    felder = daten.model_dump(exclude={"stand_km", "stand_datum"})
    f = Fahrzeug(**felder)
    db.add(f)
    db.flush()

    # Der Anfangsstand ist ein Stand wie jeder andere, nur eben der erste.
    if daten.stand_km is not None:
        datum = daten.stand_datum or date.today().isoformat()
        db.add(FahrzeugStand(
            fahrzeug_id=f.id,
            datum=datum,
            jahr=(_als_datum(datum) or date.today()).year,
            km=daten.stand_km,
            art="zwischen",
            notiz="Anfangsstand",
        ))

    db.commit()
    return _hinaus(db, [_fahrzeug(db, f.id)])[0]


@router.patch("/{fahrzeug_id}", response_model=FahrzeugOut)
def update_fahrzeug(
    fahrzeug_id: int,
    daten: FahrzeugUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    f = _fahrzeug(db, fahrzeug_id)
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(f, feld, wert)
    db.commit()
    return _hinaus(db, [_fahrzeug(db, fahrzeug_id)])[0]


@router.delete("/{fahrzeug_id}", status_code=204)
def delete_fahrzeug(fahrzeug_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Löscht das Fahrzeug mit Ständen, Tankungen, Terminen und Dokumenten.

    Buchungen und Verträge bleiben: sie gehören nicht dem Fahrzeug, es war nur
    ihre Kostenstelle. Die Verträge verlieren ihre `fahrzeug_id` über
    ON DELETE SET NULL, die Dateien räumt diese Funktion selbst ab — die
    Kaskade kennt nur die Datenbankzeilen.
    """
    f = _fahrzeug(db, fahrzeug_id)
    db.delete(f)
    db.commit()
    shutil.rmtree(settings.belege_dir / f"fahrzeug-{fahrzeug_id}", ignore_errors=True)
    return None


# ── Kostenkategorien ────────────────────────────────────────────────────────
@router.get("/{fahrzeug_id}/kostenkategorien", response_model=List[FahrzeugKostenkategorieOut])
def list_kostenkategorien(
    fahrzeug_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    f = _fahrzeug(db, fahrzeug_id)
    return [
        FahrzeugKostenkategorieOut(
            id=k.id,
            fahrzeug_id=k.fahrzeug_id,
            kategorie_id=k.kategorie_id,
            sortierung=k.sortierung,
            kategorie_name=k.kategorie.name if k.kategorie else None,
        )
        for k in sorted(f.kostenkategorien, key=lambda k: (k.sortierung, k.id))
    ]


@router.post("/{fahrzeug_id}/kostenkategorien", response_model=FahrzeugKostenkategorieOut, status_code=201)
def add_kostenkategorie(
    fahrzeug_id: int,
    kategorie_id: int = Query(...),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    _fahrzeug(db, fahrzeug_id)
    kategorie = db.get(Kategorie, kategorie_id)
    if not kategorie:
        raise HTTPException(404, "Kategorie nicht gefunden")

    vorhanden = (
        db.query(FahrzeugKostenkategorie)
        .filter(
            FahrzeugKostenkategorie.fahrzeug_id == fahrzeug_id,
            FahrzeugKostenkategorie.kategorie_id == kategorie_id,
        )
        .first()
    )
    if vorhanden:
        return FahrzeugKostenkategorieOut(
            id=vorhanden.id,
            fahrzeug_id=vorhanden.fahrzeug_id,
            kategorie_id=vorhanden.kategorie_id,
            sortierung=vorhanden.sortierung,
            kategorie_name=kategorie.name,
        )

    _kategorie_frei(db, kategorie_id, fahrzeug_id)
    k = FahrzeugKostenkategorie(fahrzeug_id=fahrzeug_id, kategorie_id=kategorie_id)
    db.add(k)
    db.commit()
    db.refresh(k)
    return FahrzeugKostenkategorieOut(
        id=k.id,
        fahrzeug_id=k.fahrzeug_id,
        kategorie_id=k.kategorie_id,
        sortierung=k.sortierung,
        kategorie_name=kategorie.name,
    )


@router.delete("/kostenkategorien/{zuordnung_id}", status_code=204)
def delete_kostenkategorie(
    zuordnung_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    k = db.get(FahrzeugKostenkategorie, zuordnung_id)
    if not k:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(k)
    db.commit()
    return None


# ── Kilometerstände ─────────────────────────────────────────────────────────
@router.get("/{fahrzeug_id}/staende", response_model=List[FahrzeugStandOut])
def list_staende(fahrzeug_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    f = _fahrzeug(db, fahrzeug_id)
    return sorted(f.staende, key=lambda s: (s.datum, s.km), reverse=True)


@router.post("/{fahrzeug_id}/staende", response_model=FahrzeugStandOut, status_code=201)
def create_stand(
    fahrzeug_id: int,
    daten: FahrzeugStandCreate,
    db: Session = Depends(get_db),
    # Ablesen ist Alltagsarbeit, Stammdatenpflege nicht - wie beim Zähler.
    _=Depends(get_current_user),
):
    _fahrzeug(db, fahrzeug_id)
    jahr = daten.jahr or (_als_datum(daten.datum) or date.today()).year

    if daten.art == "jahr":
        schon_da = (
            db.query(FahrzeugStand)
            .filter(
                FahrzeugStand.fahrzeug_id == fahrzeug_id,
                FahrzeugStand.jahr == jahr,
                FahrzeugStand.art == "jahr",
            )
            .first()
        )
        if schon_da:
            raise HTTPException(
                409,
                f"Für {jahr} gibt es schon einen Jahresstand ({schon_da.km} km). "
                "Pro Jahr genau einer — ändere oder lösche ihn.",
            )

    s = FahrzeugStand(fahrzeug_id=fahrzeug_id, jahr=jahr, **daten.model_dump(exclude={"jahr"}))
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


@router.delete("/staende/{stand_id}", status_code=204)
def delete_stand(stand_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    s = db.get(FahrzeugStand, stand_id)
    if not s:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(s)
    db.commit()
    return None


# ── Tankungen ───────────────────────────────────────────────────────────────
@router.get("/{fahrzeug_id}/tankungen", response_model=List[FahrzeugTankungOut])
def list_tankungen(fahrzeug_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    f = _fahrzeug(db, fahrzeug_id)
    gerechnet, _mengen = _verbrauch_je_tankung(f)

    aus: List[FahrzeugTankungOut] = []
    for t in sorted(f.tankungen, key=lambda t: (t.datum, t.km), reverse=True):
        werte = gerechnet.get(t.id, {})
        # Alte Zeilen koennen noch negativ sein, neue normiert das Schema.
        betrag = abs(t.betrag) if t.betrag is not None else (
            abs(t.buchung.betrag) if t.buchung else None
        )
        aus.append(FahrzeugTankungOut(
            id=t.id, fahrzeug_id=t.fahrzeug_id, datum=t.datum, km=t.km, menge=t.menge,
            einheit=t.einheit, voll=t.voll, betrag=betrag, buchung_id=t.buchung_id,
            notiz=t.notiz,
            gefahren=werte.get("gefahren"),
            verbrauch=werte.get("verbrauch"),
            preis_je_einheit=round(betrag / t.menge, 3) if betrag and t.menge else None,
            buchung_empfaenger=t.buchung.empfaenger if t.buchung else None,
        ))
    return aus


@router.post("/{fahrzeug_id}/tankungen", response_model=FahrzeugTankungOut, status_code=201)
def create_tankung(
    fahrzeug_id: int,
    daten: FahrzeugTankungCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    f = _fahrzeug(db, fahrzeug_id)
    if not f.tankungen_erfassen:
        raise HTTPException(
            400,
            "Für dieses Fahrzeug sind Tankungen abgeschaltet. Erst in den Stammdaten "
            "einschalten.",
        )
    t = FahrzeugTankung(fahrzeug_id=fahrzeug_id, **daten.model_dump())
    db.add(t)
    db.commit()
    db.refresh(t)
    return next(x for x in list_tankungen(fahrzeug_id, db) if x.id == t.id)


@router.patch("/tankungen/{tankung_id}", response_model=FahrzeugTankungOut)
def update_tankung(
    tankung_id: int,
    daten: FahrzeugTankungUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    t = db.get(FahrzeugTankung, tankung_id)
    if not t:
        raise HTTPException(404, "Nicht gefunden")
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(t, feld, wert)
    db.commit()
    fahrzeug_id = t.fahrzeug_id
    return next(x for x in list_tankungen(fahrzeug_id, db) if x.id == tankung_id)


@router.delete("/tankungen/{tankung_id}", status_code=204)
def delete_tankung(tankung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    t = db.get(FahrzeugTankung, tankung_id)
    if not t:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(t)
    db.commit()
    return None


@router.get("/{fahrzeug_id}/kraftstoff-offen")
def kraftstoff_offen(
    fahrzeug_id: int,
    monate: int = 12,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Tankstellen-Buchungen ohne erfasste Tankung.

    Welche Kategorie „Kraftstoff" ist, steht nirgends — es ergibt sich aus den
    Buchungen, die an den Tankungen dieses Fahrzeugs hängen. Ohne eine einzige
    verknüpfte Tankung gibt es darum auch keine Liste; das ist eine Hilfe beim
    Nachtragen, keine Instanz.
    """
    f = _fahrzeug(db, fahrzeug_id)
    verknuepft = {t.buchung_id for t in f.tankungen if t.buchung_id}
    if not verknuepft:
        return []

    eigene = {k.kategorie_id for k in f.kostenkategorien}
    kraftstoff_kategorien = {
        b.kategorie_id
        for b in db.query(Buchung).filter(Buchung.id.in_(verknuepft)).all()
        if b.kategorie_id and b.kategorie_id in eigene
    }
    if not kraftstoff_kategorien:
        return []

    ab = (date.today() - relativedelta(months=max(monate, 1))).isoformat()
    offen = (
        db.query(Buchung)
        .filter(
            Buchung.kategorie_id.in_(kraftstoff_kategorien),
            Buchung.status == "gebucht",
            Buchung.datum >= ab,
            ~Buchung.id.in_(verknuepft),
        )
        .order_by(Buchung.datum.desc())
        .all()
    )
    return [
        {
            "buchung_id": b.id,
            "datum": b.datum,
            "betrag": b.betrag,
            "empfaenger": b.empfaenger,
            "verwendungszweck": b.verwendungszweck or b.import_verwendungszweck,
        }
        for b in offen
    ]


# ── Termine ─────────────────────────────────────────────────────────────────
def _termin_hinaus(
    termin: FahrzeugTermin,
    stand: Optional[int],
    schnitt: Optional[float],
    heute: date,
) -> FahrzeugTerminOut:
    lage = termin_lage(termin, stand, schnitt, heute)
    return FahrzeugTerminOut(
        id=termin.id,
        fahrzeug_id=termin.fahrzeug_id,
        name=termin.name,
        intervall_monate=termin.intervall_monate,
        intervall_km=termin.intervall_km,
        notiz=termin.notiz,
        aktiv=termin.aktiv,
        erledigungen=[
            FahrzeugErledigungOut(
                id=e.id, termin_id=e.termin_id, datum=e.datum, km=e.km,
                buchung_id=e.buchung_id, notiz=e.notiz, termin_name=termin.name,
                kosten=abs(e.buchung.betrag) if e.buchung else None,
            )
            for e in sorted(termin.erledigungen, key=lambda e: e.datum, reverse=True)
        ],
        **lage,
    )


@router.get("/{fahrzeug_id}/termine", response_model=List[FahrzeugTerminOut])
def list_termine(fahrzeug_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    f = _fahrzeug(db, fahrzeug_id)
    heute = date.today()
    reihe = punkte(f)
    stand = reihe[-1].km if reihe else None
    schnitt = km_pro_tag(reihe, heute)
    termine = [_termin_hinaus(t, stand, schnitt, heute) for t in f.termine]
    # Überfällige zuerst, dann nach dem kleineren Rest.
    def schluessel(t: FahrzeugTerminOut):
        reste = [r for r in (t.rest_tage, t.rest_km) if r is not None]
        return (0 if t.ueberfaellig else 1, min(reste) if reste else 10 ** 9, t.name)
    return sorted(termine, key=schluessel)


@router.post("/{fahrzeug_id}/termine", response_model=FahrzeugTerminOut, status_code=201)
def create_termin(
    fahrzeug_id: int,
    daten: FahrzeugTerminCreate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    _fahrzeug(db, fahrzeug_id)
    felder = daten.model_dump(exclude={"zuletzt_am", "zuletzt_km"})
    t = FahrzeugTermin(fahrzeug_id=fahrzeug_id, **felder)
    db.add(t)
    db.flush()

    # „Zuletzt" bei der Anlage ist eine Erledigung, keine Spalte: sonst stünde
    # dieselbe Angabe an zwei Stellen und wüchse auseinander.
    if daten.zuletzt_am:
        db.add(FahrzeugTerminErledigung(
            termin_id=t.id, datum=daten.zuletzt_am, km=daten.zuletzt_km,
        ))

    db.commit()
    return next(x for x in list_termine(fahrzeug_id, db) if x.id == t.id)


@router.patch("/termine/{termin_id}", response_model=FahrzeugTerminOut)
def update_termin(
    termin_id: int,
    daten: FahrzeugTerminUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    t = db.get(FahrzeugTermin, termin_id)
    if not t:
        raise HTTPException(404, "Nicht gefunden")
    for feld, wert in daten.model_dump(exclude_unset=True).items():
        setattr(t, feld, wert)
    db.commit()
    return next(x for x in list_termine(t.fahrzeug_id, db) if x.id == termin_id)


@router.delete("/termine/{termin_id}", status_code=204)
def delete_termin(termin_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    t = db.get(FahrzeugTermin, termin_id)
    if not t:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(t)
    db.commit()
    return None


@router.post("/termine/{termin_id}/erledigt", response_model=FahrzeugTerminOut, status_code=201)
def erledigt(
    termin_id: int,
    daten: FahrzeugErledigungCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Trägt eine Durchführung ein; der nächste Termin folgt aus dem Intervall.

    Der Kilometerstand zählt gleich als Stand mit — ein Werkstattbesuch ist
    eine Ablesung, und zwei Eingaben für dieselbe Zahl wären eine zu viel.
    """
    t = db.get(FahrzeugTermin, termin_id)
    if not t:
        raise HTTPException(404, "Termin nicht gefunden")
    db.add(FahrzeugTerminErledigung(termin_id=termin_id, **daten.model_dump()))
    db.commit()
    return next(x for x in list_termine(t.fahrzeug_id, db) if x.id == termin_id)


@router.delete("/erledigungen/{erledigung_id}", status_code=204)
def delete_erledigung(
    erledigung_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    e = db.get(FahrzeugTerminErledigung, erledigung_id)
    if not e:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(e)
    db.commit()
    return None


# ── Jahresübersicht ─────────────────────────────────────────────────────────
@router.get("/{fahrzeug_id}/uebersicht", response_model=FahrzeugUebersicht)
def uebersicht(fahrzeug_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    f = _fahrzeug(db, fahrzeug_id)
    heute = date.today()

    reihe = punkte(f)
    leistung = fahrleistung_je_jahr(reihe)
    _gerechnet, mengen = _verbrauch_je_tankung(f)

    je_kategorie: dict[int, dict[int, float]] = {}
    for k in sorted(f.kostenkategorien, key=lambda k: (k.sortierung, k.id)):
        je_kategorie[k.kategorie_id] = _kosten_je_jahr(db, [k.kategorie_id])

    # Die Jahre sind die Vereinigung aus Kosten- und Ablesejahren: eine
    # Reparaturrechnung im Jahr ohne Stand ist eine echte Kostenposition.
    jahre = set(leistung) | set(mengen)
    for werte in je_kategorie.values():
        jahre |= set(werte)
    jahre_sortiert = sorted(jahre)

    kostenarten = [
        FahrzeugJahresreihe(
            name=k.kategorie.name if k.kategorie else f"Kategorie {k.kategorie_id}",
            kategorie_id=k.kategorie_id,
            betraege=[je_kategorie[k.kategorie_id].get(j, 0.0) for j in jahre_sortiert],
        )
        for k in sorted(f.kostenkategorien, key=lambda k: (k.sortierung, k.id))
    ]
    summe = [round(sum(r.betraege[i] for r in kostenarten), 2) for i in range(len(jahre_sortiert))]
    fahrleistung = [leistung.get(j) for j in jahre_sortiert]
    je_km = [
        round(summe[i] / fahrleistung[i], 4) if fahrleistung[i] and summe[i] else None
        for i in range(len(jahre_sortiert))
    ]
    verbrauch = []
    for j in jahre_sortiert:
        menge, strecke = mengen.get(j, (0.0, 0))
        verbrauch.append(round(menge / strecke * 100, 2) if strecke else None)

    from app.routers.vertraege import kuendigungstermin, _ratensumme_jahr
    vertraege = [
        FahrzeugVertragZeile(
            vertrag_id=v.id,
            name=v.name,
            anbieter=v.anbieter,
            soll_jahr=_ratensumme_jahr(v),
            kuendigen_bis=(lambda d: d.isoformat() if d else None)(kuendigungstermin(v, heute)),
            status="gekuendigt" if v.gekuendigt_am else "laufend",
        )
        for v in sorted(f.vertraege, key=lambda v: v.name)
    ]

    offen = kraftstoff_offen(fahrzeug_id, 12, db) if f.tankungen_erfassen else []
    kraftstoff_tankungen = None
    kraftstoff_buchungen = None
    if f.tankungen_erfassen:
        jahr = heute.year
        betraege = [
            (t.betrag if t.betrag is not None else (abs(t.buchung.betrag) if t.buchung else None))
            for t in f.tankungen
            if (_als_datum(t.datum) or heute).year == jahr
        ]
        kraftstoff_tankungen = round(sum(b for b in betraege if b), 2)
        # Nur wenn mindestens eine Tankung an einer Buchung haengt, ist
        # bekannt, welche Kategorie der Kraftstoff ist. Sonst bleibt die Zahl
        # offen - gleich hohe Zahlen wuerden sonst eine Uebereinstimmung
        # behaupten, die keine ist.
        if any(t.buchung_id for t in f.tankungen):
            kraftstoff_buchungen = round(
                kraftstoff_tankungen + sum(abs(o["betrag"]) for o in offen
                                           if (o["datum"] or "")[:4] == str(jahr)),
                2,
            )

    return FahrzeugUebersicht(
        jahre=jahre_sortiert,
        kostenarten=kostenarten,
        summe=summe,
        fahrleistung=fahrleistung,
        je_km=je_km,
        verbrauch=verbrauch,
        verbrauch_einheit=_EINHEIT.get(f.antrieb),
        vertraege=vertraege,
        kraftstoff_buchungen=kraftstoff_buchungen,
        kraftstoff_tankungen=kraftstoff_tankungen,
        kraftstoff_offen_anzahl=len(offen),
    )


# ── Für die Dashboard-Erinnerungen ──────────────────────────────────────────
def sammle_termine(
    db: Session,
    heute: date,
    vorlauf_tage: int = VORLAUF_TAGE,
    vorlauf_km: int = VORLAUF_KM,
) -> List[tuple[Fahrzeug, FahrzeugTermin, dict]]:
    """Termine, die näher rücken als der Vorlauf — gerechnet, nichts gespeichert.

    Wird von `routers/erinnerungen.py` benutzt. Der Hinweis verschwindet von
    selbst, sobald der Termin eingetragen ist oder sich der Durchschnitt
    ändert, weil weniger gefahren wird.
    """
    treffer: List[tuple[Fahrzeug, FahrzeugTermin, dict]] = []
    fahrzeuge = _geladen(db).filter(Fahrzeug.aktiv.is_(True)).all()
    for f in fahrzeuge:
        reihe = punkte(f)
        stand = reihe[-1].km if reihe else None
        schnitt = km_pro_tag(reihe, heute)
        for t in f.termine:
            if not t.aktiv:
                continue
            lage = termin_lage(t, stand, schnitt, heute)
            nah = (
                (lage["rest_tage"] is not None and lage["rest_tage"] <= vorlauf_tage)
                or (lage["rest_km"] is not None and lage["rest_km"] <= vorlauf_km)
            )
            if nah:
                treffer.append((f, t, lage))

    def schluessel(eintrag):
        _f, _t, lage = eintrag
        reste = [r for r in (lage["rest_tage"], lage["rest_km"]) if r is not None]
        return min(reste) if reste else 10 ** 9

    treffer.sort(key=schluessel)
    return treffer


def sammle_offene_staende(db: Session, heute: date) -> List[tuple[Fahrzeug, List[int]]]:
    """Fahrzeuge, deren Jahresfahrleistung am Jahresende abbricht.

    Fällig ist bis zum **Vorjahr**, wie bei den Jahresablesungen am Zähler.
    Gemahnt wird aber nicht der fehlende Eintrag mit `art='jahr'`, sondern die
    Lücke, die er hinterlässt: gerechnet wird mit dem letzten Stand des
    Jahres, woher er auch kommt. Liegt der schon im Dezember, fehlt nichts
    Nennenswertes — eine Tankung am 28.12. ist so gut wie eine Ablesung am
    31.12., und ein Hinweis darauf wäre nur Lärm.

    Ein Fahrzeug ohne jeden Stand ergibt keinen Hinweis — daraus lässt sich
    nichts folgern.
    """
    aus: List[tuple[Fahrzeug, List[int]]] = []
    for f in _geladen(db).filter(Fahrzeug.aktiv.is_(True)).all():
        reihe = punkte(f)
        if not reihe:
            continue
        letzte = _letzte_je_jahr(reihe)
        erstes = reihe[0].datum.year
        fehlend = [
            j for j in range(erstes, heute.year)
            if j not in letzte or (date(j, 12, 31) - letzte[j].datum).days > 14
        ]
        if fehlend:
            aus.append((f, fehlend))
    return aus
