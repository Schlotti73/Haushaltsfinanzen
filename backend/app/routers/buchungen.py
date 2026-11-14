import csv
import datetime
import io
import uuid
from html import escape
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from openpyxl import Workbook
from openpyxl.styles import Font
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Buchung, BuchungPosition, Geschaeft, HaushaltsbuchEintrag, ImportRegel,
    Kategorie, Konto,
)
from app.schemas import (
    BuchungBulkUpdate, BuchungCreate, BuchungFilter, BuchungListOut, BuchungOut,
    BuchungUpdate,
    HaushaltsbuchEintragOut,
)

router = APIRouter(prefix="/buchungen", tags=["buchungen"])


def _load_buchung(db: Session, buchung_id: int) -> Buchung:
    b = (
        db.query(Buchung)
        .options(selectinload(Buchung.positionen), selectinload(Buchung.haushaltsbuch_eintrag))
        .filter(Buchung.id == buchung_id)
        .first()
    )
    if not b:
        raise HTTPException(404, "Nicht gefunden")
    return b


def _apply_positionen(buchung: Buchung, positionen_data: list) -> None:
    buchung.positionen = [
        BuchungPosition(
            kategorie_id=p.kategorie_id,
            betrag=p.betrag,
            notiz=p.notiz,
        )
        for p in positionen_data
    ]


def _kategorie_teilbaum(db, kategorie_id: int) -> list[int]:
    """Die Kategorie und alle darunterliegenden Ebenen.

    Deaktivierte Unterkategorien zaehlen mit: ihre Buchungen existieren weiter,
    und wer den Elternknoten filtert, will sie sehen.
    """
    kinder: dict[int, list[int]] = {}
    for kid, eltern in db.query(Kategorie.id, Kategorie.uebergeordnet_id).all():
        if eltern is not None:
            kinder.setdefault(eltern, []).append(kid)

    ids = [kategorie_id]
    offen = [kategorie_id]
    while offen:
        ids_der_ebene = kinder.get(offen.pop(), [])
        ids.extend(ids_der_ebene)
        offen.extend(ids_der_ebene)
    return ids


def _apply_common_filters(q, db, konto_id, kategorie_id, projekt_id, quelle, suche,
                          nur_diese_kategorie=False):
    if konto_id is not None:
        q = q.filter(Buchung.konto_id == konto_id)
    if kategorie_id is not None:
        if nur_diese_kategorie:
            q = q.filter(Buchung.kategorie_id == kategorie_id)
        else:
            q = q.filter(Buchung.kategorie_id.in_(_kategorie_teilbaum(db, kategorie_id)))
    if projekt_id is not None:
        q = q.filter(Buchung.projekt_id == projekt_id)
    if quelle:
        q = q.filter(Buchung.quelle == quelle)
    if suche:
        like = f"%{suche}%"
        q = q.filter(or_(Buchung.empfaenger.ilike(like), Buchung.notiz.ilike(like)))
    return q


def _apply_zeitraum_filter(q, status, datum_von, datum_bis, geplant_ab):
    """Status- und Datumsfilter - identisch fuer Liste, Summe und Mehrfachaenderung."""
    if geplant_ab:
        # Alle gebuchten + geplante ab geplant_ab bis datum_bis
        geplant_filter = (Buchung.status == 'geplant') & (Buchung.datum >= geplant_ab)
        if datum_bis:
            geplant_filter = geplant_filter & (Buchung.datum <= datum_bis)
        return q.filter(or_(Buchung.status == 'gebucht', geplant_filter))
    if status:
        q = q.filter(Buchung.status == status)
    if datum_von:
        q = q.filter(Buchung.datum >= datum_von)
    if datum_bis:
        q = q.filter(Buchung.datum <= datum_bis)
    return q


@router.get("", response_model=BuchungListOut)
def list_buchungen(
    konto_id: Optional[int] = None,
    kategorie_id: Optional[int] = None,
    nur_diese_kategorie: bool = False,
    projekt_id: Optional[int] = None,
    status: Optional[str] = None,
    quelle: Optional[str] = None,
    datum_von: Optional[str] = None,
    datum_bis: Optional[str] = None,
    suche: Optional[str] = None,
    geplant_ab: Optional[str] = None,
    seite: int = Query(1, ge=1),
    pro_seite: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(Buchung).options(selectinload(Buchung.positionen), selectinload(Buchung.haushaltsbuch_eintrag))
    q = _apply_common_filters(q, db, konto_id, kategorie_id, projekt_id, quelle, suche,
                              nur_diese_kategorie)

    q = _apply_zeitraum_filter(q, status, datum_von, datum_bis, geplant_ab)

    # Summe auf einer sauberen Query ohne selectinload berechnen
    summe_query = db.query(Buchung)
    summe_query = _apply_common_filters(summe_query, db, konto_id, kategorie_id, projekt_id,
                                        quelle, suche, nur_diese_kategorie)
    summe_query = _apply_zeitraum_filter(summe_query, status, datum_von, datum_bis, geplant_ab)

    gesamt = q.count()
    summe = round(summe_query.with_entities(func.sum(Buchung.betrag)).scalar() or 0.0, 2)
    items = q.order_by(Buchung.datum.desc(), Buchung.empfaenger.asc().nulls_last(), Buchung.id.desc()).offset((seite - 1) * pro_seite).limit(pro_seite).all()
    return BuchungListOut(gesamt=gesamt, summe=summe, seite=seite, pro_seite=pro_seite, items=items)


@router.get("/empfaenger", response_model=list[str])
def list_empfaenger(db: Session = Depends(get_db), _=Depends(get_current_user)):
    rows = (
        db.query(Buchung.empfaenger)
        .filter(Buchung.empfaenger.isnot(None), Buchung.empfaenger != "")
        .distinct()
        .order_by(Buchung.empfaenger)
        .all()
    )
    return [r[0] for r in rows]


@router.get("/notiz-vorschlaege", response_model=list[str])
def notiz_vorschlaege(db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Werte für die Auswahlliste am Notiz-Feld.

    Vereint die definierten Händlernamen (Import-Regeln + Geschäfte) mit den
    bereits vergebenen Notizen. Ohne die definierten Namen tippt man beim
    manuellen Nachpflegen Varianten daneben – und genau deren Vereinheitlichung
    ist der Zweck der Regeln. Ohne die vorhandenen Notizen wiederum gingen die
    gewachsenen Einträge verloren.
    """
    werte: list[str] = []
    gesehen: set[str] = set()

    def ergaenze(wert: Optional[str]) -> None:
        text = (wert or "").strip()
        if text and text.lower() not in gesehen:
            gesehen.add(text.lower())
            werte.append(text)

    for regel in (
        db.query(ImportRegel)
        .filter(ImportRegel.aktiv.is_(True), ImportRegel.stufe == "haendler")
        .order_by(ImportRegel.name)
        .all()
    ):
        ergaenze(regel.notiz_text or regel.name)

    for (name,) in (
        db.query(Geschaeft.name).filter(Geschaeft.aktiv.is_(True)).order_by(Geschaeft.name).all()
    ):
        ergaenze(name)

    for (notiz,) in (
        db.query(Buchung.notiz)
        .filter(Buchung.notiz.isnot(None), Buchung.notiz != "")
        .distinct()
        .order_by(Buchung.notiz)
        .all()
    ):
        ergaenze(notiz)

    return werte


def _export_zeilen(db, konto_id, kategorie_id, projekt_id, status, quelle, datum_von, datum_bis,
                   suche, geplant_ab, nur_diese_kategorie=False):
    """Alle gefilterten Buchungen (ohne Paginierung) als flache Zeilen."""
    q = db.query(Buchung)
    q = _apply_common_filters(q, db, konto_id, kategorie_id, projekt_id, quelle, suche,
                              nur_diese_kategorie)
    q = _apply_zeitraum_filter(q, status, datum_von, datum_bis, geplant_ab)
    buchungen = q.order_by(Buchung.datum.desc(), Buchung.empfaenger.asc().nulls_last(), Buchung.id.desc()).all()

    kat = {k.id: k.name for k in db.query(Kategorie).all()}
    kon = {k.id: k.name for k in db.query(Konto).all()}
    return [
        {
            "Datum": b.datum,
            "Empfaenger": b.empfaenger or "",
            "Kategorie": kat.get(b.kategorie_id, ""),
            "Konto": kon.get(b.konto_id, ""),
            "Betrag": round(b.betrag, 2),
            "Status": b.status,
            "Quelle": b.quelle,
            "Notiz": b.notiz or "",
        }
        for b in buchungen
    ]


def _filter_beschreibung(db, konto_id, kategorie_id, status, datum_von, datum_bis, suche,
                         geplant_ab, nur_diese_kategorie=False):
    """Aktive Filter im Klartext - damit die Datei spaeter nachvollziehbar bleibt."""
    teile = []
    if konto_id:
        k = db.get(Konto, konto_id)
        teile.append(f"Konto: {k.name if k else konto_id}")
    if kategorie_id:
        k = db.get(Kategorie, kategorie_id)
        zusatz = "" if nur_diese_kategorie else " (mit Unterkategorien)"
        teile.append(f"Kategorie: {k.name if k else kategorie_id}{zusatz}")
    if status:
        teile.append(f"Status: {status}")
    if geplant_ab:
        teile.append(f"inkl. geplanter ab {geplant_ab}")
    if datum_von:
        teile.append(f"von {datum_von}")
    if datum_bis:
        teile.append(f"bis {datum_bis}")
    if suche:
        teile.append(f"Suche: {suche}")
    return "; ".join(teile) or "ohne Filter"


@router.get("/export")
def export_buchungen(
    format: str = Query("csv", pattern="^(csv|xlsx|html)$"),
    konto_id: Optional[int] = None,
    kategorie_id: Optional[int] = None,
    nur_diese_kategorie: bool = False,
    projekt_id: Optional[int] = None,
    status: Optional[str] = None,
    quelle: Optional[str] = None,
    datum_von: Optional[str] = None,
    datum_bis: Optional[str] = None,
    suche: Optional[str] = None,
    geplant_ab: Optional[str] = None,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Die gefilterte Ansicht als CSV oder Excel - alle Treffer, nicht nur die Seite."""
    zeilen = _export_zeilen(db, konto_id, kategorie_id, projekt_id, status, quelle,
                            datum_von, datum_bis, suche, geplant_ab, nur_diese_kategorie)
    beschreibung = _filter_beschreibung(db, konto_id, kategorie_id, status, datum_von,
                                        datum_bis, suche, geplant_ab, nur_diese_kategorie)
    summe = round(sum(z["Betrag"] for z in zeilen), 2)
    spalten = ["Datum", "Empfaenger", "Kategorie", "Konto", "Betrag", "Status", "Quelle", "Notiz"]
    stand = datetime.date.today().isoformat()

    if format == "csv":
        out = io.StringIO()
        out.write(f"Buchungen;{beschreibung};Stand {stand}\n")
        w = csv.DictWriter(out, fieldnames=spalten, delimiter=";", lineterminator="\n")
        w.writeheader()
        for z in zeilen:
            # Komma als Dezimaltrenner, damit Excel-DE die Betraege als Zahl liest
            w.writerow({**z, "Betrag": f"{z['Betrag']:.2f}".replace(".", ",")})
        out.write(f"Summe;;;;{summe:.2f}".replace(".", ",") + ";;;\n")
        return StreamingResponse(
            iter([out.getvalue().encode("utf-8-sig")]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=buchungen_{stand}.csv"},
        )

    if format == "html":
        # Druckansicht statt serverseitigem PDF: kein zusaetzliches Paket, und der
        # Browser speichert daraus ein PDF. Enthaelt alle Treffer, nicht nur die
        # angezeigte Seite.
        def td(wert, rechts=False, rot=False):
            stil = []
            if rechts:
                stil.append("text-align:right")
            if rot:
                stil.append("color:#b91c1c")
            return f'<td style="{";".join(stil)}">{escape(str(wert))}</td>'

        zeilen_html = "".join(
            "<tr>"
            + td(z["Datum"]) + td(z["Empfaenger"]) + td(z["Kategorie"]) + td(z["Konto"])
            + td(f"{z['Betrag']:.2f}".replace(".", ","), rechts=True, rot=z["Betrag"] < 0)
            + td(z["Status"]) + td(z["Notiz"])
            + "</tr>"
            for z in zeilen
        )
        html = f"""<!doctype html>
<html lang="de"><head><meta charset="utf-8"><title>Buchungen {stand}</title>
<style>
  body {{ font-family: system-ui, sans-serif; font-size: 11px; margin: 16px; color: #111827; }}
  h1 {{ font-size: 15px; margin: 0 0 2px; }}
  .filter {{ color: #6b7280; margin-bottom: 10px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; border-bottom: 1px solid #9ca3af; padding: 3px 5px; font-size: 10px;
        text-transform: uppercase; color: #4b5563; }}
  td {{ padding: 3px 5px; border-bottom: 1px solid #e5e7eb; }}
  tfoot td {{ font-weight: 600; border-top: 1px solid #9ca3af; border-bottom: none; }}
  @media print {{ body {{ margin: 0; }} thead {{ display: table-header-group; }} }}
</style></head>
<body onload="window.print()">
  <h1>Buchungen ({len(zeilen)})</h1>
  <div class="filter">{escape(beschreibung)} &middot; Stand {stand}</div>
  <table>
    <thead><tr><th>Datum</th><th>Empf&auml;nger</th><th>Kategorie</th><th>Konto</th>
      <th style="text-align:right">Betrag</th><th>Status</th><th>Notiz</th></tr></thead>
    <tbody>{zeilen_html}</tbody>
    <tfoot><tr><td colspan="4">Summe</td>
      <td style="text-align:right">{f"{summe:.2f}".replace(".", ",")}</td><td></td><td></td></tr></tfoot>
  </table>
</body></html>"""
        return HTMLResponse(html)

    wb = Workbook()
    ws = wb.active
    ws.title = "Buchungen"
    ws.append([f"Buchungen - {beschreibung} - Stand {stand}"])
    ws["A1"].font = Font(bold=True)
    ws.append(spalten)
    for c in ws[2]:
        c.font = Font(bold=True)
    for z in zeilen:
        ws.append([z[s] for s in spalten])
    ws.append(["Summe", "", "", "", summe, "", "", ""])
    for c in ws[ws.max_row]:
        c.font = Font(bold=True)
    for zeile in ws.iter_rows(min_row=3, min_col=5, max_col=5):
        for c in zeile:
            c.number_format = "#,##0.00"
    for spalte, breite in zip("ABCDEFGH", (11, 30, 24, 14, 12, 9, 12, 30)):
        ws.column_dimensions[spalte].width = breite
    ws.freeze_panes = "A3"

    puffer = io.BytesIO()
    wb.save(puffer)
    puffer.seek(0)
    return StreamingResponse(
        puffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=buchungen_{stand}.xlsx"},
    )


@router.get("/{buchung_id}", response_model=BuchungOut)
def get_buchung(buchung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _load_buchung(db, buchung_id)


@router.post("", response_model=BuchungOut, status_code=201)
def create_buchung(body: BuchungCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    data = body.model_dump(exclude={"positionen"})
    buchung = Buchung(**data, erstellt_von=user.id)
    db.add(buchung)
    db.flush()
    _apply_positionen(buchung, body.positionen)
    db.commit()
    return _load_buchung(db, buchung.id)


@router.patch("/bulk")
def update_buchungen_bulk(body: BuchungBulkUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Kategorie, Empfaenger oder Status fuer viele Buchungen auf einmal setzen."""
    felder = {
        f: getattr(body, f)
        for f in ("kategorie_id", "empfaenger_id", "empfaenger", "status")
        if f in body.model_fields_set
    }
    if not felder:
        raise HTTPException(400, "Kein zu aenderndes Feld angegeben")
    if felder.get("status") not in (None, "gebucht", "geplant"):
        raise HTTPException(400, "Status muss 'gebucht' oder 'geplant' sein")

    q = db.query(Buchung)
    if body.alle_gefilterten:
        f = body.filter or BuchungFilter()
        q = _apply_common_filters(q, db, f.konto_id, f.kategorie_id, f.projekt_id, f.quelle,
                                  f.suche, f.nur_diese_kategorie)
        q = _apply_zeitraum_filter(q, f.status, f.datum_von, f.datum_bis, f.geplant_ab)
    elif body.ids:
        q = q.filter(Buchung.id.in_(body.ids))
    else:
        return {"geaendert": 0}

    anzahl = q.update(felder, synchronize_session=False)
    db.commit()
    return {"geaendert": anzahl}


@router.patch("/{buchung_id}", response_model=BuchungOut)
def update_buchung(buchung_id: int, body: BuchungUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    buchung = _load_buchung(db, buchung_id)
    data = body.model_dump(exclude_none=True, exclude={"positionen"})
    for field, val in data.items():
        setattr(buchung, field, val)
    if body.positionen is not None:
        _apply_positionen(buchung, body.positionen)
    db.commit()
    return _load_buchung(db, buchung_id)


@router.delete("/bulk", status_code=204)
def delete_buchungen_bulk(ids: list[int] = Body(...), db: Session = Depends(get_db), _=Depends(get_current_user)):
    if not ids:
        return
    db.query(Buchung).filter(Buchung.id.in_(ids)).delete(synchronize_session=False)
    db.commit()


@router.delete("/{buchung_id}", status_code=204)
def delete_buchung(buchung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    buchung = db.get(Buchung, buchung_id)
    if not buchung:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(buchung)
    db.commit()


# ── 7.3 Transfer-Verknüpfung ─────────────────────────────────────────────────

@router.get("/{buchung_id}/transfer-kandidaten")
def transfer_kandidaten(
    buchung_id: int,
    tage_toleranz: int = Query(7, ge=0, le=30),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Findet mögliche Gegenbuchungen (Betrag negiert, Datum ±tage_toleranz, andere Konten)."""
    b = db.get(Buchung, buchung_id)
    if not b:
        raise HTTPException(404, "Nicht gefunden")

    ziel_betrag = -b.betrag
    kandidaten = (
        db.query(Buchung)
        .filter(
            Buchung.id != buchung_id,
            func.abs(Buchung.betrag - ziel_betrag) < 0.005,
            Buchung.datum.between(
                _tag_offset(b.datum, -tage_toleranz),
                _tag_offset(b.datum, +tage_toleranz),
            ),
            Buchung.ist_transfer == False,
        )
        .order_by(Buchung.datum)
        .limit(20)
        .all()
    )
    return [{"id": k.id, "datum": k.datum, "betrag": k.betrag, "empfaenger": k.empfaenger, "konto_id": k.konto_id} for k in kandidaten]


@router.post("/{buchung_id}/transfer-verknuepfen", response_model=BuchungOut)
def transfer_verknuepfen(
    buchung_id: int,
    gegenbuchung_id: int = Query(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Markiert zwei Buchungen als Transfer-Paar."""
    b1 = _load_buchung(db, buchung_id)
    b2 = _load_buchung(db, gegenbuchung_id)
    if abs(b1.betrag + b2.betrag) >= 0.005:
        raise HTTPException(400, "Beträge müssen sich auf 0 aufheben")

    b1.ist_transfer = True
    b1.gegenbuchung_id = b2.id
    b2.ist_transfer = True
    b2.gegenbuchung_id = b1.id
    db.commit()
    return _load_buchung(db, buchung_id)


@router.post("/{buchung_id}/transfer-neu", response_model=BuchungOut)
def transfer_neu(
    buchung_id: int,
    zielkonto_id: int = Query(...),
    kategorie_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Erstellt eine neue Gegenbuchung auf dem Zielkonto und verknüpft beide als Transfer-Paar."""
    b = _load_buchung(db, buchung_id)
    gegen = Buchung(
        konto_id=zielkonto_id,
        datum=b.datum,
        betrag=-b.betrag,
        empfaenger=b.empfaenger,
        kategorie_id=kategorie_id,
        status="gebucht",
        quelle="manuell",
        erstellt_von=current_user.id,
        ist_transfer=True,
    )
    db.add(gegen)
    db.flush()
    b.ist_transfer = True
    b.gegenbuchung_id = gegen.id
    gegen.gegenbuchung_id = b.id
    db.commit()
    return _load_buchung(db, buchung_id)


@router.post("/{buchung_id}/transfer-loesen", response_model=BuchungOut)
def transfer_loesen(buchung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    b = _load_buchung(db, buchung_id)
    if b.gegenbuchung_id:
        gegen = db.get(Buchung, b.gegenbuchung_id)
        if gegen:
            gegen.ist_transfer = False
            gegen.gegenbuchung_id = None
    b.ist_transfer = False
    b.gegenbuchung_id = None
    db.commit()
    return _load_buchung(db, buchung_id)


# ── 7.1 Haushaltsbuch-Verknüpfung ────────────────────────────────────────────

@router.get("/{buchung_id}/hh-eintrag", response_model=HaushaltsbuchEintragOut)
def get_hh_eintrag(buchung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Gibt den HaushaltsbuchEintrag zurück, der zu dieser Buchung gehört (quelle='haushaltsbuch')."""
    eintrag = db.query(HaushaltsbuchEintrag).filter(HaushaltsbuchEintrag.buchung_id == buchung_id).first()
    if not eintrag:
        raise HTTPException(404, "Kein Haushaltsbuch-Eintrag für diese Buchung")
    return eintrag


@router.post("/{buchung_id}/hh-selbst-bestaetigen", response_model=HaushaltsbuchEintragOut)
def hh_selbst_bestaetigen(buchung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Markiert den zugehörigen HaushaltsbuchEintrag als 'verknuepft', ohne eine externe Bank-Buchung."""
    eintrag = db.query(HaushaltsbuchEintrag).filter(HaushaltsbuchEintrag.buchung_id == buchung_id).first()
    if not eintrag:
        raise HTTPException(404, "Kein Haushaltsbuch-Eintrag für diese Buchung")
    if eintrag.abgleich_status == "bar_ohne_konto":
        raise HTTPException(400, "Bar-Buchungen benötigen keinen Abgleich")
    eintrag.abgleich_status = "verknuepft"
    db.commit()
    return eintrag

@router.get("/{buchung_id}/hh-kandidaten")
def hh_kandidaten(
    buchung_id: int,
    tage_toleranz: int = Query(7, ge=0, le=30),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Findet passende Gegenbuchungen zur HH-Verknüpfung.

    Richtung:
      - Ist die Buchung eine Haushaltsbuch-Buchung → suche passende Import-/Manuell-Buchungen.
      - Sonst (Import, manuell) → suche passende Haushaltsbuch-Buchungen.
    """
    b = db.get(Buchung, buchung_id)
    if not b:
        raise HTTPException(404, "Nicht gefunden")

    # 5 % Betragstoleränz, mindestens 0,50 €
    tol = max(abs(b.betrag) * 0.05, 0.50)

    if b.quelle == "haushaltsbuch":
        # Suche nach passenden Bank-/Import-/Manuell-Buchungen
        quelle_filter = Buchung.quelle.in_(["import", "manuell"])
    else:
        # Suche nach passenden Haushaltsbuch-Buchungen
        quelle_filter = Buchung.quelle == "haushaltsbuch"

    kandidaten = (
        db.query(Buchung)
        .filter(
            Buchung.id != buchung_id,
            quelle_filter,
            Buchung.betrag.between(b.betrag - tol, b.betrag + tol),
            Buchung.datum.between(
                _tag_offset(b.datum, -tage_toleranz),
                _tag_offset(b.datum, +tage_toleranz),
            ),
            Buchung.verknuepft_mit_id.is_(None),
        )
        .order_by(Buchung.datum)
        .limit(10)
        .all()
    )
    return [{"id": k.id, "datum": k.datum, "betrag": k.betrag, "empfaenger": k.empfaenger} for k in kandidaten]


@router.post("/{buchung_id}/hh-verknuepfen", response_model=BuchungOut)
def hh_verknuepfen(
    buchung_id: int,
    hh_id: int = Query(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    b = _load_buchung(db, buchung_id)
    hh = db.get(Buchung, hh_id)
    if not hh:
        raise HTTPException(404, "Haushaltsbuch-Buchung nicht gefunden")

    b.verknuepft_mit_id = hh_id
    b.verknuepfung_typ = "haushaltsbuch"
    hh.verknuepft_mit_id = buchung_id
    hh.verknuepfung_typ = "kontoauszug"
    # HaushaltsbuchEintrag auf "verknuepft" setzen, falls vorhanden
    if hh.haushaltsbuch_eintrag:
        hh.haushaltsbuch_eintrag.abgleich_status = "verknuepft"
    db.commit()
    return _load_buchung(db, buchung_id)


@router.post("/{buchung_id}/hh-loesen", response_model=BuchungOut)
def hh_loesen(buchung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    b = _load_buchung(db, buchung_id)
    if b.verknuepft_mit_id:
        andere = db.get(Buchung, b.verknuepft_mit_id)
        if andere:
            andere.verknuepft_mit_id = None
            andere.verknuepfung_typ = None
            # HaushaltsbuchEintrag-Status zurücksetzen
            if andere.haushaltsbuch_eintrag:
                ehe = andere.haushaltsbuch_eintrag
                ehe.abgleich_status = "bar_ohne_konto" if ehe.bezahlart == "bar" else "offen"
    b.verknuepft_mit_id = None
    b.verknuepfung_typ = None
    db.commit()
    return _load_buchung(db, buchung_id)


def _tag_offset(datum_iso: str, tage: int) -> str:
    from datetime import date, timedelta
    d = date.fromisoformat(datum_iso)
    return (d + timedelta(days=tage)).isoformat()
