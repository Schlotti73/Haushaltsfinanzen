"""Bildverbesserung für Kassenzettel-OCR (Phasen 11 + 14) – klassische CV, keine KI.

Reale Belegfotos scheitern an Tesseract, weil der Bon klein, schräg, perspektivisch
verzerrt und schwach beleuchtet im Bild liegt. Diese Pipeline erzeugt mehrere
Verbesserungs-Varianten und wählt automatisch die mit dem besten OCR-Ergebnis
(„bis bestes OCR-Ergebnis da ist"):

1. Beleg-Segmentierung: heller Bon auf dunklem Grund → größter heller Blob →
   rotiertes Rechteck → perspektivische Entzerrung (warpPerspective).
2. Schräglauf-Korrektur (Deskew) per minAreaRect.
3. Binarisierungs-/Graustufen-Varianten + 0°/180°-Orientierung.
4. Jede Variante wird per Tesseract bewertet (erkannte Preiszeilen, dann
   mittlere Konfidenz); die beste gewinnt.

Phase 14 – erweiterte Varianten für das Ganzbild:
- CLAHE (Kontrastlimitierte adaptive Histogramm-Egalisierung): hebt Text bei
  ungleichmäßiger Beleuchtung hervor (z.B. Handy-Blitz nur auf einer Seite).
- Schatten-Entfernung: dividiert Bild durch dilated Hintergrundmodell → entfernt
  Beleuchtungsgradienten quer über den Bon.
- Unsharp Masking: verstärkt feine Kanten – hilft bei leicht unscharfen Fotos.
Die drei neuen Varianten werden nur auf das Ganzbild angewendet; der Warp-Pfad
(Perspektivkorrektur) nutzt weiterhin die Basis-Varianten.

Empirisch (siehe Tuning): Handyfoto 0 → 9 Preiszeilen, Scans unverändert gut.

Benötigt OpenCV (opencv-python-headless). Ist es nicht installiert oder lässt
sich das Bild nicht laden (z.B. PDF), wird über `cv2 is None` sauber auf die
einfache Direkt-OCR zurückgefallen.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
import pytesseract

from app.config import settings

try:  # OpenCV ist optional – ohne es greift der Direkt-OCR-Fallback
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore

pytesseract.pytesseract.tesseract_cmd = str(settings.tesseract_cmd)

# Auflösung, bei der Thermobelege am zuverlässigsten erkannt werden (Tuning-Ergebnis).
_ZIELBREITE = 1000
# Preiszeile als Qualitätsmaß: Betrag (+ optional MwSt-Schlüssel) am Zeilenende.
_PREIS = re.compile(r"\d{1,3}(?:[.,]\d{3})*[.,]\d{2}\s*[€e]?\s*[A-Z1-9]?\s*$")


@dataclass
class OcrErgebnis:
    rohtext: str
    konfidenz: Optional[float]
    variante: str            # gewählte Verbesserungs-Variante (Diagnose)
    preiszeilen: int         # erkannte Preiszeilen in der Gewinner-Variante
    segmentiert: bool        # wurde ein Beleg aus dem Hintergrund freigestellt?


def _tess_config(sprache: str) -> str:
    tessdata = str(settings.tessdata_dir).replace("\\", "/")
    return f"--tessdata-dir {tessdata} --psm 6"


def _ocr(img: np.ndarray, sprache: str) -> tuple[str, float, int]:
    """Ein Tesseract-Lauf: liefert (Text, mittlere Konfidenz, Preiszeilen).

    Text wird aus `image_to_data` rekonstruiert – so genügt EIN Tesseract-Aufruf
    pro Variante (statt image_to_data + image_to_string)."""
    data = pytesseract.image_to_data(
        img, lang=sprache, config=_tess_config(sprache), output_type=pytesseract.Output.DICT
    )
    confs = [float(c) for c in data["conf"] if c not in ("", "-1") and float(c) >= 0]
    konfidenz = sum(confs) / len(confs) if confs else 0.0

    # Wörter zu Zeilen gruppieren (block/par/line), in Lesereihenfolge zusammensetzen.
    zeilen: dict[tuple, list[tuple[int, str]]] = {}
    for i, wort in enumerate(data["text"]):
        if not wort.strip():
            continue
        schluessel = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        zeilen.setdefault(schluessel, []).append((data["word_num"][i], wort))
    text = "\n".join(
        " ".join(w for _, w in sorted(woerter))
        for _, woerter in sorted(zeilen.items())
    )
    preiszeilen = sum(1 for ln in text.splitlines() if _PREIS.search(ln.strip()))
    return text, konfidenz, preiszeilen


# ── Geometrie: Beleg segmentieren & entzerren ─────────────────────────────────

def _order_pts(pts: np.ndarray) -> np.ndarray:
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1)
    rect[0] = pts[np.argmin(s)]   # oben-links
    rect[2] = pts[np.argmax(s)]   # unten-rechts
    rect[1] = pts[np.argmin(d)]   # oben-rechts
    rect[3] = pts[np.argmax(d)]   # unten-links
    return rect


def _segmentiere(bgr: np.ndarray) -> Optional[np.ndarray]:
    """Größter heller Blob (Beleg) → 4 Eckpunkte, oder None wenn keiner taugt."""
    h, w = bgr.shape[:2]
    skala = 1200.0 / max(h, w)
    klein = cv2.resize(bgr, (int(w * skala), int(h * skala)))
    grau = cv2.GaussianBlur(cv2.cvtColor(klein, cv2.COLOR_BGR2GRAY), (7, 7), 0)
    th = cv2.threshold(grau, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((25, 25), np.uint8))
    th = cv2.morphologyEx(th, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    anteil = cv2.contourArea(c) / (klein.shape[0] * klein.shape[1])
    # Nur eingreifen, wenn der Beleg klar abgegrenzt ist (nicht winzig, nicht fast Vollbild).
    if anteil < 0.05 or anteil > 0.92:
        return None
    return (cv2.boxPoints(cv2.minAreaRect(c)) / skala).astype("float32")


def _entzerre(bgr: np.ndarray, box: np.ndarray) -> np.ndarray:
    rect = _order_pts(box)
    tl, tr, br, bl = rect
    bw = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    bh = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if bw < 10 or bh < 10:
        return bgr
    dst = np.array([[0, 0], [bw - 1, 0], [bw - 1, bh - 1], [0, bh - 1]], dtype="float32")
    out = cv2.warpPerspective(bgr, cv2.getPerspectiveTransform(rect, dst), (bw, bh))
    # Kassenzettel sind hochkant – quer entzerrte um 90° aufrichten.
    return cv2.rotate(out, cv2.ROTATE_90_CLOCKWISE) if bh < bw else out


def _deskew(grau: np.ndarray) -> np.ndarray:
    """Feinen Schräglauf (±15°) per minAreaRect über alle Vordergrundpixel ausgleichen."""
    inv = cv2.bitwise_not(grau)
    th = cv2.threshold(inv, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(th > 0))
    if coords.shape[0] < 100:
        return grau
    winkel = cv2.minAreaRect(coords)[-1]
    winkel = -(90 + winkel) if winkel < -45 else -winkel
    if abs(winkel) < 0.2 or abs(winkel) > 15:
        return grau
    h, w = grau.shape
    M = cv2.getRotationMatrix2D((w // 2, h // 2), winkel, 1.0)
    return cv2.warpAffine(grau, M, (w, h), flags=cv2.INTER_CUBIC, borderValue=255)


def _skaliere(grau: np.ndarray, breite: int = _ZIELBREITE) -> np.ndarray:
    h, w = grau.shape[:2]
    if w == breite:
        return grau
    interp = cv2.INTER_AREA if w > breite else cv2.INTER_CUBIC
    return cv2.resize(grau, (breite, int(h * breite / w)), interpolation=interp)


def _adaptiv(grau: np.ndarray) -> np.ndarray:
    return cv2.adaptiveThreshold(
        grau, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )


def _clahe(grau: np.ndarray) -> np.ndarray:
    """CLAHE: lokale Kontrastverstärkung, hilft bei ungleichmäßiger Beleuchtung."""
    return cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(grau)


def _schatten_entfernen(grau: np.ndarray) -> np.ndarray:
    """Beleuchtungsgradient entfernen: Bild ÷ dilated Hintergrundmodell (normiert auf 0-255)."""
    bg = cv2.dilate(grau, np.ones((21, 21), np.uint8))
    return cv2.divide(grau, bg, scale=255)


def _unscharf_maskieren(grau: np.ndarray) -> np.ndarray:
    """Unsharp masking (Schärfungsfaktor 1): hebt feine Textkanten bei leichter Unschärfe hervor."""
    verschwommen = cv2.GaussianBlur(grau, (0, 0), 3)
    return cv2.addWeighted(grau, 2.0, verschwommen, -1.0, 0)


def _basis_varianten(grau: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Zwei Basis-Varianten – werden für Warp-Pfad (Perspektivkorrektur) verwendet."""
    g = _skaliere(_deskew(grau))
    return [("gray", g), ("adaptiv", _adaptiv(g))]


def _alle_varianten(grau: np.ndarray) -> list[tuple[str, np.ndarray]]:
    """Fünf Varianten für das Ganzbild: Basis + CLAHE, Schatten-Entfernung, Schärfung."""
    g = _skaliere(_deskew(grau))
    clahe = _clahe(g)
    schatten = _schatten_entfernen(g)
    scharf = _unscharf_maskieren(g)
    return [
        ("gray", g),
        ("adaptiv", _adaptiv(g)),
        ("clahe_adaptiv", _adaptiv(clahe)),
        ("schatten_adaptiv", _adaptiv(schatten)),
        ("scharf_adaptiv", _adaptiv(scharf)),
    ]


def verbessere_und_lies(
    bildpfad: Path, sprache: str = "deu", speicher_pfad: Optional[Path] = None
) -> OcrErgebnis:
    """Bestes OCR-Ergebnis über mehrere Bildverbesserungs-Varianten ermitteln.

    Wählt die Variante mit den meisten Preiszeilen, bei Gleichstand höherer
    Konfidenz. Fällt ohne OpenCV / bei nicht ladbaren Bildern auf Direkt-OCR
    der unveränderten Datei zurück.

    speicher_pfad: wenn angegeben, wird die gewinnende Bild-Variante dort gespeichert
    (nützlich, um das entzerrte Bild zur Kontrolle anzuzeigen)."""
    if cv2 is None:
        return _direkt_ocr(bildpfad, sprache, grund="opencv-fehlt")
    bgr = cv2.imread(str(bildpfad))
    if bgr is None:
        return _direkt_ocr(bildpfad, sprache, grund="bild-nicht-ladbar")

    # Kandidaten: (preiszeilen, konf, variante, text, bild)
    kandidaten: list[tuple[int, float, str, str, np.ndarray]] = []

    def bewerte(name: str, img: np.ndarray) -> None:
        text, konf, npx = _ocr(img, sprache)
        kandidaten.append((npx, konf, name, text, img))

    # 1. Ganzbild – alle 5 Varianten inkl. CLAHE / Schatten / Schärfung
    grau = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    for name, img in _alle_varianten(grau):
        bewerte(f"ganz_{name}", img)

    # 2. Freigestellter Beleg (Handyfotos mit Hintergrund/Perspektive) – beide Orientierungen
    #    Nur Basis-Varianten: Beleuchtung ist nach Warp meist gleichmäßig genug.
    box = _segmentiere(bgr)
    if box is not None:
        graub = cv2.cvtColor(_entzerre(bgr, box), cv2.COLOR_BGR2GRAY)
        for name, img in _basis_varianten(graub):
            bewerte(f"warp_{name}@0", img)
            bewerte(f"warp_{name}@180", cv2.rotate(img, cv2.ROTATE_180))

    kandidaten.sort(key=lambda k: (k[0], k[1]), reverse=True)
    npx, konf, variante, text, bestes_bild = kandidaten[0]

    if speicher_pfad is not None:
        save_img = cv2.cvtColor(bestes_bild, cv2.COLOR_GRAY2BGR) if bestes_bild.ndim == 2 else bestes_bild
        cv2.imwrite(str(speicher_pfad), save_img)

    return OcrErgebnis(
        rohtext=text,
        konfidenz=round(konf, 1) if konf else None,
        variante=variante,
        preiszeilen=npx,
        segmentiert=box is not None,
    )


def _direkt_ocr(bildpfad: Path, sprache: str, grund: str) -> OcrErgebnis:
    """Fallback ohne Bildverbesserung (unveränderte Datei direkt an Tesseract)."""
    text = pytesseract.image_to_string(str(bildpfad), lang=sprache, config=_tess_config(sprache))
    data = pytesseract.image_to_data(
        str(bildpfad), lang=sprache, config=_tess_config(sprache), output_type=pytesseract.Output.DICT
    )
    confs = [float(c) for c in data["conf"] if c not in ("", "-1") and float(c) >= 0]
    konf = sum(confs) / len(confs) if confs else None
    npx = sum(1 for ln in text.splitlines() if _PREIS.search(ln.strip()))
    return OcrErgebnis(
        rohtext=text, konfidenz=round(konf, 1) if konf else None,
        variante=f"direkt({grund})", preiszeilen=npx, segmentiert=False,
    )
