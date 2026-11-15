"""Lese/Schreibe Anwendungseinstellungen aus config/backup.json."""

import io
import json
import logging
import re
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_admin
from app.config import settings
from app.database import engine, get_db
from app.db_init import init_db_schema
from app.db_registry import aktive_id, lese_eintraege
from app.models import Benutzer, Kategorie, KassenzettelMuster, KontoauszugMuster
from app.schemas import MwstKatEintrag
from app.services import einstellungen as einst
from app.services.ocr.dispatcher import baue_profil, kategorie_map
from app.services.ocr.preprocess import verbessere_und_lies
from app.services.ocr.parser import parse_kassenzettel
from app.services.pdf_import.dispatcher import _parser_fuer_muster
from app.services.pdf_import.render import render_erste_seite_png
from app.pfade import daten_dir, einstellungen_dir, programm_dir

log = logging.getLogger(__name__)

router = APIRouter(prefix="/einstellungen", tags=["einstellungen"])

# _DATEN und _PROGRAMM sind in der Entwicklung derselbe Ordner, in der
# Produktion nicht: Belege, Backups und Einstellungen liegen beim Datenordner,
# das Backup-Skript beim Programm. Siehe app.pfade.
_DATEN      = daten_dir()
_PROGRAMM   = programm_dir()
_CONFIG_DIR = einstellungen_dir()
_BACKUP_CFG = _CONFIG_DIR / "backup.json"
_BACKUP_PY  = _PROGRAMM / "scripts" / "backup.py"

_DEFAULTS: dict = {
    "aktiviert": True,
    "ziel_ordner": "",
    "uhrzeit": "02:00",
    "behalten": 30,
    "task_name": "HaushaltsfinanzBackup",
}


def _lese_backup_cfg() -> dict:
    if _BACKUP_CFG.exists():
        try:
            data = json.loads(_BACKUP_CFG.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **data}
        except Exception:
            pass
    return dict(_DEFAULTS)


def _schreibe_backup_cfg(data: dict) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _BACKUP_CFG.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class BackupEinstellungen(BaseModel):
    aktiviert: bool
    ziel_ordner: str
    uhrzeit: str           # HH:MM
    behalten: int
    task_name: str


class BackupErgebnis(BaseModel):
    ok: bool
    meldung: Optional[str] = None


class BackupEintrag(BaseModel):
    name: str        # YYYY-MM-DD_HH-MM
    db_groesse: int  # Bytes
    # Herkunft laut backup_meta.json im ZIP. None = Backup aus der Zeit vor der
    # Mehrfach-DB-Verwaltung, Herkunft unbekannt.
    datenbank_id: Optional[int] = None
    datenbank_name: Optional[str] = None
    fremd: bool = False  # stammt nachweislich aus einer anderen als der aktiven DB


# Name der Herkunfts-Datei im ZIP – geschrieben von scripts/backup.py
_META_NAME = "backup_meta.json"


def _lese_backup_meta(zip_pfad: Path) -> Optional[dict]:
    """Herkunftsangaben aus dem ZIP, oder None bei alten ZIPs ohne Metadatei."""
    try:
        with zipfile.ZipFile(zip_pfad) as zf:
            if _META_NAME not in zf.namelist():
                return None
            return json.loads(zf.read(_META_NAME).decode("utf-8"))
    except Exception:
        return None


@router.get("/backup", response_model=BackupEinstellungen)
def get_backup(_: Benutzer = Depends(require_admin)):
    return _lese_backup_cfg()


@router.put("/backup", response_model=BackupEinstellungen)
def put_backup(body: BackupEinstellungen, _: Benutzer = Depends(require_admin)):
    data = body.model_dump()
    _schreibe_backup_cfg(data)
    return data


@router.get("/backup/liste", response_model=list[BackupEintrag])
def backup_liste(_: Benutzer = Depends(require_admin)):
    """Listet alle vorhandenen ZIP-Backups im konfigurierten Zielordner."""
    cfg = _lese_backup_cfg()
    ziel = Path(cfg.get("ziel_ordner") or str(_DATEN / "backups"))
    if not ziel.exists():
        return []
    eigene_id = aktive_id()
    eintraege = []
    for f in sorted(ziel.iterdir(), key=lambda x: x.name, reverse=True):
        if f.is_file() and f.suffix == ".zip" and re.match(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}\.zip$", f.name):
            meta = _lese_backup_meta(f) or {}
            quell_id = meta.get("datenbank_id")
            eintraege.append(BackupEintrag(
                name=f.stem,
                db_groesse=f.stat().st_size,
                datenbank_id=quell_id,
                datenbank_name=meta.get("datenbank_name"),
                fremd=quell_id is not None and quell_id != eigene_id,
            ))
    return eintraege


# Datei-Ablagen, die scripts/backup.py mitsichert (gleiche Schluessel dort in
# DATEI_ABLAGEN). Der Restore spiegelt sie auf den Backup-Stand, damit nach dem
# Wiederherstellen nicht jeder Beleg und jeder archivierte Kontoauszug der DB
# auf eine fehlende Datei zeigt.
def _datei_ablagen() -> dict[str, Path]:
    return {
        "belege": settings.belege_dir,
        "kontoauszuege": settings.kontoauszuege_dir,
        "kontoauszug_muster": settings.kontoauszug_muster_dir,
        "kassenzettel_muster": settings.kassenzettel_muster_dir,
    }


def _archiv_praefixe(meta: Optional[dict]) -> dict[str, str]:
    """Ordnername jeder Ablage im ZIP, Schluessel -> Praefix.

    Neue Backups schreiben die Zuordnung in backup_meta.json; der Ablageort
    beim Sichern kann ein anderer sein als beim Wiederherstellen (Produktion
    unter ProgramData, Entwicklung im Projektstamm). Fuer aeltere ZIPs ohne die
    Angabe gilt der Pfad relativ zum eigenen Datenordner - so, wie diese
    Fassung ihn selbst geschrieben haette.
    """
    gespeichert = (meta or {}).get("ablagen") or {}
    praefixe: dict[str, str] = {}
    for schluessel, ablage in _datei_ablagen().items():
        wert = gespeichert.get(schluessel)
        if isinstance(wert, str) and wert:
            praefixe[schluessel] = wert.strip("/")
            continue
        try:
            praefixe[schluessel] = ablage.resolve().relative_to(_DATEN.resolve()).as_posix()
        except ValueError:
            # Ablage liegt ausserhalb des Datenordners (eigener FINANZ_*-Pfad)
            # und das ZIP sagt nicht, wo sie darin steckt - nichts zu spiegeln.
            continue
    return praefixe


def _ablagen_wiederherstellen(
    zf: zipfile.ZipFile, stempel: str, meta: Optional[dict] = None
) -> tuple[int, list[str]]:
    """Setzt die Dateiordner exakt auf den Stand des ZIPs.

    Der bisherige Ordner wird nicht gelöscht, sondern nach
    <ordner>.vor-restore-<stempel> umbenannt: ein versehentlicher Restore
    kostet sonst unwiederbringlich alle Fotos und Auszüge, die seit dem Backup
    entstanden sind. Die beiseitegelegten Ordner darf man von Hand löschen.
    """
    namen = zf.namelist()
    anzahl = 0
    beiseite: list[str] = []
    praefixe = _archiv_praefixe(meta)
    ablagen = _datei_ablagen()

    for schluessel, praefix in praefixe.items():
        ablage = ablagen[schluessel]
        praefix = f"{praefix}/"
        eintraege = [n for n in namen if n.startswith(praefix) and not n.endswith("/")]
        if not eintraege:
            # Der Ordner kam im Backup nicht vor (altes ZIP oder leerer Ordner) –
            # dann den vorhandenen Stand nicht antasten.
            continue

        if ablage.exists() and any(ablage.iterdir()):
            alt = ablage.with_name(f"{ablage.name}.vor-restore-{stempel}")
            ablage.rename(alt)
            beiseite.append(alt.name)
        ablage.mkdir(parents=True, exist_ok=True)

        for eintrag in eintraege:
            # Ziel aus dem heutigen Ablageort plus dem Pfad INNERHALB der
            # Ablage: der Datenordner des Backups spielt keine Rolle mehr.
            ziel = ablage / eintrag[len(praefix) :]
            # Ein ZIP ist fremde Eingabe: ein Eintrag mit ".." darin wuerde
            # sonst ausserhalb der Ablage schreiben.
            try:
                ziel.resolve().relative_to(ablage.resolve())
            except ValueError:
                continue
            ziel.parent.mkdir(parents=True, exist_ok=True)
            ziel.write_bytes(zf.read(eintrag))
            anzahl += 1

    return anzahl, beiseite


@router.post("/backup/wiederherstellen/{name}", response_model=BackupErgebnis)
def backup_wiederherstellen(
    name: str,
    erzwingen: bool = False,
    _: Benutzer = Depends(require_admin),
):
    """Stellt die Datenbank aus einer ZIP-Backup-Datei wieder her.

    Ziel ist immer die aktuell aktive DB (settings.db_path). Stammt das Backup
    laut seiner Metadatei aus einer anderen registrierten DB, bricht der Restore
    ab – sonst überschriebe z.B. ein Backup der DB „Firma“ unbemerkt die gerade
    aktive DB „Privat“. Mit erzwingen=true ist das bewusst möglich.
    """
    if not re.match(r"^\d{4}-\d{2}-\d{2}_\d{2}-\d{2}$", name):
        raise HTTPException(400, "Ungültiger Backup-Name")
    cfg = _lese_backup_cfg()
    ziel = Path(cfg.get("ziel_ordner") or str(_DATEN / "backups"))
    zip_pfad = ziel / f"{name}.zip"
    if not zip_pfad.exists():
        raise HTTPException(404, "Backup-ZIP nicht gefunden")

    meta = _lese_backup_meta(zip_pfad)
    if meta and not erzwingen:
        # Fehlt die Metadatei (altes ZIP), ist die Herkunft unbekannt – dann
        # bleibt es beim bisherigen Verhalten und wir lassen den Restore zu.
        quell_id = meta.get("datenbank_id")
        eigene_id = aktive_id()
        if quell_id is not None and quell_id != eigene_id:
            quelle = meta.get("datenbank_name") or f"ID {quell_id}"
            aktive_name = next(
                (e.get("name") for e in lese_eintraege() if e.get("id") == eigene_id),
                None,
            ) or "aktive Datenbank"
            return BackupErgebnis(
                ok=False,
                meldung=(
                    f"Dieses Backup stammt aus der Datenbank „{quelle}“, aktiv ist "
                    f"„{aktive_name}“. Wiederherstellen würde „{aktive_name}“ mit "
                    f"fremden Daten überschreiben."
                ),
            )

    try:
        # Offene Pool-Verbindungen schließen: sie halten Lesesperren auf der
        # Zieldatei und einen Seiten-Cache, der nach dem Überschreiben veraltet
        # wäre.
        engine.dispose()

        dateien = 0
        beiseite: list[str] = []
        stempel = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

        with tempfile.TemporaryDirectory() as tmp:
            with zipfile.ZipFile(zip_pfad) as zf:
                zf.extract("finanzen.db", tmp)
                # Die DB läuft im WAL-Modus (siehe app.database), backup.py legt
                # das WAL deshalb mit ins ZIP. Ohne das WAL daneben fehlen alle
                # Transaktionen, die zum Backup-Zeitpunkt noch nicht in die
                # .db-Datei eingecheckpointet waren. SQLite spielt es beim
                # Öffnen automatisch ein.
                if "finanzen.db-wal" in zf.namelist():
                    zf.extract("finanzen.db-wal", tmp)
                # Noch im offenen ZIP: Belege, Kontoauszuege und Muster
                # zurueckschreiben.
                dateien, beiseite = _ablagen_wiederherstellen(zf, stempel, meta)
            tmp_db = Path(tmp) / "finanzen.db"
            src = sqlite3.connect(str(tmp_db))
            dst = sqlite3.connect(str(settings.db_path))
            try:
                src.backup(dst)
            finally:
                src.close()
                dst.close()

        # Ausstehende Migrationen sofort anwenden – sonst liefe der Server bis
        # zum Neustart gegen das (womöglich ältere) Schema des Backups.
        init_db_schema(engine)
        engine.dispose()

        meldung = f"Wiederhergestellt aus {name}: Datenbank"
        if dateien:
            meldung += f" und {dateien} Dateien (Belege, Kontoauszüge, Muster)"
        meldung += ". Bitte Server neu starten."
        if beiseite:
            meldung += (
                " Der bisherige Dateistand liegt als "
                + ", ".join(beiseite)
                + " daneben und kann nach der Prüfung gelöscht werden."
            )
        return BackupErgebnis(ok=True, meldung=meldung)
    except Exception as exc:
        return BackupErgebnis(ok=False, meldung=str(exc))


def fuehre_backup_aus() -> BackupErgebnis:
    """Löst ein sofortiges Backup der aktuell aktiven DB aus (settings.db_path).

    Wiederverwendet von backup_jetzt() sowie vom Datenbank-Wechseln-Endpoint
    (backend/app/routers/datenbanken.py), der vor jedem Wechsel ein Backup
    der bisherigen aktiven DB erzwingt.
    """
    if not _BACKUP_PY.exists():
        raise HTTPException(500, "backup.py nicht gefunden")
    cfg = _lese_backup_cfg()
    cmd = [sys.executable, str(_BACKUP_PY)]
    if cfg.get("ziel_ordner"):
        cmd += ["--ziel", cfg["ziel_ordner"]]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            return BackupErgebnis(ok=False, meldung=result.stderr.strip() or result.stdout.strip())
        letzte_zeile = result.stdout.strip().splitlines()[-1] if result.stdout.strip() else "OK"
        return BackupErgebnis(ok=True, meldung=letzte_zeile)
    except subprocess.TimeoutExpired:
        return BackupErgebnis(ok=False, meldung="Backup-Timeout (120 s)")
    except Exception as e:
        return BackupErgebnis(ok=False, meldung=str(e))


@router.post("/backup/jetzt", response_model=BackupErgebnis)
def backup_jetzt(_: Benutzer = Depends(require_admin)):
    """Löst ein sofortiges Backup aus."""
    return fuehre_backup_aus()


# =====================================================================
# Import-Abgleich: Toleranzen der PDF-Vorschau
# =====================================================================


class ImportAbgleichEinstellungen(BaseModel):
    betrag_toleranz: float = Field(ge=0, le=einst.MAX_BETRAG_TOLERANZ)
    tage_toleranz: int = Field(ge=0, le=einst.MAX_TAGE_TOLERANZ)


@router.get("/import-abgleich", response_model=ImportAbgleichEinstellungen)
def get_import_abgleich(db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    return ImportAbgleichEinstellungen(
        betrag_toleranz=einst.betrag_toleranz(db),
        tage_toleranz=einst.tage_toleranz(db),
    )


@router.put("/import-abgleich", response_model=ImportAbgleichEinstellungen)
def put_import_abgleich(
    body: ImportAbgleichEinstellungen,
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    einst.schreibe(db, einst.BETRAG_TOLERANZ, str(body.betrag_toleranz))
    einst.schreibe(db, einst.TAGE_TOLERANZ, str(body.tage_toleranz))
    db.commit()
    return body


# =====================================================================
# Dashboard-Anzeigeoptionen
# =====================================================================


class DashboardEinstellungen(BaseModel):
    finanzsaldo: bool
    # Schwellen der Erinnerungen. Grenzen wie in app.services.einstellungen.
    erinnerung_import_tage: int = Field(35, ge=1, le=365)
    erinnerung_vorlauf_monate: int = Field(3, ge=1, le=24)
    # Je Art ein Schalter. Die Schwelle bleibt auch bei "aus" erhalten, damit
    # der eingestellte Wert beim Wiedereinschalten wieder gilt.
    erinnerung_ablesungen_an: bool = True
    erinnerung_import_an: bool = True
    erinnerung_vorlauf_an: bool = True
    erinnerung_ueberfaellig_an: bool = True


# Lesend bewusst ohne require_admin: jeder angemeldete Benutzer rendert damit
# sein Dashboard. Geschrieben wird weiterhin nur von Admins.
@router.get("/dashboard", response_model=DashboardEinstellungen)
def get_dashboard(db: Session = Depends(get_db), _: Benutzer = Depends(get_current_user)):
    return DashboardEinstellungen(
        finanzsaldo=einst.dashboard_finanzsaldo(db),
        erinnerung_import_tage=einst.erinnerung_import_tage(db),
        erinnerung_vorlauf_monate=einst.erinnerung_vorlauf_monate(db),
        erinnerung_ablesungen_an=einst.erinnerung_ablesungen_an(db),
        erinnerung_import_an=einst.erinnerung_import_an(db),
        erinnerung_vorlauf_an=einst.erinnerung_vorlauf_an(db),
        erinnerung_ueberfaellig_an=einst.erinnerung_ueberfaellig_an(db),
    )


@router.put("/dashboard", response_model=DashboardEinstellungen)
def put_dashboard(
    body: DashboardEinstellungen,
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    einst.schreibe(db, einst.DASHBOARD_FINANZSALDO, "1" if body.finanzsaldo else "0")
    einst.schreibe(db, einst.ERINNERUNG_IMPORT_TAGE, str(body.erinnerung_import_tage))
    einst.schreibe(db, einst.ERINNERUNG_VORLAUF_MONATE, str(body.erinnerung_vorlauf_monate))
    for schluessel, an in (
        (einst.ERINNERUNG_ABLESUNGEN_AN, body.erinnerung_ablesungen_an),
        (einst.ERINNERUNG_IMPORT_AN, body.erinnerung_import_an),
        (einst.ERINNERUNG_VORLAUF_AN, body.erinnerung_vorlauf_an),
        (einst.ERINNERUNG_UEBERFAELLIG_AN, body.erinnerung_ueberfaellig_an),
    ):
        einst.schreibe(db, schluessel, "1" if an else "0")
    db.commit()
    return body


# =====================================================================
# Kontoauszug-Muster (Phase 9)
# =====================================================================

_MUSTER_DIR = settings.kontoauszug_muster_dir
MAX_PDF_MB = 20

# Ziel-DB-Attribute, auf die ein Muster-Feld zeigen kann (für die UI-Legende).
ZIEL_ATTRIBUTE = [
    {"attribut": "datum", "label": "Datum"},
    {"attribut": "betrag", "label": "Betrag"},
    {"attribut": "empfaenger", "label": "Empfänger"},
    {"attribut": "verwendungszweck", "label": "Verwendungszweck"},
    {"attribut": "iban_empfaenger", "label": "IBAN Gegenseite"},
    {"attribut": "konto_hinweis", "label": "Konto-IBAN (Header)"},
]


class FeldMarkierung(BaseModel):
    attribut: str
    label: Optional[str] = None
    x: float          # relativ 0..1
    y: float
    w: float
    h: float


class MusterOut(BaseModel):
    id: int
    name: str
    bank_key: str
    parser_key: Optional[str]
    erkennung_keywords: list[str]
    feld_markierungen: list[FeldMarkierung]
    aktiv: bool
    notiz: Optional[str]
    erstellt_am: Optional[str]
    hat_screenshot: bool
    hat_pdf: bool


class MusterUpdate(BaseModel):
    name: Optional[str] = None
    parser_key: Optional[str] = None
    erkennung_keywords: Optional[list[str]] = None
    feld_markierungen: Optional[list[FeldMarkierung]] = None
    aktiv: Optional[bool] = None
    notiz: Optional[str] = None


class ProbeBuchung(BaseModel):
    datum: str
    betrag: float
    empfaenger: Optional[str] = None
    verwendungszweck: Optional[str] = None


class MusterMitProbe(BaseModel):
    muster: MusterOut
    bank: str
    konto_hinweis: Optional[str] = None
    probe: list[ProbeBuchung]
    fehler: list[str]


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (s or "").lower()).strip("-")
    return s or "muster"


def _eindeutiger_bank_key(db: Session, basis: str) -> str:
    key = _slug(basis)
    kandidat = key
    n = 2
    while db.query(KontoauszugMuster).filter(KontoauszugMuster.bank_key == kandidat).first():
        kandidat = f"{key}-{n}"
        n += 1
    return kandidat


def _pdf_pfad(bank_key: str) -> Path:
    return _MUSTER_DIR / f"{bank_key}.pdf"


def _png_pfad(bank_key: str) -> Path:
    return _MUSTER_DIR / f"{bank_key}.png"


def _muster_out(m: KontoauszugMuster) -> MusterOut:
    try:
        keywords = json.loads(m.erkennung_keywords or "[]")
    except (ValueError, TypeError):
        keywords = []
    try:
        markierungen = json.loads(m.feld_markierungen or "[]")
    except (ValueError, TypeError):
        markierungen = []
    return MusterOut(
        id=m.id,
        name=m.name,
        bank_key=m.bank_key,
        parser_key=m.parser_key,
        erkennung_keywords=[str(k) for k in keywords],
        feld_markierungen=markierungen,
        aktiv=bool(m.aktiv),
        notiz=m.notiz,
        erstellt_am=str(m.erstellt_am) if m.erstellt_am else None,
        hat_screenshot=bool(m.screenshot_pfad) and _png_pfad(m.bank_key).exists(),
        hat_pdf=bool(m.beispiel_pdf_pfad) and _pdf_pfad(m.bank_key).exists(),
    )


def _probe(m: KontoauszugMuster, pdf_bytes: bytes) -> MusterMitProbe:
    """Best-Effort-Vorschau anhand des Muster-Parsers."""
    parser = _parser_fuer_muster(m)
    result = parser.parse(pdf_bytes)
    probe = [
        ProbeBuchung(datum=b.datum, betrag=b.betrag,
                     empfaenger=b.empfaenger, verwendungszweck=b.verwendungszweck)
        for b in result.buchungen[:25]
    ]
    return MusterMitProbe(
        muster=_muster_out(m), bank=result.bank,
        konto_hinweis=result.konto_hinweis, probe=probe, fehler=result.fehler,
    )


async def _lese_pdf(datei: UploadFile) -> bytes:
    if datei.content_type not in ("application/pdf", "application/octet-stream"):
        if not (datei.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "Nur PDF-Dateien erlaubt")
    pdf_bytes = await datei.read()
    if len(pdf_bytes) > MAX_PDF_MB * 1024 * 1024:
        raise HTTPException(413, f"PDF zu groß (max. {MAX_PDF_MB} MB)")
    return pdf_bytes


def _speichere_beispiel(m: KontoauszugMuster, pdf_bytes: bytes) -> None:
    """Beispiel-PDF dauerhaft speichern + erste Seite als Screenshot rendern."""
    _MUSTER_DIR.mkdir(exist_ok=True)
    pdf_pfad = _pdf_pfad(m.bank_key)
    pdf_pfad.write_bytes(pdf_bytes)
    m.beispiel_pdf_pfad = pdf_pfad.name
    try:
        png = render_erste_seite_png(pdf_bytes)
        _png_pfad(m.bank_key).write_bytes(png)
        m.screenshot_pfad = _png_pfad(m.bank_key).name
    except Exception:
        m.screenshot_pfad = None


@router.get("/kontoauszug-muster/ziel-attribute")
def muster_ziel_attribute(_: Benutzer = Depends(require_admin)):
    return ZIEL_ATTRIBUTE


@router.get("/kontoauszug-muster", response_model=list[MusterOut])
def muster_liste(db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    rows = db.query(KontoauszugMuster).order_by(KontoauszugMuster.id).all()
    return [_muster_out(m) for m in rows]


@router.post("/kontoauszug-muster/upload", response_model=MusterMitProbe)
async def muster_upload(
    name: str = Form(...),
    keywords: Optional[str] = Form(default=None),
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    """Neues Muster aus Beispiel-PDF: speichert PDF + Screenshot, Probe via generischem Parser."""
    pdf_bytes = await _lese_pdf(datei)
    kw_liste = [k.strip() for k in (keywords or "").split(",") if k.strip()]
    m = KontoauszugMuster(
        name=name.strip() or "Neues Muster",
        bank_key=_eindeutiger_bank_key(db, name),
        parser_key=None,
        erkennung_keywords=json.dumps(kw_liste, ensure_ascii=False),
        feld_markierungen="[]",
        aktiv=True,
        erstellt_am=datetime.utcnow(),
    )
    db.add(m)
    db.flush()
    _speichere_beispiel(m, pdf_bytes)
    db.commit()
    db.refresh(m)
    return _probe(m, pdf_bytes)


@router.put("/kontoauszug-muster/{muster_id}", response_model=MusterOut)
def muster_update(
    muster_id: int,
    body: MusterUpdate,
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    m = db.get(KontoauszugMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    if body.name is not None:
        m.name = body.name.strip() or m.name
    if body.parser_key is not None:
        m.parser_key = body.parser_key or None
    if body.erkennung_keywords is not None:
        m.erkennung_keywords = json.dumps(
            [k.strip() for k in body.erkennung_keywords if k.strip()], ensure_ascii=False)
    if body.feld_markierungen is not None:
        m.feld_markierungen = json.dumps(
            [fm.model_dump() for fm in body.feld_markierungen], ensure_ascii=False)
    if body.aktiv is not None:
        m.aktiv = body.aktiv
    if body.notiz is not None:
        m.notiz = body.notiz
    db.commit()
    db.refresh(m)
    return _muster_out(m)


@router.post("/kontoauszug-muster/{muster_id}/beispiel", response_model=MusterMitProbe)
async def muster_beispiel_ersetzen(
    muster_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    """Beispiel-PDF eines bestehenden Musters (neu) hochladen + Screenshot rendern."""
    m = db.get(KontoauszugMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    pdf_bytes = await _lese_pdf(datei)
    _speichere_beispiel(m, pdf_bytes)
    db.commit()
    db.refresh(m)
    return _probe(m, pdf_bytes)


@router.get("/kontoauszug-muster/{muster_id}/screenshot")
def muster_screenshot(
    muster_id: int,
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    m = db.get(KontoauszugMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    pfad = _png_pfad(m.bank_key)
    if not pfad.exists():
        raise HTTPException(404, "Kein Screenshot vorhanden")
    return Response(content=pfad.read_bytes(), media_type="image/png")


@router.delete("/kontoauszug-muster/{muster_id}")
def muster_loeschen(
    muster_id: int,
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    m = db.get(KontoauszugMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    for pfad in (_pdf_pfad(m.bank_key), _png_pfad(m.bank_key)):
        try:
            pfad.unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(m)
    db.commit()
    return {"ok": True}


# =====================================================================
# Kassenzettel-Muster (Phase 10) – datengetriebener OCR-Import pro Geschäft
# =====================================================================

_KZ_DIR = settings.kassenzettel_muster_dir
MAX_BILD_MB = 15
# Von Pillow gemeldetes Format → Dateiendung (MPO = Mehrbild-JPEG aus Handykameras)
_BILD_FORMATE = {
    "JPEG": ".jpg",
    "MPO": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
}


class KzFeldMarkierung(BaseModel):
    label: str
    x: float          # relativ 0..1, bezogen auf das verarbeitete (entzerrte) Bild
    y: float
    w: float
    h: float


class KzMusterOut(BaseModel):
    id: int
    name: str
    geschaeft_key: str
    geschaeft_id: Optional[int] = None
    erkennung_keywords: list[str]
    start_marker: Optional[str]
    stop_marker: Optional[str]
    skip_keywords: list[str]
    preis_regex: Optional[str]
    mwst_kategorie_map: list[MwstKatEintrag]
    feld_markierungen: list[KzFeldMarkierung]
    aktiv: bool
    notiz: Optional[str]
    erstellt_am: Optional[str]
    hat_bild: bool


class KzMusterCreate(BaseModel):
    name: str
    erkennung_keywords: list[str] = []


class KzMusterUpdate(BaseModel):
    name: Optional[str] = None
    erkennung_keywords: Optional[list[str]] = None
    start_marker: Optional[str] = None
    stop_marker: Optional[str] = None
    skip_keywords: Optional[list[str]] = None
    preis_regex: Optional[str] = None
    mwst_kategorie_map: Optional[list[MwstKatEintrag]] = None
    feld_markierungen: Optional[list[KzFeldMarkierung]] = None
    aktiv: Optional[bool] = None
    notiz: Optional[str] = None


class KzProbePosition(BaseModel):
    bezeichnung: str
    menge: float
    einzelpreis: Optional[float] = None
    gesamtpreis: float
    mwst_satz: Optional[float] = None
    mwst_schluessel: Optional[str] = None


class KzProbe(BaseModel):
    muster: KzMusterOut
    rohtext: str
    konfidenz: Optional[float] = None
    positionen: list[KzProbePosition]
    erkannte_schluessel: list[str]
    ocr_variante: Optional[str] = None
    ocr_segmentiert: Optional[bool] = None
    ocr_preiszeilen: Optional[int] = None
    hat_vorschau: bool = False
    fehler: Optional[str] = None


def _eindeutiger_geschaeft_key(db: Session, basis: str) -> str:
    key = _slug(basis)
    kandidat = key
    n = 2
    while db.query(KassenzettelMuster).filter(KassenzettelMuster.geschaeft_key == kandidat).first():
        kandidat = f"{key}-{n}"
        n += 1
    return kandidat


def _kz_bild_pfad(m: KassenzettelMuster) -> Optional[Path]:
    if not m.beispiel_bild_pfad:
        return None
    return _KZ_DIR / m.beispiel_bild_pfad


def _kz_muster_out(m: KassenzettelMuster) -> KzMusterOut:
    def liste(text: Optional[str]) -> list:
        try:
            wert = json.loads(text or "[]")
            return wert if isinstance(wert, list) else []
        except (ValueError, TypeError):
            return []

    bild = _kz_bild_pfad(m)
    return KzMusterOut(
        id=m.id,
        name=m.name,
        geschaeft_key=m.geschaeft_key,
        geschaeft_id=m.geschaeft_id,
        erkennung_keywords=[str(k) for k in liste(m.erkennung_keywords)],
        start_marker=m.start_marker,
        stop_marker=m.stop_marker,
        skip_keywords=[str(k) for k in liste(m.skip_keywords)],
        preis_regex=m.preis_regex,
        mwst_kategorie_map=[
            MwstKatEintrag(schluessel=str(k), kategorie_id=int(v))
            for k, v in kategorie_map(m).items()
        ],
        feld_markierungen=[KzFeldMarkierung(**fm) for fm in liste(m.feld_markierungen)],
        aktiv=bool(m.aktiv),
        notiz=m.notiz,
        erstellt_am=str(m.erstellt_am) if m.erstellt_am else None,
        hat_bild=bool(bild and bild.exists()),
    )


def _kz_probe(m: KassenzettelMuster) -> KzProbe:
    """OCR auf dem gespeicherten Beispielfoto + Parsen mit aktuellem Profil.

    Scheitert die Texterkennung (unlesbares Bild, Tesseract-Fehler), ist das
    kein Serverfehler: Das Muster bleibt, und die Probe kommt mit gesetztem
    `fehler` zurück, damit die Oberfläche den Grund nennen kann.
    """
    positionen: list = []
    ocr = None
    fehler: Optional[str] = None
    bild = _kz_bild_pfad(m)
    if bild and bild.exists():
        vorschau_pfad = _KZ_DIR / f"{m.geschaeft_key}_vorschau.jpg"
        try:
            ocr = verbessere_und_lies(bild, speicher_pfad=vorschau_pfad)
            positionen = parse_kassenzettel(ocr.rohtext, baue_profil(m))
        except Exception as exc:
            log.exception("Probe-Extraktion fehlgeschlagen (Muster %s)", m.geschaeft_key)
            ocr = None
            positionen = []
            fehler = f"Texterkennung fehlgeschlagen: {exc}"
    schluessel = sorted({p["mwst_schluessel"] for p in positionen if p.get("mwst_schluessel")})
    vorschau_vorhanden = bool(ocr and (_KZ_DIR / f"{m.geschaeft_key}_vorschau.jpg").exists())
    return KzProbe(
        muster=_kz_muster_out(m),
        rohtext=ocr.rohtext if ocr else "",
        konfidenz=ocr.konfidenz if ocr else None,
        positionen=[KzProbePosition(**p) for p in positionen],
        erkannte_schluessel=schluessel,
        ocr_variante=ocr.variante if ocr else None,
        ocr_segmentiert=ocr.segmentiert if ocr else None,
        ocr_preiszeilen=ocr.preiszeilen if ocr else None,
        hat_vorschau=vorschau_vorhanden,
        fehler=fehler,
    )


async def _lese_bild(datei: UploadFile) -> tuple[bytes, str]:
    """Liest ein hochgeladenes Foto und liefert (Bytes, Dateiendung).

    Die Endung richtet sich nach dem *tatsächlichen* Bildinhalt, nicht nach
    content-type oder Dateiname: Handy-Fotos kommen oft mit falscher oder
    fehlender Typ-Angabe an, und ein Bild, das Pillow nicht öffnen kann,
    würde die OCR später mit einem 500er abbrechen lassen. Lieber hier eine
    verständliche Meldung, bevor das alte Beispielfoto überschrieben wird.
    """
    daten = await datei.read()
    if not daten:
        raise HTTPException(400, "Die Datei ist leer.")
    if len(daten) > MAX_BILD_MB * 1024 * 1024:
        raise HTTPException(413, f"Foto zu groß (max. {MAX_BILD_MB} MB)")
    try:
        with Image.open(io.BytesIO(daten)) as bild:
            bild.verify()
            format_name = (bild.format or "").upper()
    except Exception:
        name = (datei.filename or "Datei").strip()
        if name.lower().endswith((".heic", ".heif")):
            raise HTTPException(
                400,
                f'„{name}" ist ein HEIC/HEIF-Foto – dieses Format kann nicht gelesen '
                'werden. Bitte als JPEG, PNG oder WebP speichern und erneut hochladen.',
            )
        raise HTTPException(
            400,
            f'„{name}" konnte nicht als Bild gelesen werden (beschädigt oder kein '
            'unterstütztes Format). Erlaubt sind JPEG, PNG und WebP.',
        )
    endung = _BILD_FORMATE.get(format_name)
    if endung is None:
        raise HTTPException(
            400,
            f'Format {format_name or "unbekannt"} wird nicht unterstützt – '
            'bitte JPEG, PNG oder WebP hochladen.',
        )
    return daten, endung


@router.get("/kassenzettel-muster/kategorien")
def kz_kategorien(db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    """Aktive Ausgabe-Kategorien für die MwSt→Kategorie-Zuordnung."""
    rows = (
        db.query(Kategorie)
        .filter(Kategorie.aktiv.is_(True))
        .order_by(Kategorie.name)
        .all()
    )
    return [{"id": k.id, "name": k.name, "uebergeordnet_id": k.uebergeordnet_id} for k in rows]


@router.get("/kassenzettel-muster", response_model=list[KzMusterOut])
def kz_liste(db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    rows = db.query(KassenzettelMuster).order_by(KassenzettelMuster.id).all()
    return [_kz_muster_out(m) for m in rows]


@router.post("/kassenzettel-muster", response_model=KzMusterOut)
def kz_anlegen(body: KzMusterCreate, db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    name = body.name.strip() or "Neues Geschäft"
    m = KassenzettelMuster(
        name=name,
        geschaeft_key=_eindeutiger_geschaeft_key(db, name),
        erkennung_keywords=json.dumps(
            [k.strip() for k in body.erkennung_keywords if k.strip()], ensure_ascii=False),
        skip_keywords="[]",
        mwst_kategorie_map="{}",
        feld_markierungen="[]",
        aktiv=True,
        erstellt_am=datetime.utcnow(),
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return _kz_muster_out(m)


@router.put("/kassenzettel-muster/{muster_id}", response_model=KzMusterOut)
def kz_update(
    muster_id: int,
    body: KzMusterUpdate,
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    m = db.get(KassenzettelMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    if body.name is not None:
        m.name = body.name.strip() or m.name
    if body.erkennung_keywords is not None:
        m.erkennung_keywords = json.dumps(
            [k.strip() for k in body.erkennung_keywords if k.strip()], ensure_ascii=False)
    if body.start_marker is not None:
        m.start_marker = body.start_marker.strip() or None
    if body.stop_marker is not None:
        m.stop_marker = body.stop_marker.strip() or None
    if body.skip_keywords is not None:
        m.skip_keywords = json.dumps(
            [k.strip() for k in body.skip_keywords if k.strip()], ensure_ascii=False)
    if body.preis_regex is not None:
        muster_text = body.preis_regex.strip()
        if muster_text:
            try:
                re.compile(muster_text)
            except re.error as exc:
                raise HTTPException(400, f"Ungültiges Preis-Muster (Regex): {exc}")
        m.preis_regex = muster_text or None
    if body.mwst_kategorie_map is not None:
        m.mwst_kategorie_map = json.dumps(
            {e.schluessel.strip(): e.kategorie_id for e in body.mwst_kategorie_map if e.schluessel.strip()},
            ensure_ascii=False)
    if body.feld_markierungen is not None:
        m.feld_markierungen = json.dumps(
            [fm.model_dump() for fm in body.feld_markierungen], ensure_ascii=False)
    if body.aktiv is not None:
        m.aktiv = body.aktiv
    if body.notiz is not None:
        m.notiz = body.notiz
    db.commit()
    db.refresh(m)
    return _kz_muster_out(m)


@router.post("/kassenzettel-muster/{muster_id}/beispiel", response_model=KzProbe)
async def kz_beispiel(
    muster_id: int,
    datei: UploadFile = File(...),
    db: Session = Depends(get_db),
    _: Benutzer = Depends(require_admin),
):
    """Beispiel-Foto (neu) hochladen, speichern und Probe-Extraktion liefern."""
    m = db.get(KassenzettelMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    daten, endung = await _lese_bild(datei)
    _KZ_DIR.mkdir(exist_ok=True)
    # alte Datei mit evtl. anderer Endung entfernen
    altes = _kz_bild_pfad(m)
    if altes and altes.exists() and altes.suffix != endung:
        altes.unlink(missing_ok=True)
    pfad = _KZ_DIR / f"{m.geschaeft_key}{endung}"
    pfad.write_bytes(daten)
    m.beispiel_bild_pfad = pfad.name
    # Koordinaten der Markierungen beziehen sich auf das alte Bild und ergeben
    # bei einem neuen Foto keinen Sinn mehr.
    m.feld_markierungen = "[]"
    db.commit()
    db.refresh(m)
    return _kz_probe(m)


@router.post("/kassenzettel-muster/{muster_id}/probe", response_model=KzProbe)
def kz_probe(muster_id: int, db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    """Probe-Extraktion auf dem gespeicherten Beispielfoto mit aktuellem Profil."""
    m = db.get(KassenzettelMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    return _kz_probe(m)


@router.get("/kassenzettel-muster/{muster_id}/screenshot")
def kz_screenshot(muster_id: int, db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    m = db.get(KassenzettelMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    pfad = _kz_bild_pfad(m)
    if not pfad or not pfad.exists():
        raise HTTPException(404, "Kein Beispielfoto vorhanden")
    media = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(pfad.suffix, "image/jpeg")
    return Response(content=pfad.read_bytes(), media_type=media)


@router.get("/kassenzettel-muster/{muster_id}/vorschau")
def kz_vorschau(muster_id: int, db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    """Liefert das von der OCR-Pipeline entzerrte/verbesserte Foto (erstellt beim letzten Probe-Lauf)."""
    m = db.get(KassenzettelMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    pfad = _KZ_DIR / f"{m.geschaeft_key}_vorschau.jpg"
    if not pfad.exists():
        raise HTTPException(404, "Kein Vorschaubild – erst Probe ausführen")
    return FileResponse(str(pfad), media_type="image/jpeg")


@router.delete("/kassenzettel-muster/{muster_id}")
def kz_loeschen(muster_id: int, db: Session = Depends(get_db), _: Benutzer = Depends(require_admin)):
    m = db.get(KassenzettelMuster, muster_id)
    if not m:
        raise HTTPException(404, "Muster nicht gefunden")
    pfad = _kz_bild_pfad(m)
    if pfad:
        try:
            pfad.unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(m)
    db.commit()
    return {"ok": True}
