"""
Postbank-Kontoauszug-Parser (Phase 7.2 - v3).

Postbank PDF-Format pro Buchung:
  Zeile 1: DD.MM. DD.MM. VorgangEmpfänger Betrag
  Zeile 2: YYYY   YYYY   EmpfängerFortsetzung
  Zeile 3+: IBAN <DE...>, BIC ..., Verwendungszweck/Kundenreferenz, Buchungstext (mehrzeilig)
"""

from __future__ import annotations

import io
import re
from typing import Optional

import pdfplumber

from app.services.import_hash import make_hash
from app.services.pdf_import.base import BankParser, ParseResult, ParsedBuchung

# Buchungszeile: DD.MM. DD.MM. Vorgang+Empfänger Betrag
BUCHUNG_RE = re.compile(
    r"^(\d{2})\.(\d{2})\.\s+\d{2}\.\d{2}\.\s+(.+?)\s+([+-]?[\d.]+,\d{2})\s*$"
)
# Jahres-Folgezeile nach der Buchungszeile
JAHRES_RE = re.compile(r"^(\d{4})\s+\d{4}\s*(.*)?$")
# Jahr aus Header ("bis DD.MM.YYYY")
HEADER_DATUM_RE = re.compile(r"bis\s+\d{2}\.\d{2}\.(\d{4})")
# Konto-IBAN aus Header (ohne Leerzeichen)
IBAN_RE = re.compile(r"DE\d{20}")
# IBAN einer Buchungszeile (mit "IBAN "-Prefix)
IBAN_ZEILE_RE = re.compile(r"^IBAN\s+(DE[\dA-Z]{2,30})", re.IGNORECASE)

# SEPA-Vorgangstypen (ohne Leerzeichen, wie im extrahierten PDF-Text)
_VORGANG_RES = [
    re.compile(r"^SEPA(Last|Dauer|Echt|Termin|Gut|[A-Z][a-z]+)[A-Za-z]+"),
    re.compile(r"^Dauerauftrag"),
    re.compile(r"^Gutschrift"),
    re.compile(r"^Lastschrift"),
]

# Zeilen, die Metadaten des Empfängers darstellen und nicht Teil des
# Verwendungszwecks sind (für Empfänger-Bereinigung genutzt).
_EMPF_META_RE = re.compile(
    r"^(Verwendungszweck/Kundenreferenz|IBAN|BIC\s|Auszug|Buchung|Valuta|"
    r"Filialnummer|EUR|Soll|Haben|Wichtige|Bitte|Som it|Die ab|Guthabensin|1\))",
    re.IGNORECASE,
)

# Abschluss-Marker innerhalb des Verwendungszweck-Blocks
# (diese Zeilen beenden die Sammlung, werden aber NICHT Teil des VZ)
_VZ_STOP_RE = re.compile(
    r"^(Auszug|Buchung\s+Valuta|Filialnummer|Verwendungszweck/Kundenreferenz)",
    re.IGNORECASE,
)

_VORGANG_ONLY_RE = re.compile(r"^SEPA.{1,30}?(von|an)$", re.IGNORECASE)
_VORGANG_PREFIX_RE = re.compile(r"^SEPA.{1,30}?(von|an)\s+", re.IGNORECASE)


def _strip_vorgang(text: str) -> str:
    """Entfernt bekannte SEPA-Transaktionstyp-Präfixe."""
    if _VORGANG_ONLY_RE.match(text):
        return ""
    m = _VORGANG_PREFIX_RE.match(text)
    if m:
        return text[m.end():].strip()
    return text


def _parse_betrag(s: str) -> Optional[float]:
    s = s.strip().replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


class PostbankParser(BankParser):
    name = "Postbank"

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        result = ParseResult(bank=self.name, konto_hinweis=None)

        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            gesamttext = ""
            for page in pdf.pages:
                gesamttext += (page.extract_text() or "") + "\n"

        # IBAN des Kontoinhabers aus Header
        m = IBAN_RE.search(gesamttext.replace(" ", ""))
        if m:
            result.konto_hinweis = m.group(0)

        # Jahr aus Header-Zeile ("Kontoauszug vom 01.05.2026 bis 29.05.2026")
        fallback_jahr = "2026"
        hm = HEADER_DATUM_RE.search(gesamttext)
        if hm:
            fallback_jahr = hm.group(1)

        zeilen = gesamttext.splitlines()
        i = 0
        while i < len(zeilen):
            zeile = zeilen[i].strip()
            bm = BUCHUNG_RE.match(zeile)
            if bm:
                tag, monat = bm.group(1), bm.group(2)
                empf_raw = bm.group(3)
                betrag_raw = bm.group(4)

                # Jahr und Empfänger-Fortsetzung aus Folgezeile
                buchung_jahr = fallback_jahr
                empf_fortsetzung = ""
                if i + 1 < len(zeilen):
                    naechste = zeilen[i + 1].strip()
                    jm = JAHRES_RE.match(naechste)
                    if jm:
                        buchung_jahr = jm.group(1)
                        empf_fortsetzung = (jm.group(2) or "").strip()
                        i += 1

                betrag = _parse_betrag(betrag_raw)
                if betrag is None:
                    i += 1
                    continue

                datum_iso = f"{buchung_jahr}-{monat}-{tag}"

                # Empfänger zusammenbauen
                empf = _strip_vorgang(empf_raw)
                if empf_fortsetzung and not _EMPF_META_RE.match(empf_fortsetzung):
                    empf = (empf + " " + empf_fortsetzung).strip()
                empf = empf or None

                # ── Detailzeilen scannen ─────────────────────────────────────
                # Sammle IBAN der Gegenseite + vollständigen Verwendungszweck.
                iban_empfaenger: Optional[str] = None
                vz_zeilen: list[str] = []

                j = i + 1
                while j < len(zeilen):
                    zl = zeilen[j].strip()
                    if not zl:
                        j += 1
                        continue

                    # Nächste Buchung beginnt → fertig
                    if BUCHUNG_RE.match(zl):
                        break

                    # Seiten-/Abschnitt-Trennzeile → fertig
                    if re.match(r"^(Auszug|Buchung\s+Valuta|Filialnummer)", zl):
                        break

                    # IBAN der Gegenseite (vor dem VZ-Marker)
                    im = IBAN_ZEILE_RE.match(zl)
                    if im:
                        iban_empfaenger = im.group(1).replace(" ", "")
                        j += 1
                        continue

                    # BIC-Zeile überspringen
                    if zl.upper().startswith("BIC "):
                        j += 1
                        continue

                    # Verwendungszweck-Block: alles bis zur nächsten Buchung sammeln
                    if zl == "Verwendungszweck/Kundenreferenz":
                        k = j + 1
                        while k < len(zeilen):
                            nz = zeilen[k].strip()
                            if not nz:
                                k += 1
                                continue
                            if BUCHUNG_RE.match(nz):
                                break
                            if _VZ_STOP_RE.match(nz):
                                break
                            vz_zeilen.append(nz)
                            k += 1
                        j = k
                        break

                    j += 1

                verwendung = "\n".join(vz_zeilen) if vz_zeilen else None

                pb = ParsedBuchung(
                    datum=datum_iso,
                    betrag=betrag,
                    empfaenger=empf,
                    verwendungszweck=verwendung,
                    iban_empfaenger=iban_empfaenger,
                )
                pb.import_hash = make_hash("postbank", datum_iso, betrag, empf)
                result.buchungen.append(pb)

            i += 1

        return result
