"""
PDF-Seiten-Rendering für Kontoauszug-Muster (Phase 9.3).

Rendert die erste Seite eines Kontoauszugs als PNG (via pypdfium2 – keine
externe Abhängigkeit), um sie als Beispiel-Screenshot mit Feld-Markierungen
zu visualisieren.
"""

from __future__ import annotations

import io

import pypdfium2 as pdfium


_CROP_PAD = 30   # Pixel Rand um den Inhalt beim Beschneiden


def _crop_whitespace(img):
    """Schneidet leere weiße Ränder ab (insb. leeres unteres Seitendrittel)."""
    from PIL import ImageOps
    inv = ImageOps.invert(img)
    bbox = inv.getbbox()          # None wenn Seite komplett weiß
    if bbox is None:
        return img
    left   = max(0, bbox[0] - _CROP_PAD)
    top    = max(0, bbox[1] - _CROP_PAD)
    right  = min(img.width,  bbox[2] + _CROP_PAD)
    bottom = min(img.height, bbox[3] + _CROP_PAD)
    return img.crop((left, top, right, bottom))


def render_erste_seite_png(pdf_bytes: bytes, scale: float = 2.0) -> bytes:
    """Erste PDF-Seite → PNG-Bytes, weißer Leerraum unten wird abgeschnitten."""
    pdf = pdfium.PdfDocument(pdf_bytes)
    try:
        if len(pdf) == 0:
            raise ValueError("PDF enthält keine Seiten")
        page = pdf[0]
        bitmap = page.render(scale=scale)
        pil_image = _crop_whitespace(bitmap.to_pil().convert("RGB"))
        puffer = io.BytesIO()
        pil_image.save(puffer, format="PNG")
        return puffer.getvalue()
    finally:
        pdf.close()
