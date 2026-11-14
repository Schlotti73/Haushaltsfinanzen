"""Wählt anhand der Kassenzettel-Muster-Registry (DB) das passende Geschäft.

Datengetrieben (Phase 10): Ein Muster pro Geschäft (Aldi, Edeka, Rossmann …)
liefert Erkennungs-Keywords, Artikelbereich-Marker, Skip-Begriffe und das
MwSt-Schlüssel→Kategorie-Mapping. So lassen sich neue Geschäfte über die
Einstellungen pflegen, ohne Code zu ändern.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from sqlalchemy.orm import Session

from app.models import KassenzettelMuster
from app.services.ocr.parser import MusterProfil


def _json_liste(text: Optional[str]) -> list:
    try:
        wert = json.loads(text or "[]")
        return wert if isinstance(wert, list) else []
    except (ValueError, TypeError):
        return []


def _json_dict(text: Optional[str]) -> dict:
    try:
        wert = json.loads(text or "{}")
        return wert if isinstance(wert, dict) else {}
    except (ValueError, TypeError):
        return {}


def waehle_muster(db: Session, rohtext: str) -> Optional[KassenzettelMuster]:
    """Erstes aktives Muster, dessen Erkennungs-Keyword im OCR-Text vorkommt."""
    t = rohtext.lower()
    muster = (
        db.query(KassenzettelMuster)
        .filter(KassenzettelMuster.aktiv.is_(True))
        .order_by(KassenzettelMuster.id)
        .all()
    )
    for m in muster:
        keywords = _json_liste(m.erkennung_keywords)
        if any(str(kw).lower() in t for kw in keywords):
            return m
    return None


def baue_profil(muster: Optional[KassenzettelMuster]) -> Optional[MusterProfil]:
    """Erstellt ein Parser-Profil aus einem Muster-Datensatz (oder None)."""
    if muster is None:
        return None
    preis_regex = None
    if muster.preis_regex:
        try:
            preis_regex = re.compile(muster.preis_regex)
        except re.error:
            preis_regex = None  # ungültiges Muster ignorieren → Standard-Regex
    return MusterProfil(
        start_marker=muster.start_marker or None,
        stop_marker=muster.stop_marker or None,
        skip_keywords=tuple(str(k) for k in _json_liste(muster.skip_keywords)),
        preis_regex=preis_regex,
    )


def kategorie_map(muster: Optional[KassenzettelMuster]) -> dict[str, int]:
    """MwSt-Schlüssel (A/B/1/2 …) → Kategorie-ID laut Muster."""
    if muster is None:
        return {}
    roh = _json_dict(muster.mwst_kategorie_map)
    ergebnis: dict[str, int] = {}
    for schluessel, kat_id in roh.items():
        try:
            ergebnis[str(schluessel)] = int(kat_id)
        except (ValueError, TypeError):
            continue
    return ergebnis
