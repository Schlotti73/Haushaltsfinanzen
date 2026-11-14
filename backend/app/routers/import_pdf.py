"""
Kontoauszug-Import (Phase 7.2).
POST /import/pdf/vorschau  – parst PDF, zeigt Vorschau (dry-run)
POST /import/pdf/commit    – schreibt Buchungen in DB, archiviert das PDF
GET  /import/pdf/auszuege  – archivierte Auszüge eines Kontos
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import logging
import traceback

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

_log = logging.getLogger(__name__)

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Benutzer, Buchung, Konto, Kontoauszug
from app.schemas import HaushaltsbuchEintragOut
from app.services.einstellungen import betrag_toleranz, tage_toleranz
from app.services.empfaenger_match import match as match_empfaenger
from app.services.hhb_match import finde_kandidaten
from app.services.import_regel import RegelKatalog
from app.services.pdf_import.dispatcher import parse_pdf

router = APIRouter(prefix="/import/pdf", tags=["import"])

MAX_PDF_MB = 20


def _vorschau_buchungen(db: Session, konto_id: int, pdf_bytes: bytes) -> dict:
    konto = db.get(Konto, konto_id)
    if not konto:
        raise HTTPException(404, "Konto nicht gefunden")

    result = parse_pdf(pdf_bytes, db)
    if not result.buchungen and result.fehler:
        raise HTTPException(422, f"Fehler beim Parsen: {'; '.join(result.fehler)}")

    # Intra-PDF-Hashkollisionen auflösen (z.B. zwei identische Buchungen am gleichen Tag)
    _pdf_hash_zaehler: dict[str, int] = {}
    for pb in result.buchungen:
        n = _pdf_hash_zaehler.get(pb.import_hash, 0)
        _pdf_hash_zaehler[pb.import_hash] = n + 1
        if n > 0:
            pb.import_hash = f"{pb.import_hash}:{n}"

    # Duplikatcheck: hard (import_hash) und weich (Datum+Betrag±1 Tag)
    existierende_hashes = {
        row[0]
        for row in db.query(Buchung.import_hash)
        .filter(Buchung.konto_id == konto_id, Buchung.import_hash.isnot(None))
        .all()
    }

    # Konfigurierbare Toleranzen für den Abgleich gegen vorhandene Buchungen.
    tage = tage_toleranz(db)
    betrag_spanne = betrag_toleranz(db)

    # Alle vorhandenen Buchungen des Kontos im PDF-Zeitraum ± Toleranz in einer Abfrage laden
    if result.buchungen:
        alle_daten = [pb.datum for pb in result.buchungen]
        fenster_von = _tag_offset(min(alle_daten), -tage)
        fenster_bis = _tag_offset(max(alle_daten), +tage)
        db_buchungen_im_fenster: list[Buchung] = (
            db.query(Buchung)
            .filter(
                Buchung.konto_id == konto_id,
                Buchung.datum.between(fenster_von, fenster_bis),
            )
            .order_by(Buchung.datum)
            .all()
        )
    else:
        db_buchungen_im_fenster = []

    def _buchung_dict(b: Buchung) -> dict:
        return {"id": b.id, "datum": b.datum, "betrag": b.betrag,
                "empfaenger": b.empfaenger, "notiz": b.notiz}

    # Hard-Duplikat-Buchungen per Hash vorindizieren
    hash_zu_buchung: dict[str, Buchung] = {
        b.import_hash: b for b in db_buchungen_im_fenster if b.import_hash
    }

    # Von diesem PDF bereits per Hash belegte Buchungen. Zwei identische Zeilen
    # am selben Tag (gleicher Empfänger, gleicher Betrag, nur anderer
    # Verwendungszweck) teilen sich den Hash und werden oben per ":n"-Suffix
    # getrennt. Trifft davon nur eine auf eine vorhandene Buchung, taucht genau
    # diese Buchung sonst auch in der Kandidatenliste der anderen Zeile auf –
    # und ist dort als erster Eintrag sogar die Vorauswahl. Ein Treffer darauf
    # würde den bestehenden Hash überschreiben, statt die noch unverknüpfte
    # Partnerbuchung zu binden: der Abgleich kippt bei jedem Import hin und her
    # und konvergiert nie.
    pdf_hashes = {pb.import_hash for pb in result.buchungen}
    belegte_buchung_ids = {
        b.id for b in db_buchungen_im_fenster if b.import_hash in pdf_hashes
    }

    # Import-Regeln einmal laden und auf jede Zeile anwenden (Phase 16).
    katalog = RegelKatalog(db)

    vorschau = []
    for pb in result.buchungen:
        ist_duplikat_hart = pb.import_hash in existierende_hashes

        # Weiche Dublettenprüfung, zweistufig:
        #   Verdacht  – Betrag exakt, ±1 Tag. Bewusst fest verdrahtet, denn nur
        #               dieser Treffer ist scharf genug, um die Zeile von der
        #               Vorauswahl auszunehmen.
        #   Ähnlich   – Betrag/Datum innerhalb der eingestellten Toleranz. Rein
        #               informativ, die Zeile bleibt vorausgewählt.
        ist_verdacht = False
        ist_aehnlich = False
        vorhandene_buchung = None   # Einzeltreffer für Hard-Duplikate
        nahe_buchungen = []         # Alle Buchungen im Toleranzfenster für Verdacht/Neu

        if ist_duplikat_hart:
            dup = hash_zu_buchung.get(pb.import_hash) or db.query(Buchung).filter(
                Buchung.import_hash == pb.import_hash
            ).first()
            if dup:
                vorhandene_buchung = _buchung_dict(dup)
        else:
            # Nahfenster: alle Buchungen ± Tagestoleranz um diesen Eintrag
            nahe_buchungen = [
                _buchung_dict(b) for b in db_buchungen_im_fenster
                if _tag_offset(pb.datum, -tage) <= b.datum <= _tag_offset(pb.datum, +tage)
                and b.id not in belegte_buchung_ids
            ]
            ist_verdacht = any(
                b["betrag"] == pb.betrag and
                _tag_offset(pb.datum, -1) <= b["datum"] <= _tag_offset(pb.datum, +1)
                for b in nahe_buchungen
            )
            ist_aehnlich = not ist_verdacht and any(
                _betrag_aehnlich(b["betrag"], pb.betrag, betrag_spanne)
                for b in nahe_buchungen
            )

        # Import-Regeln zuerst: eine gepflegte Regel ist eine explizite Aussage,
        # der Fuzzy-Match darunter nur eine Vermutung. Ohne sie erreicht ein
        # Rohtext wie "Paypal Europe S.A.R.L. … Getranke Nord …" gegen den Namen
        # "PayPal" ohnehin nie die Schwelle von 0.85.
        regel = katalog.wende_an(pb.empfaenger, pb.verwendungszweck, pb.iban_empfaenger)
        emp = None
        if not regel.empfaenger_id:
            emp = match_empfaenger(db, pb.empfaenger, pb.iban_empfaenger)

        empfaenger_id = regel.empfaenger_id or (emp.id if emp else None)
        empfaenger_name = regel.empfaenger_name or (emp.name if emp else None)
        # Kategorie: Stufe 2 (Händler) schlägt Stufe 1 und den Empfänger-Match.
        kategorie_id = regel.kategorie_id or (emp.kategorie_id if emp else None)

        vorschau.append({
            "datum": pb.datum,
            "betrag": pb.betrag,
            "empfaenger": pb.empfaenger,
            "verwendungszweck": pb.verwendungszweck,
            "iban_empfaenger": pb.iban_empfaenger,
            "import_hash": pb.import_hash,
            "duplikat": ist_duplikat_hart,
            "duplikat_verdacht": ist_verdacht,
            "duplikat_aehnlich": ist_aehnlich,
            "vorhandene_buchung": vorhandene_buchung,
            "nahe_buchungen": nahe_buchungen,
            "empfaenger_id": empfaenger_id,
            "empfaenger_name": empfaenger_name,
            "kategorie_id": kategorie_id,
            "notiz": regel.notiz,
            # Sichtbar machen, was die Regeln umgeschrieben haben – sonst ändert
            # der Import still Felder und ein Fehlgriff fällt erst Wochen später
            # in der Statistik auf.
            "regel_hinweis": regel.hinweis(),
            "regel_geschaeft_id": regel.geschaeft_id,
        })

    return {
        "bank": result.bank,
        "konto_hinweis": result.konto_hinweis,
        "konto_id": konto_id,
        "buchungen": vorschau,
        "neu": sum(1 for b in vorschau if not b["duplikat"]),
        "duplikate": sum(1 for b in vorschau if b["duplikat"]),
        "verdaechtigt": sum(1 for b in vorschau if b["duplikat_verdacht"] and not b["duplikat"]),
        "aehnlich": sum(1 for b in vorschau if b["duplikat_aehnlich"] and not b["duplikat"]),
        # Für die Hervorhebung einzelner Kandidaten in der Vorschau-Liste
        "betrag_toleranz": betrag_spanne,
        "tage_toleranz": tage,
    }


def _tag_offset(datum_iso: str, tage: int) -> str:
    from datetime import date, timedelta
    d = date.fromisoformat(datum_iso)
    return (d + timedelta(days=tage)).isoformat()


def _betrag_aehnlich(a: float, b: float, spanne: float) -> bool:
    """Beträge liegen innerhalb der Toleranz – bei gleichem Vorzeichen.

    Ohne die Vorzeichenprüfung läge eine Ausgabe von -2 € nur 4 € von einer
    Einnahme über +2 € entfernt und würde als Treffer durchgehen.
    """
    if (a < 0) != (b < 0):
        return False
    return abs(a - b) <= spanne


# ── Archiv der importierten Auszüge ─────────────────────────────────────────
# Das PDF selbst ist der Nachweis hinter jeder importierten Zeile. Es wird
# ausschließlich beim Commit abgelegt (die Vorschau bleibt folgenlos), dann
# aber immer – auch wenn der Lauf nur Duplikate enthielt, denn ein vollständig
# doppelter Auszug ist trotzdem Archivmaterial.

def _auszug_ablegen(
    db: Session, konto_id: int, pdf_bytes: bytes, daten: dict, dateiname: str | None, user,
) -> tuple[Kontoauszug, Optional[Path]]:
    """Legt das PDF ab und liefert den Archiv-Eintrag samt neu geschriebener
    Datei (None, wenn ein vorhandener Eintrag wiederverwendet wurde – der
    Aufrufer darf dessen Datei bei einem Rollback nicht löschen).

    Derselbe Upload zum zweiten Mal (z.B. der Auffrisch-Lauf) verwendet den
    vorhandenen Eintrag wieder: gleiche Bytes, gleicher Hash, keine zweite
    Datei auf der Platte und kein zweiter scheinbar fremder Auszug in der
    Liste. Der Zeitstempel des Erstimports bleibt dabei stehen.
    """
    datei_hash = hashlib.sha256(pdf_bytes).hexdigest()
    vorhanden = (
        db.query(Kontoauszug)
        .filter(Kontoauszug.konto_id == konto_id, Kontoauszug.datei_hash == datei_hash)
        .first()
    )
    if vorhanden:
        return vorhanden, None

    # Zeitraum aus den geparsten Zeilen ableiten – die Parser lesen keinen
    # Zeitraum aus dem PDF-Kopf (siehe services/pdf_import/base.py).
    alle_daten = sorted(b["datum"] for b in daten["buchungen"])

    unterordner = str(konto_id)
    zielordner = settings.kontoauszuege_dir / unterordner
    zielordner.mkdir(parents=True, exist_ok=True)
    gespeichert = f"{uuid.uuid4().hex}.pdf"
    (zielordner / gespeichert).write_bytes(pdf_bytes)

    auszug = Kontoauszug(
        konto_id=konto_id,
        dateiname=Path(dateiname or "kontoauszug.pdf").name,
        dateipfad=f"{unterordner}/{gespeichert}",
        datei_hash=datei_hash,
        bank=daten.get("bank"),
        zeitraum_von=alle_daten[0] if alle_daten else None,
        zeitraum_bis=alle_daten[-1] if alle_daten else None,
        anzahl_buchungen=len(daten["buchungen"]),
        importiert_von=user.id,
        importiert_am=datetime.utcnow(),
    )
    db.add(auszug)
    db.flush()
    return auszug, zielordner / gespeichert


def _verwaiste_datei_entfernen(pfad: Optional[Path]) -> None:
    """Räumt die Archivdatei nach einem Rollback weg – der Tabelleneintrag
    dazu existiert dann nicht mehr und die Datei wäre für immer unerreichbar."""
    if pfad is None:
        return
    try:
        pfad.unlink(missing_ok=True)
    except OSError as fehler:  # pragma: no cover - Dateisystem-Eigenheit
        _log.warning("Verwaiste Archivdatei %s nicht entfernbar: %s", pfad, fehler)


def _auszug_holen(db: Session, auszug_id: int) -> Kontoauszug:
    auszug = db.get(Kontoauszug, auszug_id)
    if not auszug:
        raise HTTPException(404, "Kontoauszug nicht gefunden")
    return auszug


@router.get("/auszuege")
def auszuege_liste(
    konto_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Archivierte Auszüge eines Kontos, neueste zuerst."""
    auszuege = (
        db.query(Kontoauszug)
        .filter(Kontoauszug.konto_id == konto_id)
        .order_by(Kontoauszug.importiert_am.desc(), Kontoauszug.id.desc())
        .all()
    )
    namen = {
        b.id: b.name
        for b in db.query(Benutzer).filter(
            Benutzer.id.in_([a.importiert_von for a in auszuege if a.importiert_von])
        ).all()
    } if auszuege else {}
    return [
        {
            "id": a.id,
            "dateiname": a.dateiname,
            "bank": a.bank,
            "zeitraum_von": a.zeitraum_von,
            "zeitraum_bis": a.zeitraum_bis,
            "anzahl_buchungen": a.anzahl_buchungen,
            "importiert_am": a.importiert_am.isoformat(timespec="seconds"),
            "importiert_von": namen.get(a.importiert_von),
        }
        for a in auszuege
    ]


@router.get("/auszuege/{auszug_id}/datei")
def auszug_datei(
    auszug_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    auszug = _auszug_holen(db, auszug_id)
    pfad = settings.kontoauszuege_dir / auszug.dateipfad
    if not pfad.exists():
        raise HTTPException(404, "Datei nicht gefunden")
    # Bewusst ohne `filename=`: FastAPI setzt damit Content-Disposition
    # "attachment", und der Browser würde statt der Anzeige einen Download
    # starten. Die Anzeige im Frontend läuft über ein <iframe> auf diese URL.
    return FileResponse(
        str(pfad),
        media_type="application/pdf",
        headers={
            "Content-Disposition":
                f"inline; filename*=UTF-8''{quote(auszug.dateiname)}",
        },
    )


@router.delete("/auszuege/{auszug_id}")
def auszug_loeschen(
    auszug_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Entfernt nur das Archiv. Die importierten Buchungen sind eigenständige
    Daten und bleiben unberührt; ihre Herkunftsangabe fällt weg."""
    auszug = _auszug_holen(db, auszug_id)
    # Ausdrücklich, nicht per ON DELETE SET NULL: in migrierten Datenbanken ist
    # die Spalte per ALTER TABLE ohne REFERENCES entstanden (siehe
    # alembic/versions/z7b8c9d0e1f2_kontoauszug_archiv.py).
    db.query(Buchung).filter(Buchung.kontoauszug_id == auszug.id).update(
        {Buchung.kontoauszug_id: None}, synchronize_session=False,
    )
    pfad = settings.kontoauszuege_dir / auszug.dateipfad
    if pfad.exists():
        pfad.unlink()
    db.delete(auszug)
    db.commit()
    return {"ok": True}


@router.post("/vorschau")
async def vorschau(
    konto_id: int = Form(...),
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if datei.content_type not in ("application/pdf", "application/octet-stream"):
        if not (datei.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "Nur PDF-Dateien erlaubt")
    pdf_bytes = await datei.read()
    if len(pdf_bytes) > MAX_PDF_MB * 1024 * 1024:
        raise HTTPException(413, f"PDF zu groß (max. {MAX_PDF_MB} MB)")
    return _vorschau_buchungen(db, konto_id, pdf_bytes)


@router.post("/commit")
async def commit(
    konto_id: int = Form(...),
    datei: UploadFile = File(...),
    hashes: Optional[str] = Form(default=None),
    treffer: Optional[str] = Form(default=None),
    auffrischen: bool = Form(default=False),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Importiert Buchungen aus PDF (überspringt Duplikate und nicht ausgewählte)."""
    pdf_bytes = await datei.read()
    daten = _vorschau_buchungen(db, konto_id, pdf_bytes)

    # Vor dem Schreiben der Buchungen, damit die Archiv-ID für die
    # Herkunftsangabe an jeder Buchung schon vorliegt.
    auszug, neue_auszug_datei = _auszug_ablegen(
        db, konto_id, pdf_bytes, daten, datei.filename, user,
    )

    ausgewaehlt: Optional[set] = None
    if hashes:
        try:
            ausgewaehlt = set(json.loads(hashes))
        except Exception:
            raise HTTPException(400, "Ungültiges hashes-Format")

    # Treffer-Zuordnungen: import_hash → existing_buchung_id
    treffer_map: dict[str, int] = {}
    if treffer:
        try:
            treffer_map = json.loads(treffer)
        except Exception:
            raise HTTPException(400, "Ungültiges treffer-Format")

    pdf_hashes = {b["import_hash"] for b in daten["buchungen"]}

    importiert = 0
    neue_buchungen: list[Buchung] = []
    for b in daten["buchungen"]:
        if b["duplikat"]:
            continue
        if ausgewaehlt is not None and b["import_hash"] not in ausgewaehlt:
            continue
        buch = Buchung(
            konto_id=konto_id,
            datum=b["datum"],
            betrag=b["betrag"],
            # Der definierte Empfängername gewinnt gegen den Bankrohtext; dieser
            # bleibt vollständig in `import_empfaenger` erhalten.
            empfaenger=b.get("empfaenger_name") or b["empfaenger"],
            empfaenger_id=b.get("empfaenger_id"),
            kategorie_id=b.get("kategorie_id"),
            notiz=b.get("notiz"),
            verwendungszweck=b.get("verwendungszweck"),
            import_verwendungszweck=b.get("verwendungszweck"),
            import_empfaenger=b.get("empfaenger"),
            import_iban=b.get("iban_empfaenger"),
            import_hash=b["import_hash"],
            kontoauszug_id=auszug.id,
            quelle="import",
            erstellt_von=user.id,
        )
        db.add(buch)
        neue_buchungen.append(buch)
        importiert += 1

    neue_hashes = {b.import_hash for b in neue_buchungen if b.import_hash}

    try:
        db.flush()
    except Exception as exc:
        db.rollback()
        _verwaiste_datei_entfernen(neue_auszug_datei)
        _log.error("Flush fehlgeschlagen: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(500, f"Datenbankfehler beim Einfügen: {exc}") from exc

    # Treffer-Buchungen patchen: import_hash + Verwendungszweck/Datum vom Kontoauszug übertragen
    verknuepft = 0
    gebucht_gesetzt = 0
    if treffer_map:
        pdf_hash_zu_eintrag = {b["import_hash"]: b for b in daten["buchungen"]}
        for pdf_hash, buchung_id in treffer_map.items():
            if pdf_hash in neue_hashes:
                continue  # als neue Buchung importiert, kein Update nötig
            vorhandene = db.get(Buchung, buchung_id)
            if not vorhandene:
                continue
            pdf_b = pdf_hash_zu_eintrag.get(pdf_hash)
            if not pdf_b:
                continue
            # Nie den Hash einer Buchung überschreiben, die schon eine andere
            # Zeile dieses PDFs belegt: sonst verliert die belegte Zeile ihren
            # Hartmatch und die eigentlich gemeinte Partnerbuchung bleibt
            # unverknüpft (siehe Kandidatenfilter in der Vorschau).
            if (vorhandene.import_hash
                    and vorhandene.import_hash != pdf_hash
                    and vorhandene.import_hash in pdf_hashes):
                continue

            vorhandene.import_hash = pdf_hash
            # Auch eine vorher manuell erfasste Buchung ist ab jetzt durch
            # diesen Auszug belegt.
            vorhandene.kontoauszug_id = auszug.id
            if pdf_b.get("verwendungszweck"):
                vorhandene.import_verwendungszweck = pdf_b["verwendungszweck"]
            # Kassenzettel-Kaufdatum aus dem Haushaltsbuch bleibt erhalten, sonst
            # zählt das Buchungsdatum laut Kontoauszug.
            if vorhandene.quelle != "haushaltsbuch":
                vorhandene.datum = pdf_b["datum"]
            # Der Kontoauszug belegt, dass das Geld tatsächlich geflossen ist. Eine
            # noch als "geplant" geführte Buchung (z.B. aus einer wiederkehrenden
            # Vorlage generiert) zählt sonst nicht in den Kontosaldo, obwohl sie
            # real stattgefunden hat.
            if vorhandene.status != "gebucht":
                vorhandene.status = "gebucht"
                gebucht_gesetzt += 1
            verknuepft += 1

    # Hart-Duplikate optional mit den aktuellen PDF-Werten auffrischen
    # (z.B. erneuter Upload eines alten Kontoauszugs zur Korrektur von Altdaten).
    aufgefrischt = 0
    if auffrischen:
        for b in daten["buchungen"]:
            if not b["duplikat"]:
                continue
            vb = b.get("vorhandene_buchung")
            if not vb:
                continue
            bestehende = db.get(Buchung, vb["id"])
            if not bestehende:
                continue
            geaendert = False
            if b.get("verwendungszweck") and bestehende.import_verwendungszweck != b["verwendungszweck"]:
                bestehende.import_verwendungszweck = b["verwendungszweck"]
                geaendert = True
            if bestehende.quelle != "haushaltsbuch" and bestehende.datum != b["datum"]:
                bestehende.datum = b["datum"]
                geaendert = True
            # Repariert Altbestand: vor Einführung der Status-Übernahme per Treffer
            # verknüpfte Buchungen blieben fälschlich "geplant".
            if bestehende.status != "gebucht":
                bestehende.status = "gebucht"
                gebucht_gesetzt += 1
                geaendert = True
            # Herkunft nachtragen: beim Auffrischen ist dieser Auszug
            # ausdrücklich der maßgebliche Nachweis für die Zeile.
            if bestehende.kontoauszug_id != auszug.id:
                bestehende.kontoauszug_id = auszug.id
                geaendert = True
            if geaendert:
                aufgefrischt += 1

    # Phase 8.5.1: für jede neu importierte Buchung nach offenen HHB-Einträgen
    # suchen, die dazu passen könnten (Betrag/Datum/Empfänger).
    abgleich_vorschlaege = []
    hash_zu_vorschau = {b["import_hash"]: b for b in daten["buchungen"]}
    for buch in neue_buchungen:
        if buch.betrag >= 0:
            continue  # nur Ausgaben können zu einem HHB-Eintrag passen
        vorschau_zeile = hash_zu_vorschau.get(buch.import_hash or "", {})
        kandidaten = finde_kandidaten(
            db, datum=buch.datum, betrag=buch.betrag,
            # Bewusst der Bankrohtext und nicht `buch.empfaenger`: seit die
            # Import-Regeln dort "PayPal" hineinschreiben, stünde der Laden
            # nicht mehr darin und der Namensvergleich in hhb_match liefe leer.
            empfaenger_text=buch.import_empfaenger or buch.empfaenger,
            empfaenger_id=buch.empfaenger_id,
            verwendungszweck=buch.import_verwendungszweck,
            geschaeft_id=vorschau_zeile.get("regel_geschaeft_id"),
        )
        if kandidaten:
            abgleich_vorschlaege.append({
                "buchung_id": buch.id,
                "buchung_empfaenger": buch.empfaenger,
                "buchung_datum": buch.datum,
                "buchung_betrag": buch.betrag,
                "kandidaten": [HaushaltsbuchEintragOut.model_validate(k).model_dump(mode="json") for k in kandidaten],
            })

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        _verwaiste_datei_entfernen(neue_auszug_datei)
        _log.error("Commit fehlgeschlagen: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(500, f"Datenbankfehler: {exc}") from exc
    return {
        "kontoauszug_id": auszug.id,
        "kontoauszug_dateiname": auszug.dateiname,
        "importiert": importiert,
        "verknuepft": verknuepft,
        "gebucht_gesetzt": gebucht_gesetzt,
        "aufgefrischt": aufgefrischt,
        "duplikate": daten["duplikate"],
        "abgleich_vorschlaege": abgleich_vorschlaege,
    }
