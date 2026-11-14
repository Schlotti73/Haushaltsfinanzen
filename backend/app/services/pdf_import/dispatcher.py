"""Wählt anhand der Muster-Registry (DB) den richtigen Parser."""

from __future__ import annotations

import io
import json
from typing import Optional

import pdfplumber
from sqlalchemy.orm import Session

from app.models import KontoauszugMuster
from app.services.pdf_import.base import BankParser, ParseResult
from app.services.pdf_import.generic import GenericParser
from app.services.pdf_import.postbank import PostbankParser
from app.services.pdf_import.ing import INGParser
from app.services.pdf_import.sparkasse import SparkasseParser

# Registrierung bankspezifischer Code-Parser (parser_key → Parser).
PARSER_REGISTRY: dict[str, BankParser] = {
    "postbank": PostbankParser(),
    "ing": INGParser(),
    "sparkasse": SparkasseParser(),
}


def _titelfall(s: str | None) -> str | None:
    """Ersten Buchstaben jedes Worts groß, Rest klein (auch nach - und +)."""
    if not s:
        return s
    return s.title()


def _muster_fuer_text(db: Session, text: str) -> Optional[KontoauszugMuster]:
    """Erstes aktives Muster, dessen Erkennungs-Keyword im Text vorkommt."""
    t = text.lower()
    muster = (
        db.query(KontoauszugMuster)
        .filter(KontoauszugMuster.aktiv.is_(True))
        .order_by(KontoauszugMuster.id)
        .all()
    )
    for m in muster:
        try:
            keywords = json.loads(m.erkennung_keywords or "[]")
        except (ValueError, TypeError):
            keywords = []
        if any(str(kw).lower() in t for kw in keywords):
            return m
    return None


def _parser_fuer_muster(muster: Optional[KontoauszugMuster]) -> BankParser:
    """Code-Parser laut parser_key, sonst generischer Best-Effort-Parser."""
    if muster and muster.parser_key and muster.parser_key in PARSER_REGISTRY:
        return PARSER_REGISTRY[muster.parser_key]
    if muster:
        return GenericParser(bank_name=muster.name, bank_key=muster.bank_key)
    return GenericParser()


def parse_pdf(pdf_bytes: bytes, db: Session) -> ParseResult:
    """Erkennt das Muster anhand der DB und parst den Kontoauszug."""
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        first_text = (pdf.pages[0].extract_text() or "") if pdf.pages else ""

    muster = _muster_fuer_text(db, first_text)
    parser = _parser_fuer_muster(muster)
    result = parser.parse(pdf_bytes)

    for b in result.buchungen:
        b.empfaenger = _titelfall(b.empfaenger)

    return result
