"""
Import-Regel-Service (Phase 16): macht aus dem Bankrohtext definierte Werte.

Aus
    Bankempfänger:     "Paypal Europe S.A.R.L. Et Cie S.C.A . Getranke Nord Selbststand Iger"
    Verwendungszweck:  "… Ihr Einkauf bei GETRANKE NORD …"
wird
    Empfänger  = "PayPal"        (Stufe 1, Anbieter)
    Notiz      = "Getränke Nord" (Stufe 2, Händler)
    Kategorie  = "Lebensmittel"  (Stufe 2, Händler)

Zwei Stufen, weil Zahlungsdienstleister und Laden unabhängig voneinander
auftreten. Stufe 1 durchsucht bewusst *nur* den Bankempfänger: der Dienstleister
ist der Kontoinhaber, der das Geld zieht. Stünde "Zahlung via PayPal" irgendwo im
Verwendungszweck, dürfte das den echten Empfänger nicht überschreiben.

Verglichen wird ohne Regex und ohne Fuzzy-Quote, sondern auf normalisiertem Text
(siehe `normalisiere`). Der Bankrohtext ist voller pdfplumber-Artefakte
("Getranke Nord", "Selbststand Iger", "S.A.R.L ."); die Normalisierung fängt
Groß-/Kleinschreibung, Satzzeichen und Umlaute ab, der Rest gehört als zweites
Schlüsselwort gepflegt – nachvollziehbar statt geraten.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session, selectinload

from app.models import Empfaenger, Geschaeft, ImportRegel

# Kürzere Schlüsselwörter lösen zu viele Zufallstreffer aus ("dm" in "Grundmiete"
# fängt die Wortgrenze zwar ab, "ab" als eigenes Wort aber nicht).
MIN_SCHLUESSELWORT = 3

# Umlaute werden auf den Grundbuchstaben gezogen, nicht entfaltet (ä→a, nicht
# ä→ae). Der PDF-Text der Banken verliert die Punkte schlicht – im Bestand steht
# "Getranke Nord" und "Selbststandiger". Ein gepflegtes "Getränke Nord" trifft
# damit die Bankschreibweise; mit "ae" ginge es daneben.
_UMLAUTE = {
    "ä": "a", "ö": "o", "ü": "u", "ß": "ss",
    "à": "a", "á": "a", "â": "a", "é": "e", "è": "e", "ê": "e",
    "í": "i", "ì": "i", "ó": "o", "ò": "o", "ô": "o", "ú": "u", "ù": "u",
}

_NICHT_ALNUM = re.compile(r"[^a-z0-9]+")


def normalisiere(text: Optional[str]) -> str:
    """Vereinheitlicht Bankrohtext und Muster auf eine vergleichbare Form.

    "Getränke Nord" und "GETRANKE NORD" werden beide zu
    "getranke nord" – der Vergleich ist damit unempfindlich gegen
    Schreibweise, Satzzeichen und fehlende Umlaute, ohne dass die Wortgrenzen
    verloren gehen (die schützen kurze Namen vor Zufallstreffern).
    """
    if not text:
        return ""
    t = text.lower()
    for zeichen, ersatz in _UMLAUTE.items():
        t = t.replace(zeichen, ersatz)
    return _NICHT_ALNUM.sub(" ", t).strip()


def _enthaelt_wort(heuhaufen_norm: str, nadel_norm: str) -> bool:
    """True, wenn `nadel_norm` als vollständige Wortfolge in `heuhaufen_norm` steht."""
    if not nadel_norm or not heuhaufen_norm:
        return False
    return re.search(rf"(?:^| ){re.escape(nadel_norm)}(?: |$)", heuhaufen_norm) is not None


def _schluesselwoerter(regel: ImportRegel) -> list[str]:
    try:
        werte = json.loads(regel.schluesselwoerter or "[]")
    except (ValueError, TypeError):
        return []
    if not isinstance(werte, list):
        return []
    return [str(w) for w in werte if str(w).strip()]


def _iban_normal(iban: Optional[str]) -> str:
    return (iban or "").replace(" ", "").upper()


@dataclass
class Treffer:
    """Ergebnis einer Stufe – was gesetzt werden soll und warum."""
    quelle: str                       # "regel" | "geschaeft"
    bezeichnung: str                  # Anzeigename der Regel bzw. des Geschäfts
    schluessel: str = ""              # das Schlüsselwort, das gegriffen hat
    empfaenger_id: Optional[int] = None
    empfaenger_name: Optional[str] = None
    kategorie_id: Optional[int] = None
    notiz: Optional[str] = None
    geschaeft_id: Optional[int] = None
    # Stand das Schlüsselwort im Bankempfängerfeld (und nicht nur irgendwo im
    # Verwendungszweck)? Nur dann ist der Treffer eine Aussage über den
    # Zahlungspartner – im Verwendungszweck ist er bloß eine Erwähnung.
    im_empfaengerfeld: bool = False


@dataclass
class RegelErgebnis:
    """Zusammengeführtes Ergebnis beider Stufen für eine Buchung."""
    empfaenger_id: Optional[int] = None
    empfaenger_name: Optional[str] = None
    kategorie_id: Optional[int] = None
    notiz: Optional[str] = None
    geschaeft_id: Optional[int] = None
    anbieter: Optional[Treffer] = None
    haendler: Optional[Treffer] = None

    @property
    def hat_treffer(self) -> bool:
        return self.anbieter is not None or self.haendler is not None

    def hinweis(self) -> Optional[str]:
        """Kurztext für die Import-Vorschau, z. B. "Regel: PayPal → Getränke Nord"."""
        teile = [t.bezeichnung for t in (self.anbieter, self.haendler) if t]
        return "Regel: " + " → ".join(teile) if teile else None


class RegelKatalog:
    """Lädt Regeln und Geschäfte einmal und wendet sie auf viele Buchungen an.

    Ein Import umfasst schnell hundert Zeilen; ohne diesen Cache liefe pro Zeile
    eine Abfrage über Regeln, Geschäfte und Empfänger.
    """

    def __init__(self, db: Session):
        regeln = (
            db.query(ImportRegel)
            .options(selectinload(ImportRegel.empfaenger_obj))
            .filter(ImportRegel.aktiv.is_(True))
            .all()
        )
        self._anbieter = [r for r in regeln if r.stufe == "anbieter"]
        self._haendler = [r for r in regeln if r.stufe == "haendler"]
        self._geschaefte = (
            db.query(Geschaeft)
            .options(selectinload(Geschaeft.empfaenger_obj))
            .filter(Geschaeft.aktiv.is_(True))
            .all()
        )

    # -- Stufe 1 ---------------------------------------------------------
    def _finde_anbieter(self, empfaenger_roh: Optional[str], iban: Optional[str]) -> Optional[Treffer]:
        heuhaufen = normalisiere(empfaenger_roh)
        iban_norm = _iban_normal(iban)
        bester: Optional[tuple[int, ImportRegel, str]] = None

        for regel in self._anbieter:
            # IBAN zuerst: eine feste Gläubiger-IBAN ist immun gegen jede
            # Schreibvariante und schlägt deshalb jeden Wortreffer.
            if iban_norm and regel.iban_muster and _iban_normal(regel.iban_muster) == iban_norm:
                return self._als_treffer(regel, "IBAN")
            for wort in _schluesselwoerter(regel):
                wort_norm = normalisiere(wort)
                if len(wort_norm) < MIN_SCHLUESSELWORT:
                    continue
                if _enthaelt_wort(heuhaufen, wort_norm) and (bester is None or len(wort_norm) > bester[0]):
                    bester = (len(wort_norm), regel, wort)

        return self._als_treffer(bester[1], bester[2]) if bester else None

    # -- Stufe 2 ---------------------------------------------------------
    def _finde_haendler(
        self, empfaenger_roh: Optional[str], verwendungszweck: Optional[str]
    ) -> Optional[Treffer]:
        # Der Laden steht je nach Bank mal im Empfängerfeld (Sparkasse), mal nur
        # im Verwendungszweck (ING/Postbank) – deshalb beides zusammen.
        heuhaufen = normalisiere(f"{empfaenger_roh or ''} {verwendungszweck or ''}")
        if not heuhaufen:
            return None
        # Getrennt mitgeführt, um später zu wissen, wo der Treffer herkam.
        nur_empfaenger = normalisiere(empfaenger_roh)

        bester_regel: Optional[tuple[int, ImportRegel, str]] = None
        for regel in self._haendler:
            for wort in _schluesselwoerter(regel):
                wort_norm = normalisiere(wort)
                if len(wort_norm) < MIN_SCHLUESSELWORT:
                    continue
                if _enthaelt_wort(heuhaufen, wort_norm) and (
                    bester_regel is None or len(wort_norm) > bester_regel[0]
                ):
                    bester_regel = (len(wort_norm), regel, wort)

        # Gepflegte Regel schlägt den Geschäfts-Fallback: sie wurde bewusst
        # angelegt, der Geschäftsname ist nur ein Nebenprodukt der Stammdaten.
        if bester_regel:
            treffer = self._als_treffer(bester_regel[1], bester_regel[2])
            treffer.im_empfaengerfeld = _enthaelt_wort(nur_empfaenger, normalisiere(bester_regel[2]))
            return treffer

        bester_gesch: Optional[tuple[int, Geschaeft]] = None
        for gesch in self._geschaefte:
            name_norm = normalisiere(gesch.name)
            if len(name_norm) < MIN_SCHLUESSELWORT:
                continue
            if _enthaelt_wort(heuhaufen, name_norm) and (
                bester_gesch is None or len(name_norm) > bester_gesch[0]
            ):
                bester_gesch = (len(name_norm), gesch)

        if bester_gesch:
            gesch = bester_gesch[1]
            return Treffer(
                quelle="geschaeft",
                bezeichnung=gesch.name,
                schluessel=gesch.name,
                empfaenger_id=gesch.empfaenger_id,
                empfaenger_name=gesch.empfaenger_obj.name if gesch.empfaenger_obj else None,
                kategorie_id=gesch.standard_kategorie_id,
                notiz=gesch.name,
                geschaeft_id=gesch.id,
                im_empfaengerfeld=_enthaelt_wort(nur_empfaenger, normalisiere(gesch.name)),
            )
        return None

    @staticmethod
    def _als_treffer(regel: ImportRegel, schluessel: str) -> Treffer:
        return Treffer(
            quelle="regel",
            bezeichnung=regel.name,
            schluessel=schluessel,
            empfaenger_id=regel.empfaenger_id,
            empfaenger_name=regel.empfaenger_obj.name if regel.empfaenger_obj else None,
            kategorie_id=regel.kategorie_id,
            notiz=(regel.notiz_text or regel.name),
        )

    # -- Zusammenführung -------------------------------------------------
    def wende_an(
        self,
        empfaenger_roh: Optional[str],
        verwendungszweck: Optional[str] = None,
        iban: Optional[str] = None,
    ) -> RegelErgebnis:
        anbieter = self._finde_anbieter(empfaenger_roh, iban)
        haendler = self._finde_haendler(empfaenger_roh, verwendungszweck)
        ergebnis = RegelErgebnis(anbieter=anbieter, haendler=haendler)

        # Empfänger: Stufe 1 gewinnt, Stufe 2 füllt nur die Lücke. Bucht der
        # Laden per Lastschrift direkt ab, ist er selbst der Empfänger.
        #
        # Stufe 2 darf den Empfänger aber nur setzen, wenn ihr Schlüsselwort im
        # Bankempfängerfeld stand. Sonst würde eine Überweisung von „Karin
        # Mustermann“, die im Verwendungszweck „Streamflix“ erwähnt, den Empfänger
        # auf Streamflix umschreiben – der Verwendungszweck nennt den Grund der
        # Zahlung, nicht den Zahlungspartner.
        for treffer in (anbieter, haendler):
            if treffer and treffer.empfaenger_id and (
                treffer is anbieter or treffer.im_empfaengerfeld
            ):
                ergebnis.empfaenger_id = treffer.empfaenger_id
                ergebnis.empfaenger_name = treffer.empfaenger_name
                break

        # Kategorie: umgekehrt – der Händler ist die spezifischere Information.
        # "Lebensmittel" ist richtig, "Onlinezahlung" wäre nur der Zahlweg.
        for treffer in (haendler, anbieter):
            if treffer and treffer.kategorie_id:
                ergebnis.kategorie_id = treffer.kategorie_id
                break

        if haendler:
            ergebnis.notiz = haendler.notiz
            ergebnis.geschaeft_id = haendler.geschaeft_id

        return ergebnis


def empfaenger_namen(db: Session, ids: set[int]) -> dict[int, str]:
    """Namen zu Empfänger-IDs, für Anzeigen ohne geladene Relation."""
    if not ids:
        return {}
    return {
        e.id: e.name
        for e in db.query(Empfaenger).filter(Empfaenger.id.in_(ids)).all()
    }
