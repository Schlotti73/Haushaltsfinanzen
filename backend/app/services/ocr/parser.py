"""Heuristischer Zeilen-Parser: Kassenzettel-Rohtext -> Artikel-Kandidaten.

Kein Anspruch auf Vollständigkeit/Korrektheit - die Kandidaten werden dem
Nutzer als Vorschau zur Korrektur angezeigt, nicht direkt gespeichert.

Der Parser ist datengetrieben (Phase 10): über ein optionales `MusterProfil`
lässt sich das Verhalten pro Geschäft (Aldi, Edeka, Rossmann …) anpassen, ohne
neuen Code zu schreiben - Artikelbereich eingrenzen, zusätzliche Skip-Begriffe,
eigenes Preis-Muster. Ohne Profil verhält er sich wie der frühere generische
Parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Pattern

# Preis mit optionalem MwSt-Schlüssel (Buchstabe A-Z oder Ziffer 1-9) am Ende
_PREIS = re.compile(r"(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*[€e]?\s*([A-Z1-9])?\s*$")
_MENGE_PRAEFIX = re.compile(r"^(\d+(?:[.,]\d+)?)\s*[xX]\s*(.+)$")
# MwSt-Tabellenzeile: optionaler Schlüssel, dann Prozentsatz (z.B. "A 7,00%" oder "7,00%")
_MWST_ZEILE = re.compile(r"^(?:([A-Z1-9])\s+)?(\d{1,2}[.,]\d{2})\s*%")

_PREIS_BEZEICHNUNG = re.compile(r"^\d+[.,]\d{1,2}$")

_SKIP_KEYWORDS = (
    "summe", "gesamt", "total", "zu zahlen", "bar", "ec-cash", "ec cash",
    "kartenzahlung", "rückgeld", "ruckgeld", "mwst", "ust", "steuer",
    "geg.", "gegeben", "zwischensumme", "anzahl artikel", "posten",
    "kassenbon", "bon-nr", "bon nr", "datum", "uhrzeit", "kunden", "filiale",
    "terminal", "beleg-nr", "beleg nr", "tse", "danke", "wiedersehen",
    "eur ", "girocard", "genehmigungs",
)


@dataclass
class MusterProfil:
    """Datengetriebene Parser-Konfiguration pro Geschäft (Phase 10).

    Alle Felder sind optional; ein leeres Profil entspricht dem generischen
    Verhalten. Wird üblicherweise aus einem `KassenzettelMuster`-Datensatz
    aufgebaut (siehe `services.ocr.dispatcher`).
    """

    # Artikelbereich eingrenzen: ab erster Zeile mit `start_marker`, bis zur
    # ersten Zeile mit `stop_marker` (jeweils case-insensitive, Teilstring).
    start_marker: Optional[str] = None
    stop_marker: Optional[str] = None
    # Zusätzliche, geschäftsspezifische Skip-Begriffe (z.B. "pfand", "coupon").
    skip_keywords: tuple[str, ...] = ()
    # Eigenes Preis-Muster, falls der Standard nicht passt. Muss zwei Gruppen
    # liefern: (1) Betrag, (2) optionaler MwSt-Schlüssel.
    preis_regex: Optional[Pattern[str]] = None

    def _alle_skip(self) -> tuple[str, ...]:
        return _SKIP_KEYWORDS + tuple(k.lower() for k in self.skip_keywords)


def _zu_float(text: str) -> float:
    return float(text.replace(".", "").replace(",", "."))


def _ist_skip_zeile(zeile: str, skip_keywords: tuple[str, ...]) -> bool:
    if _MWST_ZEILE.match(zeile.strip()):
        return True  # MwSt-Aufschlüsselungstabelle am Bonende
    klein = zeile.lower()
    return any(kw in klein for kw in skip_keywords)


def _parse_mwst_tabelle(zeilen: list[str]) -> dict[str, float]:
    """Liest MwSt-Tabelle und liefert {schlüssel: satz} (z.B. {'A': 7.0, 'B': 19.0}).
    Ohne expliziten Schlüssel im Bon wird '1', '2', ... als Schlüssel vergeben."""
    ergebnis: dict[str, float] = {}
    zaehler = 1
    for zeile in zeilen:
        m = _MWST_ZEILE.match(zeile.strip())
        if not m:
            continue
        schluessel = m.group(1) or str(zaehler)
        satz = _zu_float(m.group(2))
        ergebnis[schluessel] = satz
        zaehler += 1
    return ergebnis


def _artikelbereich(zeilen: list[str], profil: Optional[MusterProfil]) -> list[str]:
    """Grenzt die Zeilen anhand von start_marker/stop_marker ein (Phase 10).

    Marker werden case-insensitiv als Teilstring gesucht. Wird ein Marker nicht
    gefunden, bleibt die jeweilige Grenze offen (Anfang bzw. Ende des Bons)."""
    if not profil:
        return zeilen
    start = 0
    if profil.start_marker:
        marker = profil.start_marker.lower()
        for i, z in enumerate(zeilen):
            if marker in z.lower():
                start = i + 1  # ab der Zeile NACH dem Marker
                break
    ende = len(zeilen)
    if profil.stop_marker:
        marker = profil.stop_marker.lower()
        for i in range(start, len(zeilen)):
            if marker in zeilen[i].lower():
                ende = i
                break
    return zeilen[start:ende]


def parse_kassenzettel(rohtext: str, profil: Optional[MusterProfil] = None) -> list[dict]:
    """Liefert Kandidaten als [{bezeichnung, menge, einzelpreis, gesamtpreis,
    mwst_satz, mwst_schluessel}].

    `mwst_satz` enthält den erkannten MwSt-Prozentsatz (z.B. 7.0 oder 19.0) oder
    None; `mwst_schluessel` den rohen Schlüssel (A/B/1/2 …) von der Artikelzeile.
    Mit `profil` wird das Parsen geschäftsspezifisch angepasst.
    """
    alle_zeilen = rohtext.splitlines()
    mwst_map = _parse_mwst_tabelle(alle_zeilen)  # Tabelle steht im (ggf. abgeschnittenen) Footer

    skip_keywords = profil._alle_skip() if profil else _SKIP_KEYWORDS
    preis_regex = (profil.preis_regex if profil and profil.preis_regex else _PREIS)

    kandidaten: list[dict] = []
    for zeile in _artikelbereich(alle_zeilen, profil):
        zeile = zeile.strip()
        if not zeile or len(zeile) < 3:
            continue
        if _ist_skip_zeile(zeile, skip_keywords):
            continue

        preis_match = preis_regex.search(zeile)
        if not preis_match:
            continue
        gesamtpreis = _zu_float(preis_match.group(1))
        mwst_schluessel = preis_match.group(2) if preis_match.lastindex and preis_match.lastindex >= 2 else None
        rest = zeile[: preis_match.start()].strip()

        menge = 1.0
        einzelpreis = None
        menge_match = _MENGE_PRAEFIX.match(rest)
        if menge_match:
            menge = _zu_float(menge_match.group(1))
            rest = menge_match.group(2).strip()
            if menge:
                einzelpreis = round(gesamtpreis / menge, 2)

        bezeichnung = rest.strip(" -*").title()
        if not bezeichnung or re.fullmatch(r"\d*\s*[xX]", bezeichnung):
            continue  # Mengen-Fortsetzungszeile ohne Artikeltext (z.B. "3 X")

        # Edeka-Fortsatzzeile: Bezeichnung ist ein reiner Preisstring (z.B. "1,15")
        # und menge>1 → Vorgängerartikel aktualisieren statt neuen Eintrag anlegen
        if _PREIS_BEZEICHNUNG.match(bezeichnung) and menge > 1 and kandidaten:
            prev = kandidaten[-1]
            prev["menge"] = menge
            prev["gesamtpreis"] = gesamtpreis
            prev["einzelpreis"] = round(gesamtpreis / menge, 2)
            mwst_satz = mwst_map.get(mwst_schluessel) if mwst_schluessel else None
            if mwst_satz is not None:
                prev["mwst_satz"] = mwst_satz
            if mwst_schluessel is not None:
                prev["mwst_schluessel"] = mwst_schluessel
            continue

        mwst_satz = mwst_map.get(mwst_schluessel) if mwst_schluessel else None

        kandidaten.append({
            "bezeichnung": bezeichnung,
            "menge": menge,
            "einzelpreis": einzelpreis,
            "gesamtpreis": gesamtpreis,
            "mwst_satz": mwst_satz,
            "mwst_schluessel": mwst_schluessel,
        })
    return kandidaten
