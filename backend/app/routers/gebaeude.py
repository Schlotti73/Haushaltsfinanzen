"""Gebäude, Zähler, Ablesungen und Nebenkosten.

Gespeichert werden Zählerstände, der Verbrauch wird immer berechnet. Kosten
kommen automatisch aus den Buchungen der Kategorie, die am Zähler bzw. am
Gebäude hinterlegt ist – es gibt also keine zweite Buchführung neben den
Buchungen.
"""

import shutil
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.models import (
    Buchung, Gebaeude, GebaeudeKostenkategorie, Kategorie, Zaehler, ZaehlerAblesung,
)
from app.schemas import (
    AblesungCreate, AblesungOut, AblesungUpdate, GebaeudeCreate,
    GebaeudeJahresuebersicht, GebaeudeKostenkategorieOut, GebaeudeOut, GebaeudeUpdate,
    KostenPosten, OffeneAblesungen, VerbrauchJahr, VerbrauchReihe, ZaehlerCreate,
    ZaehlerOut, ZaehlerUpdate,
)

router = APIRouter(prefix="/gebaeude", tags=["gebaeude"])


# ── Gebäude ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[GebaeudeOut])
def list_gebaeude(nur_aktiv: bool = True, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Gebaeude)
    if nur_aktiv:
        q = q.filter(Gebaeude.aktiv == True)  # noqa: E712
    gebaeude = q.order_by(Gebaeude.name).all()

    # Zaehler und Ablesungen je Gebaeude zaehlen - der Loesch-Dialog nennt sie,
    # damit niemand versehentlich eine Verbrauchshistorie wegwirft.
    zaehler_je_gebaeude = dict(
        db.query(Zaehler.gebaeude_id, func.count(Zaehler.id)).group_by(Zaehler.gebaeude_id).all()
    )
    ablesungen_je_gebaeude = dict(
        db.query(Zaehler.gebaeude_id, func.count(ZaehlerAblesung.id))
        .join(ZaehlerAblesung, ZaehlerAblesung.zaehler_id == Zaehler.id)
        .group_by(Zaehler.gebaeude_id).all()
    )

    return [
        GebaeudeOut.model_validate(g).model_copy(update={
            "zaehler_anzahl": zaehler_je_gebaeude.get(g.id, 0),
            "ablesungen_anzahl": ablesungen_je_gebaeude.get(g.id, 0),
        })
        for g in gebaeude
    ]


@router.post("", response_model=GebaeudeOut, status_code=201)
def create_gebaeude(body: GebaeudeCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    g = Gebaeude(**body.model_dump())
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


@router.patch("/{gebaeude_id}", response_model=GebaeudeOut)
def update_gebaeude(gebaeude_id: int, body: GebaeudeUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    g = db.get(Gebaeude, gebaeude_id)
    if not g:
        raise HTTPException(404, "Nicht gefunden")
    for feld, wert in body.model_dump(exclude_none=True).items():
        setattr(g, feld, wert)
    db.commit()
    db.refresh(g)
    return g


@router.delete("/{gebaeude_id}", status_code=204)
def delete_gebaeude(gebaeude_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    g = db.get(Gebaeude, gebaeude_id)
    if not g:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(g)
    db.commit()
    # Die Beleg-Zeilen raeumt die Kaskade ab, die Fotodateien nicht.
    shutil.rmtree(settings.belege_dir / f"gebaeude-{gebaeude_id}", ignore_errors=True)


# ── Zähler ──────────────────────────────────────────────────────────────────

@router.get("/{gebaeude_id}/zaehler", response_model=List[ZaehlerOut])
def list_zaehler(gebaeude_id: int, nur_aktiv: bool = False, db: Session = Depends(get_db), _=Depends(get_current_user)):
    q = db.query(Zaehler).filter(Zaehler.gebaeude_id == gebaeude_id)
    if nur_aktiv:
        q = q.filter(Zaehler.aktiv == True)  # noqa: E712
    return q.order_by(Zaehler.sortierung, Zaehler.name).all()


def _pruefe_zaehler(db: Session, z: Zaehler) -> None:
    """Prüft die Verknüpfungen eines Zählers, bevor er gespeichert wird.

    Eine Kategorie darf nicht gleichzeitig am Zähler und als Nebenkosten-Kategorie
    des Gebäudes hängen - sie würde in Tabelle und Diagrammen doppelt zählen.
    Der Gegenzähler muss ein Bezugszähler derselben Art im selben Gebäude sein;
    bei einem Bezugszähler hat das Feld keine Bedeutung und wird geleert.
    """
    if z.kategorie_id:
        doppelt = (db.query(GebaeudeKostenkategorie)
                   .filter(GebaeudeKostenkategorie.gebaeude_id == z.gebaeude_id,
                           GebaeudeKostenkategorie.kategorie_id == z.kategorie_id).first())
        if doppelt:
            raise HTTPException(400, "Diese Kategorie ist beim Gebäude schon als Nebenkosten-"
                                     "Kategorie hinterlegt. Dort entfernen oder hier eine andere wählen.")

    if z.richtung != "einspeisung":
        z.gegenzaehler_id = None
        return

    if z.gegenzaehler_id is None:
        return
    if z.gegenzaehler_id == z.id:
        raise HTTPException(400, "Ein Zähler kann nicht mit sich selbst verrechnet werden")
    gegen = db.get(Zaehler, z.gegenzaehler_id)
    if not gegen:
        raise HTTPException(404, "Gegenzähler nicht gefunden")
    if gegen.gebaeude_id != z.gebaeude_id:
        raise HTTPException(400, "Der Gegenzähler muss zum selben Gebäude gehören")
    if gegen.art != z.art:
        raise HTTPException(400, f"Der Gegenzähler muss die Art '{z.art}' haben")
    if gegen.richtung != "bezug":
        raise HTTPException(400, "Verrechnet wird mit einem Bezugszähler, nicht mit einer Einspeisung")


@router.post("/zaehler", response_model=ZaehlerOut, status_code=201)
def create_zaehler(body: ZaehlerCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not db.get(Gebaeude, body.gebaeude_id):
        raise HTTPException(404, "Gebäude nicht gefunden")
    z = Zaehler(**body.model_dump())
    _pruefe_zaehler(db, z)
    db.add(z)
    db.commit()
    db.refresh(z)
    return z


@router.patch("/zaehler/{zaehler_id}", response_model=ZaehlerOut)
def update_zaehler(zaehler_id: int, body: ZaehlerUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    z = db.get(Zaehler, zaehler_id)
    if not z:
        raise HTTPException(404, "Nicht gefunden")
    for feld, wert in body.model_dump(exclude_unset=True).items():
        setattr(z, feld, wert)
    _pruefe_zaehler(db, z)
    db.commit()
    db.refresh(z)
    return z


@router.delete("/zaehler/{zaehler_id}", status_code=204)
def delete_zaehler(zaehler_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    z = db.get(Zaehler, zaehler_id)
    if not z:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(z)
    db.commit()


@router.post("/zaehler/{zaehler_id}/wechsel", response_model=ZaehlerOut, status_code=201)
def zaehlerwechsel(
    zaehler_id: int,
    datum: str = Query(..., description="Tag des Wechsels"),
    endstand_alt: float = Query(...),
    anfangsstand_neu: float = Query(0.0),
    seriennummer_neu: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    """Zähler austauschen: alter Zähler wird abgeschlossen, neuer legt an.

    Der Jahresverbrauch des Wechseljahrs setzt sich danach aus beiden Zählern
    zusammen (siehe _reihe_verbrauch), ohne dass Historie verbogen wird.
    """
    alt = db.get(Zaehler, zaehler_id)
    if not alt:
        raise HTTPException(404, "Nicht gefunden")
    if alt.gueltig_bis:
        raise HTTPException(400, "Dieser Zähler wurde bereits ersetzt")

    jahr = int(datum[:4])
    alt.gueltig_bis = datum
    db.add(ZaehlerAblesung(zaehler_id=alt.id, datum=datum, jahr=jahr, stand=endstand_alt,
                           art="jahr", notiz="Endstand bei Zählerwechsel"))

    neu = Zaehler(
        gebaeude_id=alt.gebaeude_id, name=alt.name, seriennummer=seriennummer_neu,
        art=alt.art, einheit=alt.einheit, richtung=alt.richtung, sortierung=alt.sortierung,
        uebergeordneter_zaehler_id=alt.uebergeordneter_zaehler_id, kategorie_id=alt.kategorie_id,
        gegenzaehler_id=alt.gegenzaehler_id,
        gueltig_ab=datum, ersetzt_zaehler_id=alt.id,
    )
    db.add(neu)
    db.flush()

    # Einspeisezaehler, die mit dem alten Zaehler verrechnet wurden, zeigen auf
    # den neuen. Die Uebersicht loest das ueber die Kette ohnehin auf, aber die
    # DB soll nicht auf einen stillgelegten Zaehler zeigen.
    for zeigend in db.query(Zaehler).filter(Zaehler.gegenzaehler_id == alt.id).all():
        zeigend.gegenzaehler_id = neu.id
    db.add(ZaehlerAblesung(zaehler_id=neu.id, datum=datum, jahr=jahr, stand=anfangsstand_neu,
                           art="zwischen", notiz="Anfangsstand neuer Zähler"))
    db.commit()
    db.refresh(neu)
    return neu


# ── Ablesungen ──────────────────────────────────────────────────────────────

@router.get("/zaehler/{zaehler_id}/ablesungen", response_model=List[AblesungOut])
def list_ablesungen(zaehler_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return (db.query(ZaehlerAblesung)
            .filter(ZaehlerAblesung.zaehler_id == zaehler_id)
            .order_by(ZaehlerAblesung.jahr.desc(), ZaehlerAblesung.datum.desc())
            .all())


@router.post("/ablesungen", response_model=AblesungOut, status_code=201)
def create_ablesung(body: AblesungCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    zaehler = db.get(Zaehler, body.zaehler_id)
    if not zaehler:
        raise HTTPException(404, "Zähler nicht gefunden")
    daten = body.model_dump()
    # Abrechnungsjahr aus dem Datum vorbelegen - eine Ablesung am 03.01. gehoert
    # je nach Pflege ins Vorjahr, deshalb bleibt das Feld aenderbar.
    if daten.get("jahr") is None:
        daten["jahr"] = int(body.datum[:4])
    a = ZaehlerAblesung(**daten)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


@router.patch("/ablesungen/{ablesung_id}", response_model=AblesungOut)
def update_ablesung(ablesung_id: int, body: AblesungUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    a = db.get(ZaehlerAblesung, ablesung_id)
    if not a:
        raise HTTPException(404, "Nicht gefunden")
    for feld, wert in body.model_dump(exclude_none=True).items():
        setattr(a, feld, wert)
    db.commit()
    db.refresh(a)
    return a


@router.delete("/ablesungen/{ablesung_id}", status_code=204)
def delete_ablesung(ablesung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    a = db.get(ZaehlerAblesung, ablesung_id)
    if not a:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(a)
    db.commit()


@router.get("/ablesungen/pruefung")
def pruefe_stand(
    zaehler_id: int,
    jahr: int,
    stand: float,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Plausibilitaetshinweis, keine Sperre: fallender Stand oder Ausreisser."""
    vorher = (db.query(ZaehlerAblesung)
              .filter(ZaehlerAblesung.zaehler_id == zaehler_id,
                      ZaehlerAblesung.art == "jahr",
                      ZaehlerAblesung.jahr < jahr)
              .order_by(ZaehlerAblesung.jahr.desc()).limit(2).all())
    if not vorher:
        return {"hinweis": None}
    letzter = vorher[0]
    if stand < letzter.stand:
        return {"hinweis": f"Der Stand liegt unter dem von {letzter.jahr} ({letzter.stand:g}). "
                           f"Wurde der Zähler gewechselt?"}
    if len(vorher) > 1:
        vorjahresverbrauch = letzter.stand - vorher[1].stand
        neuer = stand - letzter.stand
        if vorjahresverbrauch > 0 and neuer > 2 * vorjahresverbrauch:
            return {"hinweis": f"Verbrauch {neuer:g} ist mehr als doppelt so hoch wie "
                               f"im Vorjahr ({vorjahresverbrauch:g})."}
    return {"hinweis": None}


@router.get("/ablesungen/offen", response_model=List[OffeneAblesungen])
def offene_ablesungen(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Zaehlerketten mit fehlender Jahresablesung. Siehe sammle_offene_ablesungen."""
    return sammle_offene_ablesungen(db)


def sammle_offene_ablesungen(db: Session) -> List[OffeneAblesungen]:
    """Zaehlerketten, denen zwischen erster und letzter faelliger Jahresablesung
    eine fehlt.

    Faellig ist bis zum Vorjahr: die Ablesung fuer das laufende Jahr steht erst
    zum Jahreswechsel an. Deaktivierte Gebaeude und stillgelegte Zaehler bleiben
    aussen vor - dafuer ist der Aktiv-Schalter da.
    """
    letztes_faelliges_jahr = date.today().year - 1

    gebaeude = {g.id: g for g in db.query(Gebaeude).filter(Gebaeude.aktiv == True).all()}  # noqa: E712
    if not gebaeude:
        return []

    zaehler = db.query(Zaehler).filter(Zaehler.gebaeude_id.in_(gebaeude)).order_by(
        Zaehler.sortierung, Zaehler.name).all()
    if not zaehler:
        return []

    jahre_je_zaehler: dict[int, set[int]] = {}
    for a in db.query(ZaehlerAblesung).filter(
            ZaehlerAblesung.zaehler_id.in_([z.id for z in zaehler]),
            ZaehlerAblesung.art == "jahr").all():
        jahre_je_zaehler.setdefault(a.zaehler_id, set()).add(a.jahr)

    offen: list[OffeneAblesungen] = []
    je_gebaeude: dict[int, list[Zaehler]] = {}
    for z in zaehler:
        je_gebaeude.setdefault(z.gebaeude_id, []).append(z)

    for gebaeude_id, liste in je_gebaeude.items():
        for kette in _zaehlerketten(liste):
            aktueller = kette[-1]
            if not aktueller.aktiv:
                continue
            vorhanden: set[int] = set()
            for z in kette:
                vorhanden |= jahre_je_zaehler.get(z.id, set())
            if not vorhanden:
                continue  # noch nie abgelesen - daraus laesst sich nichts folgern

            # Ein Zaehler mit gueltig_bis ist ausgebaut: danach ist nichts mehr
            # faellig. gueltig_ab des ersten der Kette begrenzt den Anfang.
            von = min(vorhanden)
            if kette[0].gueltig_ab:
                von = max(von, int(kette[0].gueltig_ab[:4]))
            bis = letztes_faelliges_jahr
            if aktueller.gueltig_bis:
                bis = min(bis, int(aktueller.gueltig_bis[:4]))

            fehlend = [j for j in range(von, bis + 1) if j not in vorhanden]
            if fehlend:
                offen.append(OffeneAblesungen(
                    gebaeude_id=gebaeude_id, gebaeude=gebaeude[gebaeude_id].name,
                    zaehler_id=aktueller.id, zaehler=aktueller.name, jahre=fehlend,
                ))

    offen.sort(key=lambda o: (o.gebaeude, o.zaehler))
    return offen


# ── Verbrauch und Kosten ────────────────────────────────────────────────────

def _zaehlerketten(zaehler: list[Zaehler]) -> list[list[Zaehler]]:
    """Gruppiert Zähler zu Ketten: Vorgänger + Nachfolger gehören zusammen."""
    nach_vorgaenger = {z.ersetzt_zaehler_id: z for z in zaehler if z.ersetzt_zaehler_id}
    ketten = []
    for z in zaehler:
        if z.ersetzt_zaehler_id:
            continue  # kein Kettenanfang
        kette = [z]
        while kette[-1].id in nach_vorgaenger:
            kette.append(nach_vorgaenger[kette[-1].id])
        ketten.append(kette)
    return ketten


def _reihe_verbrauch(kette: list[Zaehler], ablesungen: dict[int, list[ZaehlerAblesung]]) -> dict[int, VerbrauchJahr]:
    """Jahresverbrauch einer Zählerkette.

    Innerhalb eines Zählers ist der Verbrauch die Differenz zum Vorjahresstand.
    Im Wechseljahr kommt (Endstand alt - Vorjahr alt) + (Jahresstand neu -
    Anfangsstand neu) zusammen; der Anfangsstand steht als 'zwischen'-Ablesung
    am neuen Zähler und zaehlt deshalb nicht als eigener Jahreswert.
    """
    ergebnis: dict[int, VerbrauchJahr] = {}
    for z in kette:
        jahres = sorted([a for a in ablesungen.get(z.id, []) if a.art == "jahr"], key=lambda a: a.jahr)
        start = next((a for a in ablesungen.get(z.id, [])
                      if a.art == "zwischen" and a.notiz == "Anfangsstand neuer Zähler"), None)
        vorheriger_stand = start.stand if start else None
        for a in jahres:
            eintrag = ergebnis.get(a.jahr) or VerbrauchJahr(jahr=a.jahr)
            if vorheriger_stand is not None:
                teil = round(a.stand - vorheriger_stand, 3)
                eintrag.verbrauch = round((eintrag.verbrauch or 0) + teil, 3)
            if eintrag.stand is not None:
                # zweiter Zähler im selben Jahr -> Wechseljahr
                eintrag.zaehlerwechsel = True
            eintrag.stand = a.stand
            ergebnis[a.jahr] = eintrag
            vorheriger_stand = a.stand
    return ergebnis


def _kosten_je_jahr(db: Session, kategorie_ids) -> dict[int, float]:
    """Kosten dieser Kategorien je Jahr, aus den gebuchten Buchungen.

    Das Vorzeichen wird gedreht, nicht entfernt: Ausgaben stehen in den Buchungen
    negativ und sind hier positive Kosten, Einnahmen (PV-Verguetung, Gutschrift
    aus einer Nebenkostenabrechnung) bleiben als negative Kosten erhalten und
    mindern damit die Jahresbelastung. Ein abs() hier wuerde eine Einnahme in
    eine Ausgabe verwandeln.

    Mehrere Kategorien, weil eine Zaehlerkette nach einem Zaehlerwechsel aus
    Zaehlern mit unterschiedlichen Kategorien bestehen kann - sonst fehlten die
    Kosten der Jahre vor dem Wechsel.
    """
    ids = [k for k in (kategorie_ids if isinstance(kategorie_ids, (list, set, tuple)) else [kategorie_ids]) if k]
    if not ids:
        return {}
    rows = (db.query(func.substr(Buchung.datum, 1, 4), func.sum(Buchung.betrag))
            .filter(Buchung.kategorie_id.in_(ids), Buchung.status == "gebucht")
            .group_by(func.substr(Buchung.datum, 1, 4)).all())
    return {int(j): round(-(s or 0.0), 2) for j, s in rows if j}


@router.get("/{gebaeude_id}/uebersicht", response_model=GebaeudeJahresuebersicht)
def uebersicht(gebaeude_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not db.get(Gebaeude, gebaeude_id):
        raise HTTPException(404, "Gebäude nicht gefunden")

    zaehler = db.query(Zaehler).filter(Zaehler.gebaeude_id == gebaeude_id).order_by(
        Zaehler.sortierung, Zaehler.name).all()
    alle_ablesungen: dict[int, list[ZaehlerAblesung]] = {}
    if zaehler:
        for a in db.query(ZaehlerAblesung).filter(
                ZaehlerAblesung.zaehler_id.in_([z.id for z in zaehler])).all():
            alle_ablesungen.setdefault(a.zaehler_id, []).append(a)

    ketten = _zaehlerketten(zaehler)
    # Jede Reihe traegt die ID ihres aktuellen Zaehlers. Ein gegenzaehler_id kann
    # aber noch auf einen stillgelegten Vorgaenger zeigen (Zaehlerwechsel), darum
    # wird jede Zaehler-ID auf den aktuellen Zaehler ihrer Kette abgebildet.
    aktuell_je_zaehler = {z.id: kette[-1].id for kette in ketten for z in kette}

    reihen: list[VerbrauchReihe] = []
    jahre: set[int] = set()
    for kette in ketten:
        aktueller = kette[-1]
        werte = _reihe_verbrauch(kette, alle_ablesungen)
        # Kosten ueber alle Kategorien der Kette - nach einem Zaehlerwechsel mit
        # neuer Kategorie fehlten sonst die Jahre vor dem Wechsel.
        kosten = _kosten_je_jahr(db, [z.kategorie_id for z in kette])
        # Jahre sind die Vereinigung aus Ablese- und Kostenjahren: eine
        # Schlussabrechnung nach dem Ausbau oder eine Vorauszahlung vor der
        # ersten Ablesung ist eine echte Kostenposition und darf nicht daran
        # scheitern, dass es im selben Jahr keinen Zaehlerstand gibt.
        for jahr in set(werte) | set(kosten):
            eintrag = werte.get(jahr) or VerbrauchJahr(jahr=jahr)
            eintrag.kosten = kosten.get(jahr)
            if eintrag.kosten and eintrag.verbrauch:
                eintrag.preis_je_einheit = round(eintrag.kosten / eintrag.verbrauch, 4)
            werte[jahr] = eintrag
        jahre.update(werte)
        gegen = aktuell_je_zaehler.get(aktueller.gegenzaehler_id) if aktueller.gegenzaehler_id else None
        reihen.append(VerbrauchReihe(
            zaehler_id=aktueller.id, name=aktueller.name, art=aktueller.art,
            einheit=aktueller.einheit, richtung=aktueller.richtung,
            kategorie_id=aktueller.kategorie_id,
            gegenzaehler_id=gegen if gegen != aktueller.id else None,
            jahre=[werte[j] for j in sorted(werte)],
        ))

    # Gegenstueck zum gegenzaehler_id: am Bezugszaehler stehen die Namen der
    # Reihen, die in ihn verrechnet werden - das Frontend setzt daraus das Badge.
    nach_id = {r.zaehler_id: r for r in reihen}
    for r in reihen:
        if r.gegenzaehler_id and r.gegenzaehler_id in nach_id:
            ziel = nach_id[r.gegenzaehler_id]
            r.verrechnet_mit = [ziel.name]
            ziel.verrechnet_mit.append(r.name)

    sonstige: dict[int, list[KostenPosten]] = {}
    # Kategorien, die schon an einem Zaehler dieses Gebaeudes haengen, sind ueber
    # die Zaehlerreihe erfasst. Ohne diesen Filter wuerden sie doppelt zaehlen.
    an_zaehlern = {z.kategorie_id for z in zaehler if z.kategorie_id}
    zuordnungen = (db.query(GebaeudeKostenkategorie, Kategorie)
                   .join(Kategorie, GebaeudeKostenkategorie.kategorie_id == Kategorie.id)
                   .filter(GebaeudeKostenkategorie.gebaeude_id == gebaeude_id)
                   .order_by(GebaeudeKostenkategorie.sortierung, Kategorie.name).all())
    for zuordnung, kategorie in zuordnungen:
        if kategorie.id in an_zaehlern:
            continue
        for jahr, betrag in _kosten_je_jahr(db, kategorie.id).items():
            sonstige.setdefault(jahr, []).append(
                KostenPosten(kategorie_id=kategorie.id, kategorie=kategorie.name, betrag=betrag))
            jahre.add(jahr)

    return GebaeudeJahresuebersicht(
        gebaeude_id=gebaeude_id, jahre=sorted(jahre), reihen=reihen,
        sonstige_kosten={j: sorted(p, key=lambda x: x.kategorie) for j, p in sonstige.items()},
    )


@router.get("/{gebaeude_id}/kategorie-vorschlaege")
def kategorie_vorschlaege(gebaeude_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Schlaegt je Zaehler ohne Kategorie eine passende vor.

    Die Nebenkosten-Kategorien tragen die Zaehlernummer im Namen (z. B.
    "Strom EG (12345678)"), deshalb genuegt ein Abgleich der
    Seriennummer. Vorschlag bleibt Vorschlag - gesetzt wird er erst durch ein
    PATCH auf den Zaehler.
    """
    zaehler = db.query(Zaehler).filter(Zaehler.gebaeude_id == gebaeude_id).all()
    if not zaehler:
        return []
    kategorien = db.query(Kategorie).filter(Kategorie.aktiv == True).all()  # noqa: E712

    vorschlaege = []
    for z in zaehler:
        if z.kategorie_id or not z.seriennummer:
            continue
        # Ein Zaehler kann zwei Nummern tragen (alt / neu). Verglichen wird nur der
        # Ziffern-/Buchstabenkern, Zusaetze wie "(K)" stoeren sonst.
        kerne = ["".join(c for c in teil if c.isalnum()).lower() for teil in z.seriennummer.split("/")]
        kerne = [k for k in kerne if len(k) >= 6]
        if not kerne:
            continue
        treffer = next(
            (k for k in kategorien
             if any(kern in "".join(c for c in k.name if c.isalnum()).lower() for kern in kerne)),
            None,
        )
        if treffer:
            vorschlaege.append({"zaehler_id": z.id, "zaehler": z.name,
                                "kategorie_id": treffer.id, "kategorie": treffer.name})
    return vorschlaege


# ── Nebenkosten-Kategorien ohne Verbrauchsbezug ─────────────────────────────

@router.get("/{gebaeude_id}/kostenkategorien", response_model=List[GebaeudeKostenkategorieOut])
def list_kostenkategorien(gebaeude_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return (db.query(GebaeudeKostenkategorie)
            .filter(GebaeudeKostenkategorie.gebaeude_id == gebaeude_id)
            .order_by(GebaeudeKostenkategorie.sortierung).all())


@router.post("/{gebaeude_id}/kostenkategorien", response_model=GebaeudeKostenkategorieOut, status_code=201)
def add_kostenkategorie(gebaeude_id: int, kategorie_id: int = Query(...),
                        db: Session = Depends(get_db), _=Depends(require_admin)):
    if not db.get(Gebaeude, gebaeude_id):
        raise HTTPException(404, "Gebäude nicht gefunden")
    if not db.get(Kategorie, kategorie_id):
        raise HTTPException(404, "Kategorie nicht gefunden")
    # Gegenprobe zu _pruefe_zaehler: haengt die Kategorie schon an einem Zaehler
    # dieses Gebaeudes, wuerde sie doppelt als Kosten zaehlen.
    am_zaehler = (db.query(Zaehler)
                  .filter(Zaehler.gebaeude_id == gebaeude_id,
                          Zaehler.kategorie_id == kategorie_id).first())
    if am_zaehler:
        raise HTTPException(400, f'Diese Kategorie ist schon am Zähler „{am_zaehler.name}“ '
                                 f'hinterlegt und dort in den Kosten enthalten.')
    vorhanden = (db.query(GebaeudeKostenkategorie)
                 .filter(GebaeudeKostenkategorie.gebaeude_id == gebaeude_id,
                         GebaeudeKostenkategorie.kategorie_id == kategorie_id).first())
    if vorhanden:
        return vorhanden
    k = GebaeudeKostenkategorie(gebaeude_id=gebaeude_id, kategorie_id=kategorie_id)
    db.add(k)
    db.commit()
    db.refresh(k)
    return k


@router.delete("/kostenkategorien/{zuordnung_id}", status_code=204)
def delete_kostenkategorie(zuordnung_id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    k = db.get(GebaeudeKostenkategorie, zuordnung_id)
    if not k:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(k)
    db.commit()
