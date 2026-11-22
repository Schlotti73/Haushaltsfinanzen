"""
Basis-Architektur für Kontoauszug-Parser (Phase 7.2).

Ursprünglich nur für PDFs gedacht, inzwischen auch die Schnittstelle des
generischen CSV-Parsers (services/csv_import/parser.py). Die Felder, die ein
PDF nicht hergibt, sind deshalb alle freiwillig: ein PDF-Parser lässt sie
einfach leer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ParsedBuchung:
    datum: str               # 'YYYY-MM-DD'
    betrag: float
    empfaenger: Optional[str] = None
    verwendungszweck: Optional[str] = None
    iban_empfaenger: Optional[str] = None
    import_hash: Optional[str] = None   # wird nach dem Parsen gesetzt
    # Nur strukturierte Formate (CSV, später CAMT) liefern das Folgende. Die
    # Wertstellung weicht beim Buchungsdatum selten ab und wird nur mitgeführt,
    # nicht gespeichert; die drei Referenzfelder landen an der Buchung.
    valuta: Optional[str] = None
    umsatzart: Optional[str] = None
    mandatsreferenz: Optional[str] = None
    referenz: Optional[str] = None


@dataclass
class ParseResult:
    bank: str
    konto_hinweis: Optional[str]          # IBAN/Kontonummer aus dem Dateikopf
    buchungen: list[ParsedBuchung] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)
    # Abstimmung der Datei gegen ihre eigenen Kontostände. Leer bei Formaten
    # ohne Saldo-Angabe (alle PDF-Auszüge) – siehe CsvProfilParser.
    saldo_pruefung: dict = field(default_factory=dict)


class BankParser:
    """Basisklasse für bankspezifische Parser."""

    name: str = "unbekannt"

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        raise NotImplementedError
