"""
Empfänger-Match-Service (Phase 7.4).

Matching-Strategie:
  1. IBAN-Exakt-Match (wenn Buchung eine IBAN enthält)
  2. Name-Fuzzy-Match (SequenceMatcher, Schwelle 0.85)
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Empfaenger

IBAN_RE = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}(?:[A-Z0-9]?){0,16}\b")
FUZZY_SCHWELLE = 0.85


def _iban_aus_text(text: str) -> Optional[str]:
    m = IBAN_RE.search(text.upper().replace(" ", ""))
    return m.group(0) if m else None


def _aehnlichkeit(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def match(db: Session, empfaenger_text: Optional[str], iban: Optional[str] = None) -> Optional[Empfaenger]:
    """Findet den passenden Empfänger-Eintrag oder None."""
    if not empfaenger_text and not iban:
        return None

    alle = db.query(Empfaenger).all()
    if not alle:
        return None

    # 1. IBAN-Exakt
    kandidat_iban = iban or (empfaenger_text and _iban_aus_text(empfaenger_text))
    if kandidat_iban:
        for e in alle:
            if e.iban and e.iban.replace(" ", "").upper() == kandidat_iban.replace(" ", "").upper():
                return e

    # 2. Name-Fuzzy
    if empfaenger_text:
        bestes: tuple[float, Optional[Empfaenger]] = (0.0, None)
        for e in alle:
            score = _aehnlichkeit(empfaenger_text, e.name)
            if score > bestes[0]:
                bestes = (score, e)
        if bestes[0] >= FUZZY_SCHWELLE:
            return bestes[1]

    return None


def vorschlaege(db: Session, suche: str, limit: int = 10) -> list[Empfaenger]:
    """Gibt Empfänger sortiert nach Ähnlichkeit zurück."""
    alle = db.query(Empfaenger).all()
    scored = sorted(
        alle,
        key=lambda e: _aehnlichkeit(suche, e.name),
        reverse=True,
    )
    return scored[:limit]
