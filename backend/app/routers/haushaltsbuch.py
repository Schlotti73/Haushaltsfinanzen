"""
Haushaltsbuch-Einträge (Phase 8).

Jeder Eintrag ist immer durch genau eine Buchung gedeckt (buchung_id NOT NULL):
  - bezahlart='bar'              -> Platzhalter-Buchung ohne Konto (zählt als Ausgabe)
  - bezahlart='karte'|'konto'    -> Buchung mit Konto, abgleich_status='offen'
                                     bis sie ggf. mit einer importierten
                                     Bank-Buchung verknüpft wird (Phase 8.5)
"""

from __future__ import annotations

import difflib
import re
import shutil
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import (
    Beleg, Buchung, Geschaeft, HaushaltsbuchArtikelKorrektur, HaushaltsbuchEintrag,
    HaushaltsbuchPosition, Kategorie,
)
from app.schemas import (
    HaushaltsbuchEintragCreate, HaushaltsbuchEintragOut, HaushaltsbuchEintragUpdate,
    HaushaltsbuchOcrVorschau, HaushaltsbuchPositionCreate,
)
from app.services.hhb_match import finde_kandidaten
from app.services.ocr.preprocess import verbessere_und_lies
from app.services.ocr.parser import parse_kassenzettel
from app.services.ocr.dispatcher import waehle_muster, baue_profil, kategorie_map

router = APIRouter(prefix="/haushaltsbuch", tags=["haushaltsbuch"])

# Mittlere Tesseract-Worterkennungssicherheit (0-100) als Schwellwerte fuer die
# Qualitaetseinschaetzung der OCR-Vorschau.
KONFIDENZ_FEHLGESCHLAGEN = 40
KONFIDENZ_UNSICHER = 65


def _load_eintrag(db: Session, eintrag_id: int) -> HaushaltsbuchEintrag:
    e = (
        db.query(HaushaltsbuchEintrag)
        .options(selectinload(HaushaltsbuchEintrag.positionen), selectinload(HaushaltsbuchEintrag.geschaeft))
        .filter(HaushaltsbuchEintrag.id == eintrag_id)
        .first()
    )
    if not e:
        raise HTTPException(404, "Nicht gefunden")
    return e


def _get_or_create_geschaeft(db: Session, geschaeft_id: Optional[int], geschaeft_name: Optional[str]) -> Optional[Geschaeft]:
    if geschaeft_id is not None:
        g = db.get(Geschaeft, geschaeft_id)
        if not g:
            raise HTTPException(404, "Geschäft nicht gefunden")
        return g
    name = (geschaeft_name or "").strip()
    if not name:
        return None
    g = db.query(Geschaeft).filter(Geschaeft.name == name).first()
    if g:
        return g
    g = Geschaeft(name=name)
    db.add(g)
    db.flush()
    return g


def _apply_positionen(eintrag: HaushaltsbuchEintrag, positionen_data: list) -> None:
    eintrag.positionen = [
        HaushaltsbuchPosition(
            bezeichnung=p.bezeichnung,
            menge=p.menge,
            einzelpreis=p.einzelpreis,
            gesamtpreis=p.gesamtpreis,
            kategorie_id=p.kategorie_id,
        )
        for p in positionen_data
    ]


# ── Artikel-Auswahl & OCR-Korrektur (Phase: Bereichsmarkierung/Artikel-Auswahl) ──
# Vorschläge/Korrekturen sind bewusst je Geschäft getrennt (Druckerschrift/
# Sortiment ist geschäftsspezifisch, siehe Skill „ocr").

_FUZZY_CUTOFF = 0.72  # eher konservativ, um Fehl-Vorschläge bei ähnlichen Artikeln zu vermeiden


def _normalisiere_artikel(text: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _bekannte_artikel(db: Session, geschaeft_id: Optional[int]) -> list[str]:
    """Bereits erfasste Artikel-Bezeichnungen desselben Geschäfts (für Kombobox/Fuzzy-Fallback)."""
    if not geschaeft_id:
        return []
    rows = (
        db.query(HaushaltsbuchPosition.bezeichnung)
        .join(HaushaltsbuchEintrag, HaushaltsbuchPosition.eintrag_id == HaushaltsbuchEintrag.id)
        .filter(HaushaltsbuchEintrag.geschaeft_id == geschaeft_id)
        .distinct()
        .all()
    )
    return sorted({r[0] for r in rows if r[0] and r[0].strip()}, key=str.lower)


def _schlage_bezeichnung_vor(db: Session, geschaeft_id: Optional[int], roh: str) -> str:
    """Vorschlag für eine OCR-Bezeichnung: erst exakter Treffer in der gelernten
    Korrektur-Historie, sonst Fuzzy-Fallback gegen bekannte Artikel desselben
    Geschäfts (per difflib, keine neue Abhängigkeit). Ohne Treffer: Rohtext unverändert."""
    if not geschaeft_id or not roh.strip():
        return roh
    norm = _normalisiere_artikel(roh)
    treffer = (
        db.query(HaushaltsbuchArtikelKorrektur)
        .filter(
            HaushaltsbuchArtikelKorrektur.geschaeft_id == geschaeft_id,
            HaushaltsbuchArtikelKorrektur.ocr_text == norm,
        )
        .first()
    )
    if treffer:
        return treffer.bezeichnung

    bekannt_norm = {_normalisiere_artikel(b): b for b in _bekannte_artikel(db, geschaeft_id)}
    kandidaten = difflib.get_close_matches(norm, bekannt_norm.keys(), n=1, cutoff=_FUZZY_CUTOFF)
    if kandidaten and kandidaten[0] != norm:
        return bekannt_norm[kandidaten[0]]
    return roh


def _lerne_korrekturen(db: Session, geschaeft_id: Optional[int], positionen: list[HaushaltsbuchPositionCreate]) -> None:
    """Merkt sich für jede aus OCR stammende, vor dem Speichern geänderte
    Bezeichnung eine Korrektur (Rohtext -> endgültige Bezeichnung) für dieses
    Geschäft, damit derselbe Lesefehler beim nächsten Mal automatisch
    vorgeschlagen wird."""
    if not geschaeft_id:
        return
    for p in positionen:
        roh = p.ocr_bezeichnung
        final = (p.bezeichnung or "").strip()
        if not roh or not final or _normalisiere_artikel(final) == _normalisiere_artikel(roh):
            continue
        norm = _normalisiere_artikel(roh)
        vorhanden = (
            db.query(HaushaltsbuchArtikelKorrektur)
            .filter(
                HaushaltsbuchArtikelKorrektur.geschaeft_id == geschaeft_id,
                HaushaltsbuchArtikelKorrektur.ocr_text == norm,
            )
            .first()
        )
        if vorhanden:
            vorhanden.bezeichnung = final
            vorhanden.aktualisiert_am = datetime.utcnow()
        else:
            db.add(HaushaltsbuchArtikelKorrektur(
                geschaeft_id=geschaeft_id, ocr_text=norm, bezeichnung=final,
                aktualisiert_am=datetime.utcnow(),
            ))


@router.get("", response_model=list[HaushaltsbuchEintragOut])
def list_eintraege(
    geschaeft_id: Optional[int] = None,
    abgleich_status: Optional[str] = None,
    datum_von: Optional[str] = None,
    datum_bis: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    q = db.query(HaushaltsbuchEintrag).options(
        selectinload(HaushaltsbuchEintrag.positionen), selectinload(HaushaltsbuchEintrag.geschaeft)
    )
    if geschaeft_id is not None:
        q = q.filter(HaushaltsbuchEintrag.geschaeft_id == geschaeft_id)
    if abgleich_status:
        q = q.filter(HaushaltsbuchEintrag.abgleich_status == abgleich_status)
    if datum_von:
        q = q.filter(HaushaltsbuchEintrag.datum >= datum_von)
    if datum_bis:
        q = q.filter(HaushaltsbuchEintrag.datum <= datum_bis)
    return q.order_by(HaushaltsbuchEintrag.datum.desc(), HaushaltsbuchEintrag.id.desc()).limit(limit).all()


@router.get("/abgleich-kandidaten", response_model=list[HaushaltsbuchEintragOut])
def abgleich_kandidaten(
    datum: str,
    betrag: float,
    empfaenger_text: Optional[str] = None,
    empfaenger_id: Optional[int] = None,
    verwendungszweck: Optional[str] = None,
    tage_toleranz: int = 3,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """Findet offene Haushaltsbuch-Einträge, die zu einer Bank-Buchung passen
    könnten (Phase 8.5: Import-Commit oder manuelle Buchung)."""
    return finde_kandidaten(
        db, datum=datum, betrag=betrag, empfaenger_text=empfaenger_text, empfaenger_id=empfaenger_id,
        verwendungszweck=verwendungszweck, tage_toleranz=tage_toleranz,
    )


@router.get("/artikel-vorschlaege", response_model=list[str])
def artikel_vorschlaege(geschaeft_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Bereits erfasste Artikel-Bezeichnungen dieses Geschäfts, für die Kombobox
    beim manuellen Erfassen von Artikeln."""
    return _bekannte_artikel(db, geschaeft_id)


@router.get("/{eintrag_id}", response_model=HaushaltsbuchEintragOut)
def get_eintrag(eintrag_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return _load_eintrag(db, eintrag_id)


@router.post("", response_model=HaushaltsbuchEintragOut, status_code=201)
def create_eintrag(body: HaushaltsbuchEintragCreate, db: Session = Depends(get_db), user=Depends(get_current_user)):
    geschaeft = _get_or_create_geschaeft(db, body.geschaeft_id, body.geschaeft_name)
    konto_id = body.konto_id if body.bezahlart != "bar" else None
    abgleich_status = "bar_ohne_konto" if body.bezahlart == "bar" else "offen"

    buchung = Buchung(
        konto_id=konto_id,
        datum=body.datum,
        betrag=-abs(body.betrag_gesamt),
        empfaenger=geschaeft.name if geschaeft else None,
        # Der Empfänger-FK des Geschäfts wird mitgeführt, damit Haushaltsbuch-Einkäufe
        # in Empfänger-Auswertungen auftauchen (der String bleibt Anzeigewert).
        empfaenger_id=geschaeft.empfaenger_id if geschaeft else None,
        kategorie_id=geschaeft.standard_kategorie_id if geschaeft else None,
        notiz=body.notiz,
        status="gebucht",
        quelle="haushaltsbuch",
        erstellt_von=user.id,
    )
    db.add(buchung)
    db.flush()

    eintrag = HaushaltsbuchEintrag(
        datum=body.datum,
        geschaeft_id=geschaeft.id if geschaeft else None,
        betrag_gesamt=abs(body.betrag_gesamt),
        bezahlart=body.bezahlart,
        konto_id=konto_id,
        buchung_id=buchung.id,
        abgleich_status=abgleich_status,
        notiz=body.notiz,
        erstellt_von=user.id,
    )
    db.add(eintrag)
    db.flush()
    _apply_positionen(eintrag, body.positionen)
    _lerne_korrekturen(db, geschaeft.id if geschaeft else None, body.positionen)
    db.commit()
    return _load_eintrag(db, eintrag.id)


@router.patch("/{eintrag_id}", response_model=HaushaltsbuchEintragOut)
def update_eintrag(eintrag_id: int, body: HaushaltsbuchEintragUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    eintrag = _load_eintrag(db, eintrag_id)
    buchung = db.get(Buchung, eintrag.buchung_id)
    data = body.model_dump(exclude_none=True, exclude={"positionen", "geschaeft_id", "geschaeft_name"})

    if body.geschaeft_id is not None or body.geschaeft_name is not None:
        geschaeft = _get_or_create_geschaeft(db, body.geschaeft_id, body.geschaeft_name)
        eintrag.geschaeft_id = geschaeft.id if geschaeft else None
        if buchung:
            buchung.empfaenger = geschaeft.name if geschaeft else None
            buchung.empfaenger_id = geschaeft.empfaenger_id if geschaeft else None

    if "datum" in data:
        eintrag.datum = data["datum"]
        if buchung:
            buchung.datum = data["datum"]
    if "betrag_gesamt" in data:
        eintrag.betrag_gesamt = abs(data["betrag_gesamt"])
        if buchung:
            buchung.betrag = -abs(data["betrag_gesamt"])
    if "bezahlart" in data:
        eintrag.bezahlart = data["bezahlart"]
    if "konto_id" in data:
        eintrag.konto_id = data["konto_id"]
        if buchung and eintrag.bezahlart != "bar":
            buchung.konto_id = data["konto_id"]
    if "notiz" in data:
        eintrag.notiz = data["notiz"]
        if buchung:
            buchung.notiz = data["notiz"]

    if body.positionen is not None:
        _apply_positionen(eintrag, body.positionen)
        _lerne_korrekturen(db, eintrag.geschaeft_id, body.positionen)

    db.commit()
    return _load_eintrag(db, eintrag_id)


@router.delete("/{eintrag_id}", status_code=204)
def delete_eintrag(eintrag_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    eintrag = db.get(HaushaltsbuchEintrag, eintrag_id)
    if not eintrag:
        raise HTTPException(404, "Nicht gefunden")
    buchung = db.get(Buchung, eintrag.buchung_id)
    db.delete(eintrag)
    # Nur die eigene Platzhalter-Buchung mitlöschen, keine verknüpfte Bank-Buchung
    if buchung and buchung.quelle == "haushaltsbuch":
        db.delete(buchung)
    db.commit()
    beleg_ordner = settings.belege_dir / f"eintrag-{eintrag_id}"
    if beleg_ordner.is_dir():
        shutil.rmtree(beleg_ordner)


@router.post("/{eintrag_id}/ocr", response_model=HaushaltsbuchOcrVorschau)
def ocr_vorschau(eintrag_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Texterkennung auf dem zuletzt hochgeladenen Beleg-Foto; liefert nur eine
    Vorschau der erkannten Artikel-Kandidaten (keine Speicherung)."""
    eintrag = db.get(HaushaltsbuchEintrag, eintrag_id)
    if not eintrag:
        raise HTTPException(404, "Nicht gefunden")

    beleg = (
        db.query(Beleg)
        .filter(Beleg.eintrag_id == eintrag_id)
        .order_by(Beleg.hochgeladen_am.desc())
        .first()
    )
    if not beleg:
        raise HTTPException(404, "Kein Beleg-Foto für diesen Eintrag vorhanden")

    bildpfad = settings.belege_dir / beleg.dateipfad
    if not bildpfad.exists():
        raise HTTPException(404, "Beleg-Datei nicht gefunden")
    if bildpfad.suffix.lower() == ".pdf":
        raise HTTPException(400, "Texterkennung ist nur für Foto-Belege (JPEG/PNG/WebP) verfügbar, nicht für PDF")

    vorschau_pfad = settings.belege_dir / f"eintrag-{eintrag_id}" / "vorschau.jpg"
    ocr = verbessere_und_lies(bildpfad, speicher_pfad=vorschau_pfad)
    rohtext, konfidenz = ocr.rohtext, ocr.konfidenz

    # Geschäft datengetrieben erkennen (Phase 10) und Parser entsprechend tunen.
    muster = waehle_muster(db, rohtext)
    roh_positionen = parse_kassenzettel(rohtext, baue_profil(muster))
    schluessel_kat = kategorie_map(muster)

    kat_lebensmittel = db.query(Kategorie).filter(Kategorie.name == "Lebensmittel").first()
    kat_haushalt = db.query(Kategorie).filter(Kategorie.name == "Haushaltswaren").first()
    kat_id_7 = kat_lebensmittel.id if kat_lebensmittel else None
    kat_id_19 = kat_haushalt.id if kat_haushalt else None

    positionen = []
    for p in roh_positionen:
        satz = p.pop("mwst_satz", None)
        schluessel = p.pop("mwst_schluessel", None)
        # 1. geschäftsspezifische Schlüssel→Kategorie-Zuordnung, sonst 2. satzbasiert
        if schluessel and schluessel in schluessel_kat:
            p["kategorie_id"] = schluessel_kat[schluessel]
        elif satz == 7.0:
            p["kategorie_id"] = kat_id_7
        elif satz is not None:
            p["kategorie_id"] = kat_id_19
        # Artikel-Auswahl/OCR-Korrektur: Rohtext merken, Bezeichnung ggf. anhand
        # gelernter Korrekturen/bekannter Artikel dieses Geschäfts vorschlagen.
        roh_bezeichnung = p["bezeichnung"]
        p["ocr_bezeichnung"] = roh_bezeichnung
        p["bezeichnung"] = _schlage_bezeichnung_vor(db, eintrag.geschaeft_id, roh_bezeichnung)
        positionen.append(p)

    hinweis = None
    foto_wiederholen = False
    if konfidenz is not None and konfidenz < KONFIDENZ_FEHLGESCHLAGEN:
        hinweis = (
            f"Texterkennung nicht möglich: Foto ist zu unscharf oder zu dunkel "
            f"(Erkennungssicherheit {konfidenz:.0f}%). Bitte Foto erneut aufnehmen?"
        )
        foto_wiederholen = True
    elif not positionen:
        hinweis = "Keine Artikel erkannt – Foto ggf. unscharf oder Kassenzettel nicht vollständig im Bild. Foto erneut aufnehmen?"
        foto_wiederholen = True
    elif konfidenz is not None and konfidenz < KONFIDENZ_UNSICHER:
        hinweis = (
            f"Texterkennung nur bedingt möglich (Erkennungssicherheit {konfidenz:.0f}%) – "
            f"erkannte Artikel bitte sorgfältig prüfen. Foto erneut aufnehmen?"
        )
        foto_wiederholen = True

    eintrag.ocr_rohtext = rohtext
    eintrag.ocr_konfidenz = konfidenz
    eintrag.ocr_hinweis = hinweis
    eintrag.ocr_status = "geparst" if positionen else "roh"
    db.commit()

    return HaushaltsbuchOcrVorschau(
        rohtext=rohtext,
        positionen=positionen,
        konfidenz=konfidenz,
        hinweis=hinweis,
        foto_wiederholen_empfohlen=foto_wiederholen,
        ocr_variante=ocr.variante,
        ocr_segmentiert=ocr.segmentiert,
        ocr_preiszeilen=ocr.preiszeilen,
        hat_vorschau=vorschau_pfad.exists(),
        bekannte_artikel=_bekannte_artikel(db, eintrag.geschaeft_id),
    )


@router.get("/{eintrag_id}/beleg-vorschau")
def beleg_vorschau(eintrag_id: int, _=Depends(get_current_user)):
    """Liefert das von der OCR-Pipeline entzerrte/verbesserte Belegfoto (falls vorhanden)."""
    pfad = settings.belege_dir / f"eintrag-{eintrag_id}" / "vorschau.jpg"
    if not pfad.exists():
        raise HTTPException(404, "Kein Vorschaubild – bitte erst Texterkennung starten")
    return FileResponse(str(pfad), media_type="image/jpeg")


@router.post("/{eintrag_id}/verknuepfen", response_model=HaushaltsbuchEintragOut)
def verknuepfen(eintrag_id: int, buchung_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    """Ersetzt die Platzhalter-Buchung eines offenen Eintrags durch eine echte
    Bank-/manuelle Buchung (Phase 8.5). Die alte Platzhalter-Buchung wird
    gelöscht, damit sie nicht doppelt in der Statistik auftaucht."""
    eintrag = db.get(HaushaltsbuchEintrag, eintrag_id)
    if not eintrag:
        raise HTTPException(404, "Eintrag nicht gefunden")
    if eintrag.abgleich_status != "offen":
        raise HTTPException(400, "Nur offene Einträge können verknüpft werden")

    neue_buchung = db.get(Buchung, buchung_id)
    if not neue_buchung:
        raise HTTPException(404, "Buchung nicht gefunden")
    if neue_buchung.haushaltsbuch_eintrag is not None:
        raise HTTPException(400, "Diese Buchung ist bereits mit einem Haushaltsbuch-Eintrag verknüpft")

    alte_buchung = db.get(Buchung, eintrag.buchung_id)

    eintrag.buchung_id = neue_buchung.id
    eintrag.abgleich_status = "verknuepft"
    db.flush()

    if alte_buchung and alte_buchung.quelle == "haushaltsbuch":
        db.delete(alte_buchung)
    db.commit()
    return _load_eintrag(db, eintrag_id)
