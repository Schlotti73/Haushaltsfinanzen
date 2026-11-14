"""
ING-Kontoauszug-Parser (Phase 7.2).

ING-PDFs enthalten typischerweise Tabellen mit Spalten:
  Buchung | Valuta | Auftraggeber/Begünstigter | Buchungstext | Betrag
"""

from __future__ import annotations

import io
import re
from typing import Optional

import pdfplumber

from app.services.import_hash import make_hash
from app.services.pdf_import.base import BankParser, ParseResult, ParsedBuchung

DATUM_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
BETRAG_CLEAN_RE = re.compile(r"[^\d,\-+]")
IBAN_RE = re.compile(r"DE\d{20}")


def _datum_iso(tag: str, monat: str, jahr: str) -> str:
    return f"{jahr}-{monat}-{tag}"


def _parse_betrag(s: str) -> Optional[float]:
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class INGParser(BankParser):
    name = "ING"

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        result = ParseResult(bank=self.name, konto_hinweis=None)

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            alle_zeilen: list[str] = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                alle_zeilen.extend(text.splitlines())

        gesamttext = "\n".join(alle_zeilen)

        # IBAN (Leerzeichen entfernen für Suche, z.B. "DE10 5001 0517 ...")
        m = IBAN_RE.search(gesamttext.replace(" ", ""))
        if m:
            result.konto_hinweis = m.group(0)

        # Zeilen mit Datum am Anfang als Buchungszeilen behandeln
        i = 0
        while i < len(alle_zeilen):
            zeile = alle_zeilen[i].strip()
            dm = DATUM_RE.match(zeile)
            if dm:
                datum_iso = _datum_iso(dm.group(1), dm.group(2), dm.group(3))
                rest = zeile[dm.end():].strip()

                # Betrag am Ende (kann negativ mit Minuszeichen sein)
                teile = rest.rsplit(None, 1)
                if len(teile) == 2:
                    betrag = _parse_betrag(teile[-1])
                    if betrag is not None:
                        empfaenger = teile[0].strip() or None
                        # Verwendungszweck: Folgezeile (startet oft mit gleichem Datum)
                        verwendung = None
                        if i + 1 < len(alle_zeilen):
                            naechste = alle_zeilen[i + 1].strip()
                            if naechste:
                                dm2 = DATUM_RE.match(naechste)
                                if dm2:
                                    # Folgezeile mit Datum: Verwendungszweck wenn kein Betrag am Ende
                                    rest2 = naechste[dm2.end():].strip()
                                    t2 = rest2.rsplit(None, 1)
                                    hat_betrag = len(t2) == 2 and _parse_betrag(t2[-1]) is not None
                                    if rest2 and not hat_betrag:
                                        verwendung = rest2
                                elif not re.match(r"^(Mandat:|Referenz:|T_\d|ING)", naechste):
                                    verwendung = naechste
                        pb = ParsedBuchung(
                            datum=datum_iso,
                            betrag=betrag,
                            empfaenger=empfaenger,
                            verwendungszweck=verwendung,
                        )
                        pb.import_hash = make_hash("ing", datum_iso, betrag, empfaenger)
                        result.buchungen.append(pb)
            i += 1

        return result
