"""Verträge und laufende Verpflichtungen.

Zwei Dinge rechnet dieses Modul und speichert sie nicht:

* den **Kündigungstermin** aus `laufzeit_bis`, `kuendigungsfrist` und
  `verlaengerung_monate` (`kuendigungstermin`). Eine gespeicherte Spalte wäre
  nach der ersten stillen Verlängerung falsch, ohne dass es jemand merkt.
* **Soll und Ist**: Soll ist die Summe der Raten auf ein Jahr gerechnet, Ist
  sind die Buchungen der letzten zwölf Monate mit dieser `vertrag_id`.

Die Zuordnung einer echten Buchung läuft über zwei ungleich starke Merkmale —
`mandatsreferenz` (eindeutig, ordnet still zu) und `empfaenger_id` (Indiz,
fragt immer). Warum, steht an `models.Vertrag`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Optional

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.models import Beleg, Buchung, Vertrag, WiederkehrendeBuchung
from app.schemas import (
    VertragCreate,
    VertragKandidat,
    VertragOut,
    VertragUpdate,
    VertragVorschlag,
    VertragZuordnen,
)
from app.services.import_regel import RegelKatalog

router = APIRouter(prefix="/vertraege", tags=["vertraege"])

# Wie oft im Jahr eine Rate anfällt. Dieselben Schlüssel wie der CHECK an
# `wiederkehrende_buchungen.rhythmus`.
_JE_JAHR = {"monatlich": 12, "zweimonatlich": 6, "quartal": 4, "jaehrlich": 1}

# Ab wann eine Frist als "rückt näher" gilt. Bewusst großzügig: drei Monate
# Kündigungsfrist sind üblich, und wer erst 30 Tage vorher erfährt, dass er
# vor 60 Tagen hätte kündigen müssen, ist nicht gewarnt, sondern geärgert.
VORLAUF_TAGE = 60


def _als_datum(wert: Optional[str]) -> Optional[date]:
    """ISO-Text zu Datum, tolerant: krumme Werte gelten als "nicht gesetzt"."""
    if not wert:
        return None
    try:
        return date.fromisoformat(wert[:10])
    except ValueError:
        return None


def _frist(vertrag: Vertrag) -> Optional[relativedelta]:
    if not vertrag.kuendigungsfrist or vertrag.kuendigungsfrist <= 0:
        return None
    einheit = vertrag.kuendigungsfrist_einheit or "monate"
    if einheit == "tage":
        return relativedelta(days=vertrag.kuendigungsfrist)
    if einheit == "wochen":
        return relativedelta(weeks=vertrag.kuendigungsfrist)
    return relativedelta(months=vertrag.kuendigungsfrist)


def kuendigungstermin(vertrag: Vertrag, heute: date) -> Optional[date]:
    """Der nächste Tag, an dem noch gekündigt werden kann.

    `None` heißt: es gibt keinen Termin, auf den man warten muss — der Vertrag
    ist schon gekündigt, unbefristet (dann gilt nur die Frist, er ist jederzeit
    kündbar) oder er endet mit der Laufzeit, die bereits verstrichen ist.
    """
    if vertrag.gekuendigt_am:
        return None

    ende = _als_datum(vertrag.laufzeit_bis)
    frist = _frist(vertrag)
    if not ende or not frist:
        return None

    termin = ende - frist
    # Ist der Termin vorbei, hat sich der Vertrag verlängert: so lange
    # weiterschieben, bis er in der Zukunft liegt. Ohne Verlängerung bleibt es
    # beim verstrichenen Termin, und der Vertrag läuft einfach aus.
    schritte = 0
    while termin < heute and vertrag.verlaengerung_monate and vertrag.verlaengerung_monate > 0:
        ende = ende + relativedelta(months=vertrag.verlaengerung_monate)
        termin = ende - frist
        schritte += 1
        if schritte > 200:  # Notbremse gegen krumme Daten, nie im Normalbetrieb
            return None

    return termin if termin >= heute else None


def _ratensumme_jahr(vertrag: Vertrag) -> float:
    return sum(
        (r.betrag or 0) * _JE_JAHR.get(r.rhythmus, 0)
        for r in vertrag.raten
        if r.aktiv
    )


def _ist_summen(db: Session, vertrag_ids: list[int], heute: date) -> dict[int, float]:
    """Summe der gebuchten Zahlungen der letzten zwölf Monate, je Vertrag."""
    if not vertrag_ids:
        return {}
    ab = (heute - relativedelta(years=1)).isoformat()
    zeilen = (
        db.query(Buchung.vertrag_id, func.sum(Buchung.betrag))
        .filter(
            Buchung.vertrag_id.in_(vertrag_ids),
            Buchung.status == "gebucht",
            Buchung.datum >= ab,
        )
        .group_by(Buchung.vertrag_id)
        .all()
    )
    return {vid: float(summe or 0) for vid, summe in zeilen}


def _dokument_anzahl(db: Session, vertrag_ids: list[int]) -> dict[int, int]:
    if not vertrag_ids:
        return {}
    zeilen = (
        db.query(Beleg.vertrag_id, func.count(Beleg.id))
        .filter(Beleg.vertrag_id.in_(vertrag_ids))
        .group_by(Beleg.vertrag_id)
        .all()
    )
    return {vid: int(anzahl) for vid, anzahl in zeilen}


def _hinaus(db: Session, vertraege: list[Vertrag], heute: Optional[date] = None) -> list[VertragOut]:
    heute = heute or date.today()
    ids = [v.id for v in vertraege]
    ist = _ist_summen(db, ids, heute)
    dok = _dokument_anzahl(db, ids)

    ergebnis: list[VertragOut] = []
    for v in vertraege:
        termin = kuendigungstermin(v, heute)
        aus = VertragOut.model_validate(v)
        aus.status = "gekuendigt" if v.gekuendigt_am else "laufend"
        aus.kuendigen_bis = termin.isoformat() if termin else None
        aus.tage_bis_kuendigung = (termin - heute).days if termin else None
        aus.soll_jahr = _ratensumme_jahr(v)
        aus.ist_12monate = ist.get(v.id, 0.0)
        aus.raten_anzahl = sum(1 for r in v.raten if r.aktiv)
        aus.dokumente_anzahl = dok.get(v.id, 0)
        aus.kategorie_name = v.kategorie.name if v.kategorie else None
        aus.konto_name = v.konto.name if v.konto else None
        aus.empfaenger_name = v.empfaenger_obj.name if v.empfaenger_obj else None
        aus.fahrzeug_name = v.fahrzeug.name if v.fahrzeug else None
        ergebnis.append(aus)
    return ergebnis


def _geladen(db: Session):
    return db.query(Vertrag).options(
        selectinload(Vertrag.raten),
        selectinload(Vertrag.kategorie),
        selectinload(Vertrag.konto),
        selectinload(Vertrag.empfaenger_obj),
        selectinload(Vertrag.fahrzeug),
    )


def _referenz_frei(db: Session, referenz: Optional[str], ausser_id: Optional[int] = None) -> None:
    """Wirft 409, wenn die Mandatsreferenz schon an einem anderen Vertrag steht.

    Der UNIQUE-Index der Migration fängt das ohnehin ab — aber als nackter
    IntegrityError, dem niemand ansieht, welcher Vertrag im Weg steht.
    """
    if not referenz:
        return
    q = db.query(Vertrag).filter(Vertrag.mandatsreferenz == referenz)
    if ausser_id:
        q = q.filter(Vertrag.id != ausser_id)
    anderer = q.first()
    if anderer:
        raise HTTPException(
            409,
            f"Die Mandatsreferenz {referenz} steht schon am Vertrag "
            f"„{anderer.name}“. Eine Referenz gehört zu genau einem Vertrag.",
        )


# ── Stammdaten ──────────────────────────────────────────────────────────────
@router.get("", response_model=list[VertragOut])
def list_vertraege(
    nur_laufend: bool = False,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = _geladen(db).filter(Vertrag.aktiv.is_(True))
    if nur_laufend:
        q = q.filter(Vertrag.gekuendigt_am.is_(None))
    return _hinaus(db, q.order_by(Vertrag.name).all())


@router.get("/offene-zuordnungen", response_model=list[VertragVorschlag])
def offene_zuordnungen(
    konto_id: Optional[int] = None,
    grenze: int = 25,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Gebuchte Zahlungen ohne Vertrag, zu denen ein Vertrag passen könnte.

    Die Liste ist der Arbeitsvorrat des Zuordnungs-Dialogs. Vorgeschlagen wird
    nur, was auch zugeordnet werden kann: ein Vorschlag ohne Kandidaten wäre
    eine Frage ohne Antwortmöglichkeit.
    """
    vertraege = _geladen(db).filter(
        Vertrag.aktiv.is_(True), Vertrag.gekuendigt_am.is_(None)
    ).all()
    if not vertraege:
        return []

    # Vorauswahl schon in SQL, und zwar nach denselben Merkmalen, die der
    # Vorschlag nachher prüft. Ohne sie müsste ein Fenster der jüngsten
    # Buchungen reichen - und das verfehlt bei dreitausend Buchungen genau die
    # eine, um die es geht.
    emp_ids = {v.empfaenger_id for v in vertraege if v.empfaenger_id}
    referenzen = {v.mandatsreferenz for v in vertraege if v.mandatsreferenz}
    konto_ids = {v.konto_id for v in vertraege if v.konto_id}
    betraege = {
        r.betrag for v in vertraege for r in v.raten if r.aktiv and r.betrag is not None
    }

    merkmale = []
    if emp_ids:
        merkmale.append(Buchung.empfaenger_id.in_(emp_ids))
    if referenzen:
        merkmale.append(Buchung.import_mandatsreferenz.in_(referenzen))
    if konto_ids and betraege:
        # Der Betrag exakt, die Toleranz von einem Cent prüft erst
        # `_betrag_passt`: die Vorauswahl darf strenger sein als die Prüfung,
        # nur nicht weiter.
        merkmale.append(and_(Buchung.konto_id.in_(konto_ids), Buchung.betrag.in_(betraege)))
    if not merkmale:
        return []

    q = (
        db.query(Buchung)
        .options(selectinload(Buchung.konto))
        .filter(
            Buchung.vertrag_id.is_(None),
            Buchung.status == "gebucht",
            Buchung.ist_transfer.is_(False),
            or_(*merkmale),
        )
    )
    if konto_id:
        q = q.filter(Buchung.konto_id == konto_id)
    # Die jüngsten zuerst - eine zwei Jahre alte Zahlung ordnet niemand mehr zu.
    offen = q.order_by(Buchung.datum.desc()).limit(max(grenze, 1) * 8).all()

    katalog = RegelKatalog(db)
    vorschlaege: list[VertragVorschlag] = []
    for buchung in offen:
        vorschlag = _vorschlag(db, buchung, vertraege, katalog)
        if vorschlag and vorschlag.kandidaten:
            vorschlaege.append(vorschlag)
        if len(vorschlaege) >= grenze:
            break
    return vorschlaege


@router.get("/{vertrag_id}", response_model=VertragOut)
def get_vertrag(vertrag_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    vertrag = _geladen(db).filter(Vertrag.id == vertrag_id).first()
    if not vertrag:
        raise HTTPException(404, "Nicht gefunden")
    return _hinaus(db, [vertrag])[0]


@router.post("", response_model=VertragOut, status_code=201)
def create_vertrag(
    body: VertragCreate,
    db: Session = Depends(get_db),
    benutzer=Depends(require_admin),
):
    daten = body.model_dump()
    _referenz_frei(db, daten.get("mandatsreferenz"))
    vertrag = Vertrag(**daten, erstellt_von=getattr(benutzer, "id", None))
    db.add(vertrag)
    db.commit()
    db.refresh(vertrag)
    return _hinaus(db, [vertrag])[0]


@router.patch("/{vertrag_id}", response_model=VertragOut)
def update_vertrag(
    vertrag_id: int,
    body: VertragUpdate,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    vertrag = db.get(Vertrag, vertrag_id)
    if not vertrag:
        raise HTTPException(404, "Nicht gefunden")

    daten = body.model_dump(exclude_unset=True)
    if "mandatsreferenz" in daten:
        daten["mandatsreferenz"] = (daten["mandatsreferenz"] or "").strip() or None
        _referenz_frei(db, daten["mandatsreferenz"], ausser_id=vertrag_id)
    if daten.get("kuendigungsfrist_einheit") not in (None, "tage", "wochen", "monate"):
        raise HTTPException(422, "kuendigungsfrist_einheit muss tage, wochen oder monate sein")

    for feld, wert in daten.items():
        setattr(vertrag, feld, wert)
    db.commit()
    db.refresh(vertrag)
    return _hinaus(db, [vertrag])[0]


@router.delete("/{vertrag_id}", status_code=204)
def delete_vertrag(vertrag_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    """Löscht den Vertrag, nicht seine Zahlungen.

    `buchungen.vertrag_id` und `wiederkehrende_buchungen.vertrag_id` wurden per
    ALTER TABLE nachgerüstet und tragen in gewachsenen Datenbanken keinen
    Fremdschlüssel — SQLite kann keinen nachrüsten. Das SET NULL macht deshalb
    der Router selbst, sonst zeigten die Zahlungen ins Leere. Die Dokumente
    hängen an `belege` *mit* Fremdschlüssel und gehen per CASCADE mit.
    """
    vertrag = db.get(Vertrag, vertrag_id)
    if not vertrag:
        raise HTTPException(404, "Nicht gefunden")

    db.query(Buchung).filter(Buchung.vertrag_id == vertrag_id).update(
        {Buchung.vertrag_id: None}, synchronize_session=False
    )
    db.query(WiederkehrendeBuchung).filter(
        WiederkehrendeBuchung.vertrag_id == vertrag_id
    ).update({WiederkehrendeBuchung.vertrag_id: None}, synchronize_session=False)

    db.delete(vertrag)
    db.commit()
    return None


# ── Raten am Vertrag ────────────────────────────────────────────────────────
# Eigene Endpunkte statt PATCH /wiederkehrend: dort wird mit exclude_none
# gespeichert, ein `vertrag_id: null` käme also nie an. Und das Lösen einer
# Verknüpfung ist etwas anderes als das Ändern eines Betrags - es soll nicht
# aus Versehen beim Bearbeiten einer Vorlage passieren.

@router.post("/{vertrag_id}/raten/{wk_id}", status_code=204)
def rate_anhaengen(
    vertrag_id: int,
    wk_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    if not db.get(Vertrag, vertrag_id):
        raise HTTPException(404, "Vertrag nicht gefunden")
    rate = db.get(WiederkehrendeBuchung, wk_id)
    if not rate:
        raise HTTPException(404, "Vorlage nicht gefunden")
    rate.vertrag_id = vertrag_id
    db.commit()
    return None


@router.delete("/{vertrag_id}/raten/{wk_id}", status_code=204)
def rate_loesen(
    vertrag_id: int,
    wk_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Löst die Vorlage vom Vertrag. Die Vorlage selbst bleibt bestehen."""
    rate = db.get(WiederkehrendeBuchung, wk_id)
    if not rate or rate.vertrag_id != vertrag_id:
        raise HTTPException(404, "Nicht gefunden")
    rate.vertrag_id = None
    db.commit()
    return None


# ── Zahlungen eines Vertrags ────────────────────────────────────────────────
@router.get("/{vertrag_id}/zahlungen")
def zahlungen(
    vertrag_id: int,
    monate: int = 12,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Die Buchungen dieses Vertrags, mit der Angabe, wie sie hergefunden haben."""
    vertrag = _geladen(db).filter(Vertrag.id == vertrag_id).first()
    if not vertrag:
        raise HTTPException(404, "Nicht gefunden")

    ab = (date.today() - relativedelta(months=max(monate, 1))).isoformat()
    buchungen = (
        db.query(Buchung)
        .filter(Buchung.vertrag_id == vertrag_id, Buchung.datum >= ab)
        .order_by(Buchung.datum.desc())
        .all()
    )
    raten_ids = {r.id for r in vertrag.raten}

    def herkunft(b: Buchung) -> str:
        if vertrag.mandatsreferenz and b.import_mandatsreferenz == vertrag.mandatsreferenz:
            return "mandatsreferenz"
        if b.wiederkehrend_id and b.wiederkehrend_id in raten_ids:
            return "vorlage"
        return "manuell"

    return [
        {
            "id": b.id,
            "datum": b.datum,
            "betrag": b.betrag,
            "empfaenger": b.empfaenger,
            "verwendungszweck": b.verwendungszweck or b.import_verwendungszweck,
            "herkunft": herkunft(b),
        }
        for b in buchungen
    ]


# ── Zuordnung einer Buchung ─────────────────────────────────────────────────
@dataclass
class _Sperre:
    """Warum die Mandatsreferenz dieser Buchung nicht gelernt werden darf."""
    grund: str


def _referenz_sperre(buchung: Buchung, katalog: RegelKatalog) -> Optional[_Sperre]:
    """Zahlungsdienstleister: die Referenz gehört ihm, nicht dem Vertrag.

    Über PayPal läuft **ein** SEPA-Mandat für alles. Würde seine Referenz an
    einem Vertrag gelernt, bekäme danach jede PayPal-Abbuchung diesen Vertrag —
    ein stiller Dauerfehler. Erkannt wird der Dienstleister von Stufe
    `anbieter` der Import-Regeln, deren `iban_muster` laut
    `services/import_regel.py` der stabilste Treffer überhaupt ist.
    """
    if not buchung.import_mandatsreferenz:
        return _Sperre("Die Buchung trägt keine Mandatsreferenz.")
    ergebnis = katalog.wende_an(
        buchung.import_empfaenger or buchung.empfaenger,
        buchung.verwendungszweck or buchung.import_verwendungszweck,
        buchung.import_iban,
    )
    if ergebnis.anbieter:
        return _Sperre(
            f"{ergebnis.anbieter.bezeichnung} ist ein Zahlungsdienstleister: die "
            "Mandatsreferenz gehört ihm, nicht diesem Vertrag."
        )
    return None


def _vorschlag(
    db: Session,
    buchung: Buchung,
    vertraege: list[Vertrag],
    katalog: RegelKatalog,
) -> Optional[VertragVorschlag]:
    sperre = _referenz_sperre(buchung, katalog)

    # Harter Weg: die Referenz steht schon an einem Vertrag. Nur gültig, wenn
    # sie überhaupt lernbar wäre - sonst wäre es die Referenz von PayPal.
    if not sperre and buchung.import_mandatsreferenz:
        treffer = [
            v for v in vertraege
            if v.mandatsreferenz and v.mandatsreferenz == buchung.import_mandatsreferenz
        ]
        if treffer:
            v = treffer[0]
            return VertragVorschlag(
                buchung_id=buchung.id,
                datum=buchung.datum,
                betrag=buchung.betrag,
                empfaenger=buchung.empfaenger,
                verwendungszweck=buchung.verwendungszweck or buchung.import_verwendungszweck,
                mandatsreferenz=buchung.import_mandatsreferenz,
                konto_name=buchung.konto.name if buchung.konto else None,
                eindeutig=True,
                referenz_lernbar=True,
                kandidaten=[_kandidat(v, "mandatsreferenz")],
                rueckwirkend_anzahl=0,
            )

    # Weicher Weg: Empfänger, hilfsweise Konto und Betrag.
    kandidaten: list[Vertrag] = []
    for v in vertraege:
        # Eine fremde, schon gelernte Referenz schließt den Vertrag aus - das
        # ist der Fall "zwei gleiche Verträge, einer bereits erkannt".
        if (
            v.mandatsreferenz
            and buchung.import_mandatsreferenz
            and not sperre
            and v.mandatsreferenz != buchung.import_mandatsreferenz
        ):
            continue
        if v.empfaenger_id and v.empfaenger_id == buchung.empfaenger_id:
            kandidaten.append(v)
            continue
        if v.konto_id and v.konto_id == buchung.konto_id and _betrag_passt(v, buchung):
            kandidaten.append(v)

    if not kandidaten:
        return None

    rueckwirkend = 0
    if buchung.import_mandatsreferenz and not sperre:
        rueckwirkend = (
            db.query(func.count(Buchung.id))
            .filter(
                Buchung.import_mandatsreferenz == buchung.import_mandatsreferenz,
                Buchung.vertrag_id.is_(None),
                Buchung.id != buchung.id,
            )
            .scalar()
        ) or 0

    return VertragVorschlag(
        buchung_id=buchung.id,
        datum=buchung.datum,
        betrag=buchung.betrag,
        empfaenger=buchung.empfaenger,
        verwendungszweck=buchung.verwendungszweck or buchung.import_verwendungszweck,
        mandatsreferenz=buchung.import_mandatsreferenz,
        konto_name=buchung.konto.name if buchung.konto else None,
        # Mehrere Kandidaten heißen: keine Vorauswahl. Ein vorausgewählter
        # Vorschlag wird weggeklickt, und der Fehler fällt erst Monate später auf.
        eindeutig=False,
        referenz_lernbar=sperre is None,
        referenz_sperrgrund=sperre.grund if sperre else None,
        # Der Grund steht je Kandidat, nicht am Vorschlag: bei zwei Kandidaten
        # kann einer über den Empfänger und einer nur über den Betrag kommen.
        # "beide empfaenger_id leer" ist kein Empfängertreffer, sondern keiner.
        kandidaten=[
            _kandidat(
                v,
                "empfaenger"
                if v.empfaenger_id and v.empfaenger_id == buchung.empfaenger_id
                else "empfaenger_betrag",
            )
            for v in kandidaten
        ],
        rueckwirkend_anzahl=rueckwirkend,
    )


def _betrag_passt(vertrag: Vertrag, buchung: Buchung) -> bool:
    """Der Betrag ist Bestätigung, nie Bedingung.

    Nach einer Preiserhöhung passt er nicht mehr zur Vorlage; deshalb gilt er
    nur als Treffer, wenn es überhaupt eine aktive Rate gibt, und mit einem
    Cent Toleranz gegen Rundungen.
    """
    for rate in vertrag.raten:
        if rate.aktiv and abs((rate.betrag or 0) - buchung.betrag) < 0.01:
            return True
    return False


def _kandidat(vertrag: Vertrag, grund: str) -> VertragKandidat:
    rate = next((r for r in vertrag.raten if r.aktiv), None)
    return VertragKandidat(
        vertrag_id=vertrag.id,
        name=vertrag.name,
        anbieter=vertrag.anbieter,
        grund=grund,
        rate=rate.betrag if rate else None,
        rhythmus=rate.rhythmus if rate else None,
        gelernte_referenz=vertrag.mandatsreferenz,
    )


@router.post("/zuordnen/{buchung_id}")
def zuordnen(
    buchung_id: int,
    body: VertragZuordnen,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Ordnet eine Buchung einem Vertrag zu — oder nimmt die Zuordnung zurück.

    `vertrag_id = None` löst die Verbindung. Das Lernen der Mandatsreferenz
    wird abgelehnt, wenn der Gläubiger ein Zahlungsdienstleister ist: die
    Oberfläche bietet es dort nicht an, und ein Aufrufer, der es trotzdem
    versucht, bekommt eine Antwort statt eines stillen Dauerfehlers.
    """
    buchung = db.get(Buchung, buchung_id)
    if not buchung:
        raise HTTPException(404, "Buchung nicht gefunden")

    if body.vertrag_id is None:
        buchung.vertrag_id = None
        db.commit()
        return {"zugeordnet": 0, "referenz_gelernt": False}

    vertrag = db.get(Vertrag, body.vertrag_id)
    if not vertrag:
        raise HTTPException(404, "Vertrag nicht gefunden")

    buchung.vertrag_id = vertrag.id
    anzahl = 1
    referenz_gelernt = False

    if body.referenz_merken:
        sperre = _referenz_sperre(buchung, RegelKatalog(db))
        if sperre:
            raise HTTPException(422, sperre.grund)
        _referenz_frei(db, buchung.import_mandatsreferenz, ausser_id=vertrag.id)
        vertrag.mandatsreferenz = buchung.import_mandatsreferenz
        referenz_gelernt = True

    if body.rueckwirkend:
        if not buchung.import_mandatsreferenz:
            raise HTTPException(
                422,
                "Rückwirkend geht nur über die Mandatsreferenz. Ohne sie würden "
                "Zahlungen nach Empfänger und Betrag mitgenommen — bei zwei "
                "gleichen Verträgen die falschen.",
            )
        anzahl += db.query(Buchung).filter(
            Buchung.import_mandatsreferenz == buchung.import_mandatsreferenz,
            Buchung.vertrag_id.is_(None),
            Buchung.id != buchung.id,
        ).update({Buchung.vertrag_id: vertrag.id}, synchronize_session=False)

    db.commit()
    return {"zugeordnet": anzahl, "referenz_gelernt": referenz_gelernt}


# ── Für den Kontoauszug-Import ──────────────────────────────────────────────
def ordne_nach_referenz(db: Session, buchungen: list[Buchung]) -> int:
    """Setzt `vertrag_id`, wo die Mandatsreferenz einen Vertrag eindeutig trifft.

    Das ist der stille Teil der Zuordnung, und er darf still sein: eine
    SEPA-Mandatsreferenz ist pro Vertrag stabil und in `vertraege` UNIQUE, ein
    Treffer kann also nur einen Vertrag meinen. Alles Weichere — Empfänger,
    Betrag, Zahlungsdienstleister — wird nicht hier entschieden, sondern im
    Zuordnungs-Dialog gefragt.

    Gibt zurück, wie viele Buchungen zugeordnet wurden. Der Aufrufer committet.
    """
    referenzen = {b.import_mandatsreferenz for b in buchungen if b.import_mandatsreferenz}
    if not referenzen:
        return 0

    nach_referenz = {
        v.mandatsreferenz: v.id
        for v in db.query(Vertrag)
        .filter(Vertrag.mandatsreferenz.in_(referenzen), Vertrag.aktiv.is_(True))
        .all()
    }
    if not nach_referenz:
        return 0

    anzahl = 0
    for b in buchungen:
        if b.vertrag_id:
            continue
        vertrag_id = nach_referenz.get(b.import_mandatsreferenz or "")
        if vertrag_id:
            b.vertrag_id = vertrag_id
            anzahl += 1
    return anzahl


# ── Für die Dashboard-Erinnerungen ──────────────────────────────────────────
def sammle_fristen(db: Session, heute: date, vorlauf_tage: int = VORLAUF_TAGE) -> list[tuple[Vertrag, date]]:
    """Verträge, deren Kündigungstermin näher rückt als `vorlauf_tage`.

    Wird von `routers/erinnerungen.py` benutzt. Gerechnet, nichts gespeichert:
    der Hinweis verschwindet von selbst, sobald gekündigt oder das Laufzeitende
    weitergeschoben ist.
    """
    treffer: list[tuple[Vertrag, date]] = []
    vertraege = (
        db.query(Vertrag)
        .filter(Vertrag.aktiv.is_(True), Vertrag.gekuendigt_am.is_(None))
        .all()
    )
    for vertrag in vertraege:
        termin = kuendigungstermin(vertrag, heute)
        if termin and (termin - heute).days <= vorlauf_tage:
            treffer.append((vertrag, termin))
    treffer.sort(key=lambda paar: paar[1])
    return treffer
