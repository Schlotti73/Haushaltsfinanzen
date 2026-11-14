"""
Sparkasse-Kontoauszug-Parser.

Format pro Buchung:
  Zeile 1: DD.MM.YYYYVorgangtyp Betrag   (Datum direkt am Vorgangstext, kein Leerzeichen)
  Zeile 2: Empfänger (+ Verwendungszweck-Teil)
  Zeile 3+: weitere Verwendungszweck-Zeilen
"""

from __future__ import annotations

import io
import re
from typing import Optional

import pdfplumber

from app.services.import_hash import make_hash
from app.services.pdf_import.base import BankParser, ParseResult, ParsedBuchung

# DD.MM.YYYYVorgangstext Betrag
# pdfplumber fügt an einzelnen Ziffernpaaren manchmal ein Kerning-Leerzeichen ein
# (z.B. "1 8.01.2024" statt "18.01.2024") - daher zwischen den Ziffern optional \s?
BUCHUNG_RE = re.compile(
    r"^(\d\s?\d\s?\.\d\s?\d\s?\.\d\s?\d\s?\d\s?\d)(.+?)\s+([+-]?[\d.]+,\d{2})\s*$"
)
DATUM_ZEILE_RE = re.compile(r"^\d{2}\.\d{2}\.\d{4}")
IBAN_RE = re.compile(r"DE\d{20}")

_FOOTER_RE = re.compile(
    r"^(Sparkasse|Kontostand|Privatgirokonto|HR\s*Nr|Anstalt|Nordhoff|"
    r"Vorstand|Telefon|Fax|www\.|USt|info@|Rechnungs|Anzahl|Abrechnung\s+\d|"
    r"Hinweise|Sehr geehrte|bitte\s+pr|Dieser\s+Konto|Unsere\s+f|Mit\s+freundlich|"
    r"-{5,}|Entgelte\s+vom|Kontoauszug\s+\d|Seite\s+\d|BLZ:|BIC:)",
    re.IGNORECASE,
)

_VORGANG_RE = re.compile(
    r"^(Lastschrift|Gutschrift.{0,2}berweisung|Gutschrift|Kartenzahlung|"
    r"Bargeldauszahlung\s*GA|Bargeldauszahlung|Entgeltabrechnung.*|"
    r"Dauerauftrag|Terminüberw\.|SEPA.{0,30})\s*",
    re.IGNORECASE,
)


def _parse_betrag(s: str) -> Optional[float]:
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class SparkasseParser(BankParser):
    name = "Sparkasse"

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        result = ParseResult(bank=self.name, konto_hinweis=None)

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            gesamttext = ""
            for page in pdf.pages:
                gesamttext += (page.extract_text() or "") + "\n"

        # IBAN (ohne Leerzeichen)
        m = IBAN_RE.search(gesamttext.replace(" ", ""))
        if m:
            result.konto_hinweis = m.group(0)

        zeilen = gesamttext.splitlines()

        i = 0
        while i < len(zeilen):
            zeile = zeilen[i].strip()
            bm = BUCHUNG_RE.match(zeile)
            if bm:
                datum_str = bm.group(1).replace(" ", "")   # DD.MM.YYYY
                vorgang_raw = bm.group(2).strip()
                betrag_raw = bm.group(3)

                # ISO-Datum
                t, mo, j = datum_str[:2], datum_str[3:5], datum_str[6:]
                datum_iso = f"{j}-{mo}-{t}"

                betrag = _parse_betrag(betrag_raw)
                if betrag is None:
                    i += 1
                    continue

                # Vorgangstyp aus empf_raw strippen → verbleibender Text als Empfänger-Hinweis
                rest = _VORGANG_RE.sub("", vorgang_raw).strip()

                # Fortsetzungszeilen lesen
                empfaenger: Optional[str] = rest or None
                verwendung_teile: list[str] = []

                j_idx = i + 1
                while j_idx < len(zeilen):
                    zl = zeilen[j_idx].strip()
                    if not zl:
                        j_idx += 1
                        continue
                    if BUCHUNG_RE.match(zl) or _FOOTER_RE.match(zl):
                        break
                    if empfaenger is None:
                        empfaenger = zl
                    else:
                        verwendung_teile.append(zl)
                    j_idx += 1

                verwendung = " ".join(verwendung_teile) or None

                pb = ParsedBuchung(
                    datum=datum_iso,
                    betrag=betrag,
                    empfaenger=empfaenger,
                    verwendungszweck=verwendung,
                )
                pb.import_hash = make_hash("sparkasse", datum_iso, betrag, empfaenger)
                result.buchungen.append(pb)

            i += 1

        return result
