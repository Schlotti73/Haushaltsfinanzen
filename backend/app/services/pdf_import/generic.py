"""
Generischer Best-Effort-Parser (Phase 9.2).

Für noch nicht gemappte Muster (ohne bankspezifischen Code-Parser). Sucht je
Zeile nach einem Datum und einem Betrag am Zeilenende und nimmt den Text
dazwischen als Empfänger/Verwendungszweck. Liefert bewusst grobe Ergebnisse,
die am Beispiel-Screenshot geprüft und später durch einen echten Parser
ersetzt werden.
"""

from __future__ import annotations

import io
import re
from typing import Optional

import pdfplumber

from app.services.import_hash import make_hash
from app.services.pdf_import.base import BankParser, ParseResult, ParsedBuchung

# Datum am Zeilenanfang: DD.MM.YYYY oder DD.MM.YY (auch ohne Leerzeichen danach)
DATUM_RE = re.compile(r"^(\d{2})\.(\d{2})\.(\d{2,4})")
# Betrag am Zeilenende: 1.234,56 / -12,00 / +3,50 (optional EUR/H/S dahinter)
BETRAG_END_RE = re.compile(r"([+-]?\d{1,3}(?:\.\d{3})*,\d{2})\s*(?:EUR|€|[HS])?\s*$")
IBAN_RE = re.compile(r"DE\d{20}")


def _parse_betrag(s: str) -> Optional[float]:
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _datum_iso(tag: str, monat: str, jahr: str) -> str:
    if len(jahr) == 2:
        jahr = "20" + jahr
    return f"{jahr}-{monat}-{tag}"


class GenericParser(BankParser):
    name = "Generisch"

    def __init__(self, bank_name: str = "Generisch", bank_key: str = "generisch") -> None:
        self.name = bank_name
        self._bank_key = bank_key

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        result = ParseResult(bank=self.name, konto_hinweis=None)

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            zeilen: list[str] = []
            for page in pdf.pages:
                zeilen.extend((page.extract_text() or "").splitlines())

        gesamttext = "\n".join(zeilen)
        m = IBAN_RE.search(gesamttext.replace(" ", ""))
        if m:
            result.konto_hinweis = m.group(0)

        for zeile in zeilen:
            z = zeile.strip()
            dm = DATUM_RE.match(z)
            if not dm:
                continue
            bm = BETRAG_END_RE.search(z)
            if not bm:
                continue
            betrag = _parse_betrag(bm.group(1))
            if betrag is None:
                continue

            datum_iso = _datum_iso(dm.group(1), dm.group(2), dm.group(3))
            mitte = z[dm.end():bm.start()].strip(" .-")
            empf = mitte or None

            pb = ParsedBuchung(datum=datum_iso, betrag=betrag, empfaenger=empf)
            pb.import_hash = make_hash(self._bank_key, datum_iso, betrag, empf)
            result.buchungen.append(pb)

        if not result.buchungen:
            result.fehler.append(
                "Generischer Parser hat keine Buchungen erkannt – ggf. eigenen Parser ergänzen."
            )
        return result
