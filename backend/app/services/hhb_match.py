"""
Abgleich-Match-Service (Phase 8.5): findet offene Haushaltsbuch-Einträge,
die zu einer Bank-Buchung (Import oder manuell) passen könnten.

Matching-Strategie:
  1. Betrag muss (auf 1 Cent) übereinstimmen
  2. Datum innerhalb der Toleranz (Tage)
  3. Geschäft <-> Bank-Buchung, in dieser Reihenfolge:
       a) Empfänger-Link-ID-Treffer (sicherster Weg)
       b) Name-Fuzzy/Substring gegen den Empfänger-Text
       c) Geschäftsname als eigenständiges Wort im Verwendungszweck
          -> deckt Zahlungsdienstleister (PayPal, Klarna …) ab, bei denen der
             Kontoauszug immer denselben Empfänger trägt und der echte Laden
             nur im Verwendungszweck steht.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.models import HaushaltsbuchEintrag

FUZZY_SCHWELLE = 0.6


def _tag_offset(datum_iso: str, tage: int) -> str:
    d = date.fromisoformat(datum_iso)
    return (d + timedelta(days=tage)).isoformat()


def _aehnlichkeit(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def _name_matcht(geschaeft_name: Optional[str], empfaenger_text: Optional[str]) -> bool:
    if not geschaeft_name or not empfaenger_text:
        return False
    g, e = geschaeft_name.lower(), empfaenger_text.lower()
    if g in e or e in g:
        return True
    return _aehnlichkeit(g, e) >= FUZZY_SCHWELLE


def _name_in_verwendungszweck(geschaeft_name: Optional[str], verwendungszweck: Optional[str]) -> bool:
    """True, wenn der Geschäftsname als eigenständiges Wort im Verwendungszweck steht.

    Bewusst kein Fuzzy-Match: der Verwendungszweck ist Freitext, in dem eine
    Ähnlichkeitsquote über den ganzen Text kaum aussagt. Der Wort-Grenzen-Treffer
    (\\b…\\b) verhindert Zufallstreffer kurzer Namen (z. B. „dm" in „Grundmiete").
    """
    name = (geschaeft_name or "").strip()
    if len(name) < 3 or not verwendungszweck:
        return False
    return re.search(rf"\b{re.escape(name)}\b", verwendungszweck, re.IGNORECASE) is not None


def finde_kandidaten(
    db: Session,
    datum: str,
    betrag: float,
    empfaenger_text: Optional[str] = None,
    empfaenger_id: Optional[int] = None,
    verwendungszweck: Optional[str] = None,
    geschaeft_id: Optional[int] = None,
    tage_toleranz: int = 3,
    limit: int = 5,
) -> list[HaushaltsbuchEintrag]:
    """Findet offene Haushaltsbuch-Einträge, die zu Datum/Betrag/Empfänger passen.

    `geschaeft_id` stammt aus dem Import-Regel-Treffer (Stufe Händler) und ist
    der sicherste Weg überhaupt: dort wurde der Laden bereits eindeutig
    identifiziert, hier muss nichts mehr geraten werden.
    """
    betrag_abs = abs(betrag)
    eintraege = (
        db.query(HaushaltsbuchEintrag)
        .options(selectinload(HaushaltsbuchEintrag.geschaeft))
        .filter(
            HaushaltsbuchEintrag.abgleich_status == "offen",
            HaushaltsbuchEintrag.betrag_gesamt.between(betrag_abs - 0.01, betrag_abs + 0.01),
            HaushaltsbuchEintrag.datum.between(
                _tag_offset(datum, -tage_toleranz), _tag_offset(datum, +tage_toleranz)
            ),
        )
        .all()
    )

    treffer = []
    for e in eintraege:
        geschaeft_name = e.geschaeft.name if e.geschaeft else None
        if geschaeft_id and e.geschaeft_id == geschaeft_id:
            treffer.append(e)
        elif empfaenger_id and e.geschaeft and e.geschaeft.empfaenger_id == empfaenger_id:
            treffer.append(e)
        elif _name_matcht(geschaeft_name, empfaenger_text):
            treffer.append(e)
        elif _name_in_verwendungszweck(geschaeft_name, verwendungszweck):
            treffer.append(e)
    return treffer[:limit]
