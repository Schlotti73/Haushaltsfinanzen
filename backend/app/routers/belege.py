"""
Beleg-Upload und -Abruf.
Dateien landen in belege/<buchung_id>/<uuid>.<ext>.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import get_db
from app.models import (
    Beleg, Buchung, Fahrzeug, Gebaeude, HaushaltsbuchEintrag, Vertrag, ZaehlerAblesung,
)

try:  # OpenCV ist optional (wie bei der OCR-Pipeline) - ohne bleibt das Original erhalten
    import cv2
    import numpy as np
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore
    np = None  # type: ignore

router = APIRouter(prefix="/belege", tags=["belege"])

ERLAUBTE_TYPEN = {"image/jpeg", "image/png", "image/webp", "application/pdf"}
_BILD_TYPEN = ERLAUBTE_TYPEN - {"application/pdf"}
# Fallback ueber Dateiendung, falls der Client keinen/unspezifischen MIME-Typ
# sendet (manche Clients schicken application/octet-stream fuer echte Bilder).
ENDUNG_MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp", ".pdf": "application/pdf",
}
MAX_BYTES = 20 * 1024 * 1024  # 20 MB

# Handyfotos (12-48 MP) unkomprimiert zu speichern sprengt den Speicherplatz;
# die OCR-Verarbeitung braucht ohnehin nur ~1000px Breite (siehe preprocess.py),
# 2000px lange Kante lässt also reichlich Reserve für Bildschirmansicht/Zoom.
BILD_MAX_KANTE = 2000
BILD_JPEG_QUALITAET = 85
# Harte Obergrenze je Bild. 2000px bei Qualität 85 liegt meist schon darunter,
# garantiert war es nie: ein kontrastreiches Foto (Kassenzettel, Zählwerk mit
# Streiflicht) kommt auch so auf mehrere MB. Erst sinkt die Qualität, dann die
# Kante - in dieser Reihenfolge, weil ein kleineres Bild mehr Information
# verliert als ein etwas weicheres.
BILD_MAX_BYTES = 1024 * 1024
BILD_KANTEN = (BILD_MAX_KANTE, 1600, 1200, 900)
BILD_QUALITAETEN = (BILD_JPEG_QUALITAET, 70, 55)


def _ermittle_mime(content_type: str | None, dateiname: str | None) -> str | None:
    """Liefert einen erlaubten MIME-Typ oder None, wenn nicht zulaessig.
    Vertraut zuerst dem Client-Typ, faellt sonst auf die Dateiendung zurueck."""
    if content_type in ERLAUBTE_TYPEN:
        return content_type
    ext = Path(dateiname or "").suffix.lower()
    return ENDUNG_MIME.get(ext)


def _skaliere(bild, kante: int):
    """Verkleinert auf `kante` lange Kante; ein kleineres Bild bleibt, wie es ist."""
    hoehe, breite = bild.shape[:2]
    lange_kante = max(hoehe, breite)
    if lange_kante <= kante:
        return bild
    skala = kante / lange_kante
    return cv2.resize(
        bild, (round(breite * skala), round(hoehe * skala)), interpolation=cv2.INTER_AREA,
    )


def _optimiere_bild(daten: bytes) -> bytes:
    """Kodiert Fotos einheitlich als JPEG unter BILD_MAX_BYTES.

    Der erste Versuch ist der bisherige - BILD_MAX_KANTE bei Qualität
    BILD_JPEG_QUALITAET -, und für fast jedes Foto bleibt es dabei. Passt es
    nicht, sinkt erst die Qualität, dann die Kante. Ohne OpenCV oder bei nicht
    lesbaren Bilddaten bleibt die Datei unveraendert (bestehendes Verhalten);
    reicht keine Stufe, wird die kleinste erreichte genommen - ein etwas zu
    großes Bild ist besser als ein abgelehnter Upload.
    """
    if cv2 is None:
        return daten
    bild = cv2.imdecode(np.frombuffer(daten, dtype=np.uint8), cv2.IMREAD_COLOR)
    if bild is None:
        return daten

    kleinste: bytes | None = None
    for kante in BILD_KANTEN:
        verkleinert = _skaliere(bild, kante)
        for qualitaet in BILD_QUALITAETEN:
            ok, kodiert = cv2.imencode(".jpg", verkleinert, [cv2.IMWRITE_JPEG_QUALITY, qualitaet])
            if not ok:
                continue
            roh = kodiert.tobytes()
            if len(roh) <= BILD_MAX_BYTES:
                return roh
            if kleinste is None or len(roh) < len(kleinste):
                kleinste = roh
    return kleinste if kleinste is not None else daten


# ── Gemeinsame Bausteine ────────────────────────────────────────────────────
# Buchung, Haushaltsbuch-Eintrag und Gebaeude haengen Belege nach demselben
# Muster an: speichern, ausliefern, loeschen - nur die Zuordnungsspalte und der
# Unterordner unterscheiden sich.

async def _beleg_anlegen(datei: UploadFile, ordner: str, db: Session, user, **zuordnung) -> dict:
    mime = _ermittle_mime(datei.content_type, datei.filename)
    if mime is None:
        raise HTTPException(
            400,
            f"Dateityp nicht erlaubt (erlaubt: JPEG, PNG, WebP, PDF). "
            f"Erhalten: {datei.content_type}, Datei: {datei.filename}",
        )

    inhalt = await datei.read()
    if len(inhalt) > MAX_BYTES:
        raise HTTPException(400, "Datei zu groß (max. 20 MB)")

    ext = Path(datei.filename or "datei").suffix or ".bin"
    dateiname_orig = datei.filename or f"beleg{ext}"
    if mime in _BILD_TYPEN:
        inhalt = _optimiere_bild(inhalt)
        ext = ".jpg"
        mime = "image/jpeg"
        dateiname_orig = f"{Path(dateiname_orig).stem}.jpg"

    dateiname_gespeichert = f"{uuid.uuid4().hex}{ext}"
    zielordner = settings.belege_dir / ordner
    zielordner.mkdir(parents=True, exist_ok=True)
    (zielordner / dateiname_gespeichert).write_bytes(inhalt)

    beleg = Beleg(
        dateiname=dateiname_orig,
        dateipfad=f"{ordner}/{dateiname_gespeichert}",
        hochgeladen_von=user.id,
        **zuordnung,
    )
    db.add(beleg)
    db.commit()
    db.refresh(beleg)
    return {"id": beleg.id, "dateiname": beleg.dateiname, "mime_typ": mime}


def _beleg_holen(db: Session, beleg_id: int, spalte, wert) -> Beleg:
    beleg = db.query(Beleg).filter(Beleg.id == beleg_id, spalte == wert).first()
    if not beleg:
        raise HTTPException(404, "Beleg nicht gefunden")
    return beleg


def _beleg_antwort(beleg: Beleg) -> FileResponse:
    pfad = settings.belege_dir / beleg.dateipfad
    if not pfad.exists():
        raise HTTPException(404, "Datei nicht gefunden")
    mime = ENDUNG_MIME.get(pfad.suffix.lower(), "application/octet-stream")
    return FileResponse(str(pfad), media_type=mime, filename=beleg.dateiname)


def _beleg_entfernen(db: Session, beleg: Beleg) -> dict:
    pfad = settings.belege_dir / beleg.dateipfad
    if pfad.exists():
        pfad.unlink()
    db.delete(beleg)
    db.commit()
    return {"ok": True}


# ── Belege an Buchungen ─────────────────────────────────────────────────────

@router.post("/{buchung_id}")
async def beleg_hochladen(
    buchung_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if db.get(Buchung, buchung_id) is None:
        raise HTTPException(404, "Buchung nicht gefunden")
    return await _beleg_anlegen(datei, str(buchung_id), db, user, buchung_id=buchung_id)


@router.get("/{buchung_id}")
def belege_liste(
    buchung_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    belege = db.query(Beleg).filter(Beleg.buchung_id == buchung_id).all()
    return [{"id": b.id, "dateiname": b.dateiname} for b in belege]


@router.get("/{buchung_id}/{beleg_id}/datei")
def beleg_datei(
    buchung_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_antwort(_beleg_holen(db, beleg_id, Beleg.buchung_id, buchung_id))


@router.delete("/{buchung_id}/{beleg_id}")
def beleg_loeschen(
    buchung_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_entfernen(db, _beleg_holen(db, beleg_id, Beleg.buchung_id, buchung_id))


# ── Phase 8: Belege an Haushaltsbuch-Eintraege haengen ──────────────────────

@router.post("/eintrag/{eintrag_id}")
async def beleg_hochladen_eintrag(
    eintrag_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if db.get(HaushaltsbuchEintrag, eintrag_id) is None:
        raise HTTPException(404, "Haushaltsbuch-Eintrag nicht gefunden")
    return await _beleg_anlegen(datei, f"eintrag-{eintrag_id}", db, user, eintrag_id=eintrag_id)


@router.get("/eintrag/{eintrag_id}")
def belege_liste_eintrag(
    eintrag_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    belege = db.query(Beleg).filter(Beleg.eintrag_id == eintrag_id).all()
    return [{"id": b.id, "dateiname": b.dateiname} for b in belege]


@router.get("/eintrag/{eintrag_id}/{beleg_id}/datei")
def beleg_datei_eintrag(
    eintrag_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_antwort(_beleg_holen(db, beleg_id, Beleg.eintrag_id, eintrag_id))


@router.delete("/eintrag/{eintrag_id}/{beleg_id}")
def beleg_loeschen_eintrag(
    eintrag_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_entfernen(db, _beleg_holen(db, beleg_id, Beleg.eintrag_id, eintrag_id))


# ── Fotos an Gebaeude ───────────────────────────────────────────────────────

@router.post("/gebaeude/{gebaeude_id}")
async def beleg_hochladen_gebaeude(
    gebaeude_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    if db.get(Gebaeude, gebaeude_id) is None:
        raise HTTPException(404, "Gebäude nicht gefunden")
    return await _beleg_anlegen(datei, f"gebaeude-{gebaeude_id}", db, user, gebaeude_id=gebaeude_id)


@router.get("/gebaeude/{gebaeude_id}")
def belege_liste_gebaeude(
    gebaeude_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    belege = db.query(Beleg).filter(Beleg.gebaeude_id == gebaeude_id).order_by(Beleg.id).all()
    return [{"id": b.id, "dateiname": b.dateiname} for b in belege]


@router.get("/gebaeude/{gebaeude_id}/{beleg_id}/datei")
def beleg_datei_gebaeude(
    gebaeude_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_antwort(_beleg_holen(db, beleg_id, Beleg.gebaeude_id, gebaeude_id))


@router.delete("/gebaeude/{gebaeude_id}/{beleg_id}")
def beleg_loeschen_gebaeude(
    gebaeude_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return _beleg_entfernen(db, _beleg_holen(db, beleg_id, Beleg.gebaeude_id, gebaeude_id))


# ── Foto an einer Zählerablesung ────────────────────────────────────────────
# Nicht require_admin, sondern get_current_user wie die Ablesungen selbst
# (siehe routers/gebaeude.py): Ablesen ist Alltagsarbeit, Stammdaten nicht.
# Zugeschnitten und gedreht wird im Browser - hier kommt nur noch der
# Ausschnitt an.

@router.post("/ablesung/{ablesung_id}")
async def beleg_hochladen_ablesung(
    ablesung_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    if db.get(ZaehlerAblesung, ablesung_id) is None:
        raise HTTPException(404, "Ablesung nicht gefunden")
    # Genau ein Foto je Ablesung: ein neues ersetzt das alte, samt Datei.
    for alt in db.query(Beleg).filter(Beleg.zaehler_ablesung_id == ablesung_id).all():
        _beleg_entfernen(db, alt)
    return await _beleg_anlegen(
        datei, f"ablesung-{ablesung_id}", db, user, zaehler_ablesung_id=ablesung_id
    )


@router.get("/ablesung/{ablesung_id}")
def belege_liste_ablesung(
    ablesung_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    belege = db.query(Beleg).filter(Beleg.zaehler_ablesung_id == ablesung_id).order_by(Beleg.id).all()
    return [{"id": b.id, "dateiname": b.dateiname} for b in belege]


@router.get("/ablesung/{ablesung_id}/{beleg_id}/datei")
def beleg_datei_ablesung(
    ablesung_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_antwort(_beleg_holen(db, beleg_id, Beleg.zaehler_ablesung_id, ablesung_id))


@router.delete("/ablesung/{ablesung_id}/{beleg_id}")
def beleg_loeschen_ablesung(
    ablesung_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_entfernen(db, _beleg_holen(db, beleg_id, Beleg.zaehler_ablesung_id, ablesung_id))


# ── Unterlagen am Vertrag ───────────────────────────────────────────────────
# Police, Nachtrag, Preiserhoehung, Kuendigungsschreiben: sie gehoeren zum
# Vertrag und nicht zu einer einzelnen Zahlung, an der sie nur zufaellig
# haengen wuerden. Mehrere je Vertrag, anders als beim Zaehlerfoto - ein
# Vertrag sammelt seine Unterlagen ueber Jahre.

@router.post("/vertrag/{vertrag_id}")
async def beleg_hochladen_vertrag(
    vertrag_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    if db.get(Vertrag, vertrag_id) is None:
        raise HTTPException(404, "Vertrag nicht gefunden")
    return await _beleg_anlegen(datei, f"vertrag-{vertrag_id}", db, user, vertrag_id=vertrag_id)


@router.get("/vertrag/{vertrag_id}")
def belege_liste_vertrag(
    vertrag_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    belege = db.query(Beleg).filter(Beleg.vertrag_id == vertrag_id).order_by(Beleg.id).all()
    return [{"id": b.id, "dateiname": b.dateiname} for b in belege]


@router.get("/vertrag/{vertrag_id}/{beleg_id}/datei")
def beleg_datei_vertrag(
    vertrag_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_antwort(_beleg_holen(db, beleg_id, Beleg.vertrag_id, vertrag_id))


@router.delete("/vertrag/{vertrag_id}/{beleg_id}")
def beleg_loeschen_vertrag(
    vertrag_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return _beleg_entfernen(db, _beleg_holen(db, beleg_id, Beleg.vertrag_id, vertrag_id))


# ── Unterlagen am Fahrzeug ──────────────────────────────────────────────────
# Fahrzeugschein, HU-Bericht, Werkstattrechnung, Leasingvertrag. Wie beim
# Vertrag mehrere je Fahrzeug: ein Fahrzeug sammelt seine Unterlagen ueber
# Jahre, und sie gehoeren dem Fahrzeug, nicht einer einzelnen Zahlung.
#
# Gelesen von jedem angemeldeten Benutzer, geschrieben nur von Admins -
# dieselbe Teilung wie am Vertrag. Beim Loeschen des Fahrzeugs raeumt
# `routers/fahrzeuge.delete_fahrzeug` den Ordner `fahrzeug-<id>` selbst ab; die
# Kaskade der Datenbank kennt nur die Zeilen.

@router.post("/fahrzeug/{fahrzeug_id}")
async def beleg_hochladen_fahrzeug(
    fahrzeug_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    user=Depends(require_admin),
):
    if db.get(Fahrzeug, fahrzeug_id) is None:
        raise HTTPException(404, "Fahrzeug nicht gefunden")
    return await _beleg_anlegen(datei, f"fahrzeug-{fahrzeug_id}", db, user, fahrzeug_id=fahrzeug_id)


@router.get("/fahrzeug/{fahrzeug_id}")
def belege_liste_fahrzeug(
    fahrzeug_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    belege = db.query(Beleg).filter(Beleg.fahrzeug_id == fahrzeug_id).order_by(Beleg.id).all()
    return [{"id": b.id, "dateiname": b.dateiname} for b in belege]


@router.get("/fahrzeug/{fahrzeug_id}/{beleg_id}/datei")
def beleg_datei_fahrzeug(
    fahrzeug_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    return _beleg_antwort(_beleg_holen(db, beleg_id, Beleg.fahrzeug_id, fahrzeug_id))


@router.delete("/fahrzeug/{fahrzeug_id}/{beleg_id}")
def beleg_loeschen_fahrzeug(
    fahrzeug_id: int,
    beleg_id: int,
    db: Session = Depends(get_db),
    _=Depends(require_admin),
):
    return _beleg_entfernen(db, _beleg_holen(db, beleg_id, Beleg.fahrzeug_id, fahrzeug_id))
