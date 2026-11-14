"""
Basis-Architektur für PDF-Kontoauszug-Parser (Phase 7.2).
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


@dataclass
class ParseResult:
    bank: str
    konto_hinweis: Optional[str]          # IBAN/Kontonummer aus PDF-Header
    buchungen: list[ParsedBuchung] = field(default_factory=list)
    fehler: list[str] = field(default_factory=list)


class BankParser:
    """Basisklasse für bankspezifische Parser."""

    name: str = "unbekannt"

    def parse(self, pdf_bytes: bytes) -> ParseResult:
        raise NotImplementedError
