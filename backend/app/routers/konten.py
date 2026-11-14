from datetime import date

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Buchung, Konto, Sondertilgung
from app.schemas import (
    KontoCreate,
    KontoOut,
    KontoUpdate,
    SondertilgungCreate,
    SondertilgungOut,
    SondertilgungUpdate,
)

router = APIRouter(prefix="/konten", tags=["konten"])

MAX_MONATE = 70 * 12  # Sicherheitsgrenze gegen Endlosschleife


@router.get("", response_model=list[KontoOut])
def list_konten(nur_aktiv: bool = True, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Konto)
    if nur_aktiv:
        q = q.filter(Konto.aktiv == True)
    typ_order = case({'giro': 0, 'spar': 1, 'darlehen': 2, 'kredit': 3, 'depot': 4}, value=Konto.typ, else_=5)
    return q.order_by(typ_order, Konto.name).all()


def _hoechststand(konto_id: int, startsaldo: float, db: Session) -> float:
    """Höchster je erreichter Schuldenstand des Kontos (positiv), aus dem Verlauf
    der gebuchten Buchungen.

    Bezugsgröße für den Tilgungsfortschritt. Der vereinbarte darlehen_betrag taugt
    dafür nicht: bei einem Bauvorhaben wird er in Teilbeträgen abgerufen, eine
    niedrige Restschuld bedeutet dann „noch nicht ausgezahlt" und nicht „getilgt".
    Der Höchststand wächst während der Auszahlungsphase mit, danach misst die
    Differenz zur aktuellen Restschuld die tatsächliche Tilgung.

    Achtung: beruht auf den vorhandenen Buchungen – fehlt ein Kontoauszug aus der
    Auszahlungsphase, fällt auch der Höchststand zu niedrig aus.
    """
    stand = startsaldo
    tiefster = min(stand, 0.0)
    for (betrag,) in db.query(Buchung.betrag).filter(
        Buchung.konto_id == konto_id, Buchung.status == "gebucht",
    ).order_by(Buchung.datum, Buchung.id).all():
        stand += betrag
        tiefster = min(tiefster, stand)
    return round(abs(tiefster), 2)


# Muss vor der Route "/{konto_id}" stehen, sonst fängt diese den festen Pfad ab.
@router.get("/darlehen-uebersicht")
def darlehen_uebersicht(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Kompakte Eckdaten aller aktiven Darlehens-/Kreditkonten für das Dashboard.

    Nutzt dieselbe Rechnung wie darlehen_hochrechnung, liefert aber weder Monats-
    noch Jahresliste – das Dashboard zeigt pro Konto nur eine Tabellenzeile.
    Unvollständig gepflegte Konten erscheinen mit konfiguriert=False und den
    fehlenden Feldern; ihre Restschuld steht als real_restschuld trotzdem bereit.

    rate, zinssatz, letzte_rate und nie_getilgt zeigt das Dashboard derzeit nicht
    an (die Kacheln tragen nur Restschuld und Tilgungsfortschritt) – sie bleiben
    bewusst im Ergebnis, für eine spätere Detailansicht.
    """
    typ_order = case({'darlehen': 0, 'kredit': 1}, value=Konto.typ, else_=2)
    konten = (
        db.query(Konto)
        .filter(Konto.aktiv == True, Konto.typ.in_(("darlehen", "kredit")))  # noqa: E712
        .order_by(typ_order, Konto.name)
        .all()
    )
    zeilen = []
    for k in konten:
        h = darlehen_hochrechnung(k.id, True, db, None)
        eck = h.get("eckdaten") or {}
        zeilen.append({
            "konto_id": k.id,
            "name": k.name,
            "bank": k.bank,
            "typ": k.typ,
            "darlehen_art": k.darlehen_art or "annuitaet",
            "konfiguriert": h["konfiguriert"],
            "fehlende_parameter": h["fehlende_parameter"],
            "real_restschuld": h["real_restschuld"],
            "hoechststand": _hoechststand(k.id, k.startsaldo, db),
            "darlehen_betrag": k.darlehen_betrag,
            "rate": k.rate,
            "zinssatz": k.zinssatz,
            "letzte_rate": eck.get("letzte_rate"),
            "nie_getilgt": eck.get("nie_getilgt", False),
            "zinsbindung_ende": eck.get("zinsbindung_ende"),
            "restschuld_bei_zinsbindungsende": eck.get("restschuld_bei_zinsbindungsende"),
            # nur bei darlehen_art='endfaellig' gefüllt – dort ersetzt Restlaufzeit/Ablösung
            # den Tilgungsfortschritt, der hier per Definition ewig 0 % bliebe
            "faelligkeit": eck.get("faelligkeit"),
            "restlaufzeit_monate": eck.get("restlaufzeit_monate"),
            "abloesebetrag": eck.get("abloesebetrag"),
            "freie_kreditlinie": eck.get("freie_kreditlinie"),
            "monatszins_aktuell": eck.get("monatszins_aktuell"),
        })
    return zeilen


# Muss vor der Route "/{konto_id}" stehen, sonst fängt diese den festen Pfad ab.
@router.get("/depot-uebersicht")
def depot_uebersicht(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Wert und Gewinn/Verlust aller aktiven Depotkonten.

    marktwert = anteile × kurs, beides manuell am Konto gepflegt (die App ruft
    keine Kurse ab). investiert ist der Buchungssaldo: die Summe aller Ein- und
    Auszahlungen auf das Depot – ein späterer Verkauf ist eine negative Buchung
    und senkt die Basis von selbst.

    Fehlt anteile oder kurs, bleibt marktwert None; `wert` trägt dann den
    Buchungssaldo, damit das Depot nicht aus dem Finanzsaldo verschwindet.
    Ein Gewinn/Verlust wird in dem Fall bewusst nicht ausgewiesen – er wäre
    per Definition 0 und würde eine Aussage vortäuschen.

    breakeven_kurs braucht nur die Anteile und sagt, ab welchem Kurs der
    Bestand die investierte Summe übersteigt.
    """
    konten = (
        db.query(Konto)
        .filter(Konto.aktiv == True, Konto.typ == "depot")  # noqa: E712
        .order_by(Konto.name)
        .all()
    )
    zeilen = []
    for k in konten:
        investiert = _saldo(k.id, k.startsaldo, db)
        marktwert = (
            round(float(k.anteile) * float(k.kurs), 2)
            if k.anteile is not None and k.kurs is not None
            else None
        )
        gewinn = round(marktwert - investiert, 2) if marktwert is not None else None
        zeilen.append({
            "konto_id": k.id,
            "name": k.name,
            "bank": k.bank,
            "isin": k.isin,
            "anteile": k.anteile,
            "kurs": k.kurs,
            "kurs_datum": k.kurs_datum,
            "investiert": investiert,
            "marktwert": marktwert,
            "wert": marktwert if marktwert is not None else investiert,
            "gewinn": gewinn,
            # Ohne Einzahlungen (investiert = 0) ist die Rendite nicht definiert.
            "gewinn_prozent": (
                round(gewinn / investiert * 100, 1)
                if gewinn is not None and investiert > 0 else None
            ),
            # Kurs, ab dem der Bestand die investierte Summe übersteigt (Gewinn = 0).
            # Hängt an den Anteilen, nicht am gepflegten Kurs – die Schwelle bleibt
            # also stehen, während der Kurs darum schwankt. Ohne Anteile nicht
            # bestimmbar.
            "breakeven_kurs": (
                round(investiert / float(k.anteile), 4)
                if k.anteile not in (None, 0) and investiert > 0 else None
            ),
        })
    return zeilen


@router.get("/{konto_id}", response_model=KontoOut)
def get_konto(konto_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    konto = db.get(Konto, konto_id)
    if not konto:
        raise HTTPException(404, "Nicht gefunden")
    return konto


@router.get("/{konto_id}/buchungen-count")
def buchungen_count(konto_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Anzahl Buchungen für dieses Konto."""
    count = db.query(Buchung).filter(Buchung.konto_id == konto_id).count()
    return {"count": count}


@router.get("/{konto_id}/saldo")
def get_saldo(
    konto_id: int,
    bis: str | None = Query(None),
    geplant_ab: str | None = Query(None, description="Geplante Buchungen ab diesem Datum mitzaehlen"),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Saldo = Startsaldo + Summe aller gebuchten Buchungen (optional bis zu einem Stichtag).

    Mit geplant_ab zaehlen zusaetzlich geplante Buchungen ab diesem Datum mit -
    dieselbe Logik wie der Filter in routers/buchungen.py. Ueberfaellige, nie
    gebuchte Planposten bleiben dadurch aussen vor und verzerren den Ausblick
    nicht.
    """
    konto = db.get(Konto, konto_id)
    if not konto:
        raise HTTPException(404, "Nicht gefunden")
    q = db.query(func.sum(Buchung.betrag)).filter(Buchung.konto_id == konto_id)
    if geplant_ab:
        # bis greift weiter unten fuer alle Buchungen, hier nur die Untergrenze
        q = q.filter(or_(
            Buchung.status == "gebucht",
            (Buchung.status == "geplant") & (Buchung.datum >= geplant_ab),
        ))
    else:
        q = q.filter(Buchung.status == "gebucht")
    if bis:
        q = q.filter(Buchung.datum <= bis)
    summe = q.scalar() or 0.0
    return {"konto_id": konto_id, "name": konto.name, "saldo": round(konto.startsaldo + summe, 2)}


@router.post("", response_model=KontoOut, status_code=201)
def create_konto(body: KontoCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    konto = Konto(**body.model_dump())
    db.add(konto)
    db.commit()
    db.refresh(konto)
    return konto


@router.patch("/{konto_id}", response_model=KontoOut)
def update_konto(konto_id: int, body: KontoUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    konto = db.get(Konto, konto_id)
    if not konto:
        raise HTTPException(404, "Nicht gefunden")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(konto, field, val)
    db.commit()
    db.refresh(konto)
    return konto


def _saldo(konto_id: int, startsaldo: float, db: Session) -> float:
    summe = db.query(func.sum(Buchung.betrag)).filter(
        Buchung.konto_id == konto_id,
        Buchung.status == "gebucht",
    ).scalar() or 0.0
    return round(startsaldo + summe, 2)


# ── Sondertilgungen ──────────────────────────────────────────────────────────
def _get_darlehen_konto(konto_id: int, db: Session) -> Konto:
    konto = db.get(Konto, konto_id)
    if not konto:
        raise HTTPException(404, "Konto nicht gefunden")
    return konto


@router.get("/{konto_id}/sondertilgungen", response_model=list[SondertilgungOut])
def list_sondertilgungen(konto_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    _get_darlehen_konto(konto_id, db)
    return (
        db.query(Sondertilgung)
        .filter(Sondertilgung.konto_id == konto_id)
        .order_by(Sondertilgung.datum)
        .all()
    )


@router.post("/{konto_id}/sondertilgungen", response_model=SondertilgungOut, status_code=201)
def create_sondertilgung(
    konto_id: int, body: SondertilgungCreate, db: Session = Depends(get_db), _=Depends(require_admin)
):
    konto = _get_darlehen_konto(konto_id, db)
    if _ist_endfaellig(konto):
        # Rückführungen laufen bei der Zwischenfinanzierung als normale Buchung über das
        # Konto; die Zinsrechnung sitzt ohnehin auf dem realen Saldo auf. Eine zusätzlich
        # erfasste Sondertilgung würde denselben Betrag ein zweites Mal abziehen.
        raise HTTPException(400, "Endfällige Darlehen: Rückführungen als normale Buchung erfassen")
    st = Sondertilgung(konto_id=konto_id, **body.model_dump())
    db.add(st)
    db.commit()
    db.refresh(st)
    return st


@router.patch("/{konto_id}/sondertilgungen/{st_id}", response_model=SondertilgungOut)
def update_sondertilgung(
    konto_id: int, st_id: int, body: SondertilgungUpdate,
    db: Session = Depends(get_db), _=Depends(require_admin),
):
    st = db.get(Sondertilgung, st_id)
    if not st or st.konto_id != konto_id:
        raise HTTPException(404, "Sondertilgung nicht gefunden")
    for field, val in body.model_dump(exclude_unset=True).items():
        setattr(st, field, val)
    db.commit()
    db.refresh(st)
    return st


@router.delete("/{konto_id}/sondertilgungen/{st_id}", status_code=204)
def delete_sondertilgung(konto_id: int, st_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    st = db.get(Sondertilgung, st_id)
    if not st or st.konto_id != konto_id:
        raise HTTPException(404, "Sondertilgung nicht gefunden")
    db.delete(st)
    db.commit()


def _ist_endfaellig(konto: Konto) -> bool:
    """Endfälliges Darlehen (Zwischenfinanzierung): keine Tilgung, keine Rate, nur Zinsen.
    NULL in darlehen_art bedeutet 'annuitaet' (Bestandsdaten vor Einführung des Feldes)."""
    return konto.darlehen_art == "endfaellig"


def _laufzeit_beginn(konto: Konto, db: Session) -> date | None:
    """Referenzdatum für Zinsbindung bzw. Laufzeit: vollauszahlung_datum, ersatzweise die
    früheste gebuchte Buchung auf dem Konto. Bei einer Zwischenfinanzierung ist das der
    erste Tranchenabruf – eine 'Vollauszahlung' gibt es dort nie, deshalb bleibt das Feld
    dort die manuelle Korrektur (Vertrag früher geschlossen als erstmals abgerufen)."""
    if konto.vollauszahlung_datum:
        return date.fromisoformat(konto.vollauszahlung_datum)
    start_str = db.query(func.min(Buchung.datum)).filter(
        Buchung.konto_id == konto.id, Buchung.status == "gebucht",
    ).scalar()
    return date.fromisoformat(start_str) if start_str else None


def _zinsbindung_ende(konto: Konto, db: Session) -> date | None:
    """Ende der Zinsbindung = Referenzdatum + zinsbindung_jahre. Referenzdatum ist
    vollauszahlung_datum, ersatzweise die früheste gebuchte Buchung auf dem Konto.
    None, wenn zinsbindung_jahre fehlt oder kein Referenzdatum ermittelbar ist."""
    if not konto.zinsbindung_jahre:
        return None
    beginn = _laufzeit_beginn(konto, db)
    if not beginn:
        return None
    return beginn + relativedelta(years=int(konto.zinsbindung_jahre))


def _restschuld_bei_datum(monate: list[dict], datum: date, vor_start_wert: float | None) -> float | None:
    """Restschuld zu einem Stichtag aus einer Monatsliste (rein informativ, ändert die
    Amortisation nicht). Vor dem ersten Monat der Liste: vor_start_wert (z.B. voller
    Darlehensbetrag beim Plan, None beim Szenario, da dessen Historie vor Start unbekannt ist).
    Nach dem letzten Monat: 0 (bereits getilgt)."""
    if not monate:
        return None
    iso = datum.isoformat()
    if iso < monate[0]["datum"]:
        return vor_start_wert
    for m in monate:
        if m["datum"] >= iso:
            return m["restschuld"]
    return 0.0


# ── Endfälliges Darlehen (Zwischenfinanzierung) ──────────────────────────────
def _endfaellig_hochrechnung(konto: Konto, db: Session, saldo: float, real_restschuld: float, basis: dict) -> dict:
    """Zinsplan eines endfälligen Darlehens: keine Tilgung, keine Rate – nur Zinsen bis
    zur Fälligkeit, dann Ablösung in einer Summe (durch Bausparsumme, Endfinanzierung o.ä.).

    Hybride Schuldbasis: für vergangene Monate der reale Saldoverlauf (die Linie wird in
    Tranchen abgerufen, ein konstanter darlehen_betrag würde die Zinsen überschätzen), ab
    dem laufenden Monat der heutige Saldo konstant fortgeschrieben – der weitere Abrufplan
    ist nicht bekannt, alles andere wäre geraten. Maßgeblich ist jeweils der Stand zu
    Periodenbeginn; ein Abruf mitten im Monat wirkt also erst im Folgemonat.

    Die Zinsen sind damit rechnerisch, nicht gebucht: die Zinszahlungen laufen über das
    Girokonto und sind auf diesem Konto gar nicht sichtbar. Abweichungen zur Bankabrechnung
    (Zinsmethode, Abrechnungstermine) sind zu erwarten.
    """
    fehlend = [f for f in ("darlehen_betrag", "zinssatz", "zinsbindung_jahre")
               if getattr(konto, f) in (None, "")]
    beginn = _laufzeit_beginn(konto, db)
    if beginn is None:
        fehlend.append("vollauszahlung_datum")
    if fehlend:
        return {**basis, "konfiguriert": False, "fehlende_parameter": fehlend,
                "monate": [], "jahre": [], "eckdaten": None}

    faelligkeit = beginn + relativedelta(years=int(konto.zinsbindung_jahre))
    zinssatz_m = float(konto.zinssatz) / 100.0 / 12.0
    heute = date.today()

    buchungen = (
        db.query(Buchung.datum, Buchung.betrag)
        .filter(Buchung.konto_id == konto.id, Buchung.status == "gebucht")
        .order_by(Buchung.datum)
        .all()
    )

    monate: list[dict] = []
    lauf = float(konto.startsaldo)
    idx = 0
    zinsen_bisher = 0.0
    zinsen_kuenftig = 0.0
    kumuliert = 0.0
    aktuell = beginn
    # Ganze Jahre ab beginn gehen glatt in Monate auf, es entsteht keine Teilperiode.
    while aktuell < faelligkeit and len(monate) < MAX_MONATE:
        iso = aktuell.isoformat()
        while idx < len(buchungen) and buchungen[idx][0] <= iso:
            lauf += buchungen[idx][1]
            idx += 1
        ist = aktuell <= heute
        schuld = (round(abs(lauf), 2) if lauf < 0 else round(lauf, 2)) if ist else real_restschuld
        zins = round(schuld * zinssatz_m, 2)
        kumuliert = round(kumuliert + zins, 2)
        if ist:
            zinsen_bisher = round(zinsen_bisher + zins, 2)
        else:
            zinsen_kuenftig = round(zinsen_kuenftig + zins, 2)
        monate.append({
            "datum": iso,
            "restschuld": schuld,
            "zins": zins,
            "zins_kumuliert": kumuliert,
            "ist": ist,
            # Für die gemeinsame Chart-/Tabellenlogik mit der Annuität:
            "rate": zins, "tilgung": 0.0, "sondertilgung": 0.0,
        })
        aktuell += relativedelta(months=1)

    jahre_map: dict[int, dict] = {}
    for m in monate:
        jahr = int(m["datum"][:4])
        j = jahre_map.setdefault(jahr, {"jahr": jahr, "zins": 0.0, "tilgung": 0.0,
                                        "sondertilgung": 0.0, "restschuld": 0.0})
        j["zins"] = round(j["zins"] + m["zins"], 2)
        j["restschuld"] = m["restschuld"]
    jahre = [jahre_map[k] for k in sorted(jahre_map)]

    restlaufzeit = sum(1 for m in monate if not m["ist"])
    eckdaten = {
        "laufzeit_beginn": beginn.isoformat(),
        "faelligkeit": faelligkeit.isoformat(),
        "laufzeit_monate": len(monate),
        "restlaufzeit_monate": restlaufzeit,
        "abloesebetrag": real_restschuld,
        "freie_kreditlinie": round(float(konto.darlehen_betrag) - real_restschuld, 2),
        "monatszins_aktuell": round(real_restschuld * zinssatz_m, 2),
        "zinsen_bisher": zinsen_bisher,
        "zinsen_kuenftig": zinsen_kuenftig,
        "gesamt_zinsen": round(zinsen_bisher + zinsen_kuenftig, 2),
        "gesamt_sondertilgung": 0.0,
        "summe_gezahlt": round(real_restschuld + zinsen_bisher + zinsen_kuenftig, 2),
        "letzte_rate": None,
        "nie_getilgt": False,
        # Fälligkeit füllt die Zinsbindungs-Felder, damit Dashboard und Chart-Linie
        # unverändert weiterfunktionieren.
        "zinsbindung_ende": faelligkeit.isoformat(),
        "restschuld_bei_zinsbindungsende": real_restschuld,
    }
    return {**basis, "konfiguriert": True, "fehlende_parameter": [],
            "monate": monate, "jahre": jahre, "eckdaten": eckdaten}


# ── Darlehens-Hochrechnung (Annuität) ────────────────────────────────────────
@router.get("/{konto_id}/darlehen-hochrechnung")
def darlehen_hochrechnung(
    konto_id: int,
    mit_sondertilgung: bool = Query(True),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Tilgungsplan (Annuität) aus den Darlehensparametern des Kontos.
    Monatlich: Zinsanteil/Tilgungsanteil/Sondertilgung/Restschuld bis Restschuld 0.
    Zusätzlich Jahres-Zusammenfassung, Eckdaten und realer Saldo zum Vergleich.

    Bei darlehen_art='endfaellig' (Zwischenfinanzierung) übernimmt stattdessen
    _endfaellig_hochrechnung – dort gibt es weder Rate noch Tilgung."""
    konto = _get_darlehen_konto(konto_id, db)

    saldo = _saldo(konto_id, konto.startsaldo, db)
    real_restschuld = round(abs(saldo), 2) if saldo < 0 else round(saldo, 2)

    basis = {
        "konto": {"id": konto.id, "name": konto.name, "typ": konto.typ},
        "darlehen_art": konto.darlehen_art or "annuitaet",
        "parameter": {
            "darlehen_betrag": konto.darlehen_betrag,
            "zinssatz": konto.zinssatz,
            "rate": konto.rate,
            "tilgung_start": konto.tilgung_start,
            "vollauszahlung_datum": konto.vollauszahlung_datum,
            "zinsbindung_jahre": konto.zinsbindung_jahre,
        },
        "real_saldo": saldo,
        "real_restschuld": real_restschuld,
    }

    if _ist_endfaellig(konto):
        return _endfaellig_hochrechnung(konto, db, saldo, real_restschuld, basis)

    fehlend = [f for f in ("darlehen_betrag", "zinssatz", "rate", "tilgung_start")
               if getattr(konto, f) in (None, "")]
    if fehlend:
        return {**basis, "konfiguriert": False, "fehlende_parameter": fehlend,
                "monate": [], "jahre": [], "eckdaten": None}

    # Sondertilgungen je Monat (YYYY-MM -> Summe)
    st_map: dict[str, float] = {}
    if mit_sondertilgung:
        for st in db.query(Sondertilgung).filter(Sondertilgung.konto_id == konto_id).all():
            key = st.datum[:7]
            st_map[key] = round(st_map.get(key, 0.0) + st.betrag, 2)

    restschuld = float(konto.darlehen_betrag)
    zinssatz_m = float(konto.zinssatz) / 100.0 / 12.0
    rate = float(konto.rate)
    aktuell = date.fromisoformat(konto.tilgung_start)

    monate = []
    gesamt_zinsen = 0.0
    gesamt_sonder = 0.0
    nie_getilgt = False

    for _i in range(MAX_MONATE):
        if restschuld <= 0:
            break
        zins = round(restschuld * zinssatz_m, 2)
        tilgung = round(rate - zins, 2)
        if tilgung <= 0:
            nie_getilgt = True
            break
        if tilgung > restschuld:
            tilgung = round(restschuld, 2)
        restschuld = round(restschuld - tilgung, 2)
        # Sondertilgung in diesem Monat
        sonder = st_map.get(aktuell.strftime("%Y-%m"), 0.0)
        if sonder:
            sonder = round(min(sonder, restschuld), 2)
            restschuld = round(restschuld - sonder, 2)
        gesamt_zinsen = round(gesamt_zinsen + zins, 2)
        gesamt_sonder = round(gesamt_sonder + sonder, 2)
        monate.append({
            "datum": aktuell.isoformat(),
            "rate": round(zins + tilgung, 2),
            "zins": zins,
            "tilgung": tilgung,
            "sondertilgung": sonder,
            "restschuld": restschuld,
        })
        aktuell += relativedelta(months=1)

    # Jahres-Zusammenfassung
    jahre_map: dict[int, dict] = {}
    for m in monate:
        jahr = int(m["datum"][:4])
        j = jahre_map.setdefault(jahr, {"jahr": jahr, "zins": 0.0, "tilgung": 0.0, "sondertilgung": 0.0, "restschuld": 0.0})
        j["zins"] = round(j["zins"] + m["zins"], 2)
        j["tilgung"] = round(j["tilgung"] + m["tilgung"], 2)
        j["sondertilgung"] = round(j["sondertilgung"] + m["sondertilgung"], 2)
        j["restschuld"] = m["restschuld"]  # Stand Jahresende (letzter Monat gewinnt)
    jahre = [jahre_map[k] for k in sorted(jahre_map)]

    zinsbindung_ende = _zinsbindung_ende(konto, db)
    eckdaten = {
        "laufzeit_monate": len(monate),
        "letzte_rate": monate[-1]["datum"] if monate else None,
        "gesamt_zinsen": gesamt_zinsen,
        "gesamt_sondertilgung": gesamt_sonder,
        "summe_gezahlt": round(float(konto.darlehen_betrag) + gesamt_zinsen, 2),
        "nie_getilgt": nie_getilgt,
        "zinsbindung_ende": zinsbindung_ende.isoformat() if zinsbindung_ende else None,
        "restschuld_bei_zinsbindungsende": (
            _restschuld_bei_datum(monate, zinsbindung_ende, float(konto.darlehen_betrag))
            if zinsbindung_ende else None
        ),
    }

    return {**basis, "konfiguriert": True, "fehlende_parameter": [],
            "monate": monate, "jahre": jahre, "eckdaten": eckdaten}


def _simuliere_szenario(
    restschuld_start: float, rate: float, zinssatz_m: float, st_map: dict[str, float],
    differenz_pro_monat: float, zusatz_jaehrlich: float, start_datum: date,
) -> tuple[list[dict], list[dict], dict]:
    """Monatsschleife ab start_datum mit gegebener Rate. Im Dezember wird zusaetzlich
    zu real geplanten Sondertilgungen `differenz_pro_monat` je seit der letzten
    Ausschuettung vergangenem Monat sowie `zusatz_jaehrlich` als Sondertilgung
    eingerechnet (0 fuer differenz_pro_monat ergibt die unveraenderte Vergleichsrechnung)."""
    restschuld = restschuld_start
    aktuell = start_datum
    monate: list[dict] = []
    gesamt_zinsen = 0.0
    gesamt_sonder = 0.0
    monate_seit_ausschuettung = 0
    nie_getilgt = False

    for _i in range(MAX_MONATE):
        if restschuld <= 0:
            break
        zins = round(restschuld * zinssatz_m, 2)
        tilgung = round(rate - zins, 2)
        if tilgung <= 0:
            nie_getilgt = True
            break
        if tilgung > restschuld:
            tilgung = round(restschuld, 2)
        restschuld = round(restschuld - tilgung, 2)
        monate_seit_ausschuettung += 1

        sonder = st_map.get(aktuell.strftime("%Y-%m"), 0.0)
        if aktuell.month == 12:
            sonder = round(sonder + differenz_pro_monat * monate_seit_ausschuettung + zusatz_jaehrlich, 2)
            monate_seit_ausschuettung = 0
        if sonder:
            sonder = round(min(sonder, restschuld), 2)
            restschuld = round(restschuld - sonder, 2)

        gesamt_zinsen = round(gesamt_zinsen + zins, 2)
        gesamt_sonder = round(gesamt_sonder + sonder, 2)
        monate.append({
            "datum": aktuell.isoformat(),
            "rate": round(zins + tilgung, 2),
            "zins": zins,
            "tilgung": tilgung,
            "sondertilgung": sonder,
            "restschuld": restschuld,
        })
        aktuell += relativedelta(months=1)

    jahre_map: dict[int, dict] = {}
    for m in monate:
        jahr = int(m["datum"][:4])
        j = jahre_map.setdefault(jahr, {"jahr": jahr, "zins": 0.0, "tilgung": 0.0, "sondertilgung": 0.0, "restschuld": 0.0})
        j["zins"] = round(j["zins"] + m["zins"], 2)
        j["tilgung"] = round(j["tilgung"] + m["tilgung"], 2)
        j["sondertilgung"] = round(j["sondertilgung"] + m["sondertilgung"], 2)
        j["restschuld"] = m["restschuld"]
    jahre = [jahre_map[k] for k in sorted(jahre_map)]

    eckdaten = {
        "laufzeit_monate": len(monate),
        "letzte_rate": monate[-1]["datum"] if monate else None,
        "gesamt_zinsen": gesamt_zinsen,
        "gesamt_sondertilgung": gesamt_sonder,
        "summe_gezahlt": round(restschuld_start + gesamt_zinsen, 2),
        "nie_getilgt": nie_getilgt,
    }
    return monate, jahre, eckdaten


@router.get("/{konto_id}/darlehen-hochrechnung-szenario")
def darlehen_hochrechnung_szenario(
    konto_id: int,
    neuer_tilgungssatz: float = Query(..., gt=0),
    zusatz_sondertilgung_jaehrlich: float = Query(0.0, ge=0),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Was-wäre-wenn: neuer Tilgungssatz ab heute (bezogen auf den urspruenglichen
    Darlehensbetrag), Startpunkt ist die reale Restschuld heute. Die Differenz aus
    alter und neuer Monatsrate fliesst jaehrlich im Dezember als Sondertilgung ein
    (im ersten, angebrochenen Jahr anteilig nach vergangenen Monaten seit Start),
    zusaetzlich zu bereits real geplanten Sondertilgungen und einem optionalen
    fixen Jahresbetrag. Rein rechnerische Vorschau, aendert keine gespeicherten Daten.
    Zum fairen Vergleich wird zusaetzlich die Variante 'unveraendert' (alte Rate,
    keine Differenz-Umleitung, aber gleiche Zusatz-Sondertilgung) mitberechnet."""
    konto = _get_darlehen_konto(konto_id, db)
    if _ist_endfaellig(konto):
        # Das Szenario rechnet mit einer Anfangstilgung – die gibt es bei einem
        # endfälligen Darlehen per Definition nicht.
        raise HTTPException(400, "Für endfällige Darlehen gibt es keine Tilgungssatz-Simulation")

    fehlend = [f for f in ("darlehen_betrag", "zinssatz", "rate", "tilgung_start")
               if getattr(konto, f) in (None, "")]
    if fehlend:
        raise HTTPException(400, f"Darlehen nicht vollständig konfiguriert: {', '.join(fehlend)}")

    saldo = _saldo(konto_id, konto.startsaldo, db)
    restschuld_start = round(abs(saldo), 2) if saldo < 0 else round(saldo, 2)
    if restschuld_start <= 0:
        raise HTTPException(400, "Darlehen ist bereits getilgt")

    zinssatz = float(konto.zinssatz)
    zinssatz_m = zinssatz / 100.0 / 12.0
    alte_rate = float(konto.rate)
    neue_rate = round(float(konto.darlehen_betrag) * (zinssatz + neuer_tilgungssatz) / 100.0 / 12.0, 2)
    monatliche_ersparnis = max(0.0, round(alte_rate - neue_rate, 2))

    # real geplante Sondertilgungen (YYYY-MM -> Summe) fliessen zusaetzlich mit ein
    st_map: dict[str, float] = {}
    for st in db.query(Sondertilgung).filter(Sondertilgung.konto_id == konto_id).all():
        key = st.datum[:7]
        st_map[key] = round(st_map.get(key, 0.0) + st.betrag, 2)

    heute = date.today()
    aktuell = date(heute.year, heute.month, 1) + relativedelta(months=1)

    monate, jahre, eckdaten = _simuliere_szenario(
        restschuld_start, neue_rate, zinssatz_m, st_map,
        monatliche_ersparnis, zusatz_sondertilgung_jaehrlich, aktuell,
    )
    _, _, eckdaten_unveraendert = _simuliere_szenario(
        restschuld_start, alte_rate, zinssatz_m, st_map,
        0.0, zusatz_sondertilgung_jaehrlich, aktuell,
    )

    zinsbindung_ende = _zinsbindung_ende(konto, db)
    eckdaten["zinsbindung_ende"] = zinsbindung_ende.isoformat() if zinsbindung_ende else None
    eckdaten["restschuld_bei_zinsbindungsende"] = (
        _restschuld_bei_datum(monate, zinsbindung_ende, None) if zinsbindung_ende else None
    )

    return {
        "parameter": {
            "restschuld_start": restschuld_start,
            "alte_rate": alte_rate,
            "neue_rate": neue_rate,
            "monatliche_ersparnis": monatliche_ersparnis,
            "neuer_tilgungssatz": neuer_tilgungssatz,
            "zusatz_sondertilgung_jaehrlich": zusatz_sondertilgung_jaehrlich,
        },
        "monate": monate,
        "jahre": jahre,
        "eckdaten": eckdaten,
        "vergleich_unveraendert": {"eckdaten": eckdaten_unveraendert},
    }


@router.delete("/{konto_id}", status_code=204)
def delete_konto(konto_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    konto = db.get(Konto, konto_id)
    if not konto:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(konto)
    db.commit()
