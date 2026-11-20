"""Texterkennung auf Belegfotos via Tesseract (Phase 8.4)."""

from __future__ import annotations

from pathlib import Path

import pytesseract

# Setzt tesseract_cmd und TESSDATA_PREFIX - siehe dort, warum der
# Sprachdaten-Ordner nicht als --tessdata-dir mitgegeben wird.
from app.services.ocr.tess import KONFIGURATION
from app.services.ocr.preprocess import verbessere_und_lies


def _config(sprache: str) -> tuple[str, str]:
    return sprache, KONFIGURATION


def bild_zu_text(bildpfad: Path, sprache: str = "deu") -> str:
    """Erkennt Text auf einem Belegfoto und liefert den Rohtext."""
    sprache, config = _config(sprache)
    return pytesseract.image_to_string(str(bildpfad), lang=sprache, config=config)


def bild_zu_text_mit_konfidenz(bildpfad: Path, sprache: str = "deu") -> tuple[str, float | None]:
    """Wie `bild_zu_text`, liefert zusätzlich die mittlere Worterkennungssicherheit (0-100).

    Nutzt seit Phase 11 die Bildverbesserungs-Pipeline (Deskew/Crop/Perspektive/
    Binarisierung mit Auto-Auswahl der besten Variante). Ohne OpenCV fällt diese
    automatisch auf die einfache Direkt-OCR zurück."""
    ergebnis = verbessere_und_lies(bildpfad, sprache)
    return ergebnis.rohtext, ergebnis.konfidenz
