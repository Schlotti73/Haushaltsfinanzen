"""Generischer CSV-Parser: ein Profil statt eines Parsers pro Bank.

Der Parser kennt keine Bank. Was eine Bank ausmacht, steht im Profil
(`csv_profil`): Kodierung, Trennzeichen, Kopfzeile, Datums- und Zahlenformat,
Vorzeichen- und Saldo-Verfahren sowie die Zuordnung Spalte -> Zielfeld. Ändert
eine Bank ihren Export, wird das Profil in der Oberfläche korrigiert statt der
Code in einem Release.

Ergebnis ist dasselbe `ParseResult` wie beim PDF-Import, damit Vorschau,
Dublettenprüfung, Import-Regeln, Haushaltsbuch-Abgleich und Archiv unverändert
weiterarbeiten.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from typing import Optional

from app.services.csv_import.erkennung import zeilen_lesen
from app.services.import_hash import make_hash
from app.services.pdf_import.base import BankParser, ParsedBuchung, ParseResult

IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
# Ein Datum darf nie als Zahl durchgehen: die Postbank schreibt ihren Endsaldo
# als Fußzeile der Form "Kontostand;<Datum>;;;<Betrag>;EUR", und ohne diese
# Sperre wird aus dem Datum durch das Entfernen der Tausenderpunkte eine
# achtstellige Zahl (aus "31.12.2025" etwa 31122025).
DATUM_AEHNLICH_RE = re.compile(r"^\d{1,2}[./-]\d{1,2}[./-]\d{2,4}$|^\d{4}-\d{2}-\d{2}$")


def _zahl(text: str, dezimal: str) -> Optional[float]:
    """Deutsche wie englische Schreibweise, tolerant gegen fehlende Nachkommastellen.

    Die Postbank schreibt die Nachkommastellen nur, soweit sie gebraucht werden
    ("-12,5" und "-50" stehen in derselben Spalte), deshalb wird hier nichts
    über die Stellenzahl angenommen.
    """
    t = (text or "").strip().replace("\xa0", "").replace(" ", "")
    if not t or DATUM_AEHNLICH_RE.match(t):
        return None
    t = t.replace("+", "")
    if dezimal == ",":
        t = t.replace(".", "").replace(",", ".")
    else:
        t = t.replace(",", "")
    # Nachgestelltes Vorzeichen, wie es manche Banken schreiben ("12,50-").
    if t.endswith("-"):
        t = "-" + t[:-1]
    try:
        return float(t)
    except ValueError:
        return None


def _datum_iso(text: str, fmt: str) -> Optional[str]:
    t = (text or "").strip()
    if not t:
        return None
    try:
        return datetime.strptime(t, fmt).strftime("%Y-%m-%d")
    except ValueError:
        return None


def _text(zeile: list[str], index: dict, zuordnung: dict, feld: str) -> Optional[str]:
    """Wert eines Zielfeldes. Mehrere Spalten (Verwendungszweck 1..n) werden
    zusammengefügt, weil manche Banken ihn aufteilen."""
    name = zuordnung.get(feld)
    if not name:
        return None
    namen = name if isinstance(name, list) else [name]
    teile = []
    for n in namen:
        i = index.get(n)
        if i is not None and i < len(zeile):
            wert = (zeile[i] or "").strip()
            if wert:
                teile.append(wert)
    return " ".join(teile) or None


def _saldo_aus_zeilen(zeilen: list[list[str]], marke: str, dezimal: str) -> Optional[float]:
    """Erster Zahlenwert in der Zeile, deren erste Zelle mit der Marke beginnt."""
    if not marke:
        return None
    for zeile in zeilen:
        if zeile and zeile[0].strip().lower().startswith(marke.strip().lower()):
            for zelle in zeile[1:]:
                wert = _zahl(zelle, dezimal)
                if wert is not None:
                    return wert
    return None


class CsvProfilParser(BankParser):
    """Parst eine CSV nach einem gespeicherten Profil."""

    def __init__(self, profil: dict):
        self.profil = profil
        self.name = profil.get("name") or "CSV"
        self.bank_key = profil.get("bank_key") or "csv"
        self.struktur = profil.get("struktur") or {}
        self.zuordnung = profil.get("zuordnung") or {}

    # Das PDF-Gegenstück heißt `parse(pdf_bytes)`; hier sind es beliebige Bytes.
    def parse(self, daten: bytes) -> ParseResult:
        s = self.struktur
        z = self.zuordnung
        dezimal = s.get("dezimal", ",")
        datum_format = s.get("datum_format", "%d.%m.%Y")

        result = ParseResult(bank=self.name, konto_hinweis=None)

        kodierung = s.get("kodierung") or "utf-8"
        tabelle = list(csv.reader(
            zeilen_lesen(daten, kodierung),
            delimiter=s.get("trennzeichen", ";"),
        ))
        if not tabelle:
            result.fehler.append("Die Datei enthält keine Zeilen.")
            return result

        kopf_index = self._kopfzeile(tabelle)
        if kopf_index is None:
            result.fehler.append(
                "Die Spaltenzeile des Profils kommt in dieser Datei nicht vor – "
                "hat die Bank ihren Export geändert?")
            return result

        kopf = [c.strip() for c in tabelle[kopf_index]]
        breite = len(kopf)
        # Erste Fundstelle gewinnt: die ING führt zwei Spalten "Währung", von
        # denen keine zugeordnet wird – ein Namensindex darf daran nicht scheitern.
        index: dict[str, int] = {}
        for i, name in enumerate(kopf):
            if name and name not in index:
                index[name] = i

        daten_zeilen = [r for r in tabelle[kopf_index + 1:] if len(r) == breite]
        rand_zeilen = ([r for r in tabelle[:kopf_index]]
                       + [r for r in tabelle[kopf_index + 1:]
                          if len(r) != breite and any(r)])

        # IBAN des eigenen Kontos aus dem Kopf, für den Hinweis in der Vorschau.
        for zeile in tabelle[:kopf_index]:
            for zelle in zeile:
                kandidat = (zelle or "").replace(" ", "").upper()
                if IBAN_RE.match(kandidat):
                    result.konto_hinweis = kandidat
                    break
            if result.konto_hinweis:
                break

        salden: list[Optional[float]] = []
        for nr, zeile in enumerate(daten_zeilen, start=1):
            datum = _datum_iso(_text(zeile, index, z, "datum") or "", datum_format)
            if not datum:
                result.fehler.append(f"Zeile {nr}: Datum nicht lesbar.")
                continue
            betrag = self._betrag(zeile, index, dezimal)
            if betrag is None:
                result.fehler.append(f"Zeile {nr}: Betrag nicht lesbar.")
                continue

            empf = _text(zeile, index, z, "empfaenger")
            zweck = _text(zeile, index, z, "verwendungszweck")
            # Der abweichende Empfänger ist bei der Postbank der eigentliche
            # Zahlungspartner hinter dem technischen Einzieher (z.B. die
            # Krankenkasse hinter ihrer Abrechnungsstelle). Er wandert an den
            # Verwendungszweck, nicht in das Empfängerfeld: dort würde er den
            # Import-Hash verschieben, und die Händler-Regeln durchsuchen den
            # Verwendungszweck ohnehin mit.
            zusatz = _text(zeile, index, z, "empfaenger_zusatz")
            if zusatz and zusatz != empf:
                zweck = f"{zweck} / Abw. Empfänger: {zusatz}" if zweck else \
                    f"Abw. Empfänger: {zusatz}"

            iban = _text(zeile, index, z, "iban")
            if iban:
                iban = iban.replace(" ", "").upper()

            pb = ParsedBuchung(
                datum=datum,
                betrag=betrag,
                empfaenger=empf,
                verwendungszweck=zweck,
                iban_empfaenger=iban if iban and IBAN_RE.match(iban) else None,
                valuta=_datum_iso(_text(zeile, index, z, "valuta") or "", datum_format),
                umsatzart=_text(zeile, index, z, "umsatzart"),
                mandatsreferenz=_text(zeile, index, z, "mandatsreferenz"),
                referenz=_text(zeile, index, z, "referenz"),
            )
            # Gleiches Schema wie die PDF-Parser (bank_key, Datum, Betrag,
            # Empfänger). Der Empfängertext geht bewusst mit ein: ohne ihn
            # kollidieren zwei Zahlungen gleicher Höhe am selben Tag an
            # verschiedene Empfänger, und das ist der häufigere Fall. Wer die
            # Empfängerspalte eines Profils nachträglich umstellt, ändert damit
            # alle künftigen Hashes – die Maske warnt davor.
            pb.import_hash = make_hash(self.bank_key, datum, betrag, empf)
            result.buchungen.append(pb)
            salden.append(_zahl(_text(zeile, index, z, "saldo") or "", dezimal)
                          if z.get("saldo") else None)

        result.saldo_pruefung = self._saldo_pruefen(
            result.buchungen, salden, rand_zeilen, dezimal)
        return result

    def _kopfzeile(self, tabelle: list[list[str]]) -> Optional[int]:
        """Gespeicherter Index, aber nur wenn er stimmt.

        Banken schieben gern eine Zeile in den Kopf. Deshalb wird der Index aus
        dem Profil geprüft und sonst die Zeile gesucht, die alle zugeordneten
        Spalten trägt – das Profil bleibt gültig, solange die Spaltennamen
        stehen.
        """
        gesucht = set()
        for wert in self.zuordnung.values():
            gesucht.update(wert if isinstance(wert, list) else [wert])
        gesucht = {g for g in gesucht if g}

        gespeichert = self.struktur.get("kopfzeile")
        kandidaten = ([gespeichert] if isinstance(gespeichert, int) else []) + \
            list(range(min(len(tabelle), 40)))
        for i in kandidaten:
            if not isinstance(i, int) or i < 0 or i >= len(tabelle):
                continue
            vorhanden = {c.strip() for c in tabelle[i] if c and c.strip()}
            if gesucht and gesucht.issubset(vorhanden):
                return i
        return None

    def _betrag(self, zeile: list[str], index: dict, dezimal: str) -> Optional[float]:
        z = self.zuordnung
        if self.struktur.get("betrag_modus") == "soll_haben":
            soll = _zahl(_text(zeile, index, z, "soll") or "", dezimal)
            haben = _zahl(_text(zeile, index, z, "haben") or "", dezimal)
            if soll not in (None, 0.0):
                # Manche Banken schreiben die Belastung ohne Vorzeichen in eine
                # eigene Spalte, andere mit.
                return soll if soll < 0 else -soll
            if haben is not None:
                return abs(haben)
            return None
        return _zahl(_text(zeile, index, z, "betrag") or "", dezimal)

    def _saldo_pruefen(self, buchungen: list[ParsedBuchung],
                       salden: list[Optional[float]],
                       rand_zeilen: list[list[str]], dezimal: str) -> dict:
        """Rechnet die Datei gegen ihre eigenen Kontostände.

        Zwei Verfahren, je nachdem was die Bank mitliefert:

        `zeile` – ein Kontostand an jeder Buchung (ING). Das ist die härteste
        Prüfung, die ein Auszug zulässt: jede fehlende, doppelte oder falsch
        gelesene Zeile bricht die Kette an einer benennbaren Stelle. Geprüft
        werden beide Sortierrichtungen, die bessere gewinnt – welche Richtung
        die Datei hat, muss das Profil deshalb nicht wissen.

        `datei` – Anfangs- und Endsaldo in Kopf und Fuß (Postbank). Dann muss
        Anfang + Summe aller Beträge den Endsaldo ergeben.
        """
        modus = self.struktur.get("saldo_modus", "keiner")
        summe = round(sum(b.betrag for b in buchungen), 2)
        ergebnis: dict = {"modus": modus, "zeilen": len(buchungen), "summe": summe}

        if modus == "zeile" and any(s is not None for s in salden):
            brueche_ab: list[str] = []
            brueche_auf: list[str] = []
            for i in range(len(salden) - 1):
                a, b = salden[i], salden[i + 1]
                if a is None or b is None:
                    continue
                if abs(round(a - buchungen[i].betrag, 2) - b) > 0.005:
                    brueche_ab.append(buchungen[i].datum)
                if abs(round(b + buchungen[i + 1].betrag, 2) - a) > 0.005:
                    brueche_auf.append(buchungen[i].datum)
            brueche = brueche_ab if len(brueche_ab) <= len(brueche_auf) else brueche_auf
            ergebnis.update({
                "uebergaenge": max(0, len(salden) - 1),
                "brueche": brueche[:10],
                "anzahl_brueche": len(brueche),
                "saldo_ende": salden[0] if brueche is brueche_ab else salden[-1],
                "stimmt": not brueche,
            })
            return ergebnis

        if modus == "datei":
            anfang = _saldo_aus_zeilen(
                rand_zeilen, self.struktur.get("anfang_marke", ""), dezimal)
            ende = _saldo_aus_zeilen(
                rand_zeilen, self.struktur.get("ende_marke", ""), dezimal)
            ergebnis.update({"saldo_anfang": anfang, "saldo_ende": ende})
            if anfang is not None and ende is not None:
                erwartet = round(anfang + summe, 2)
                ergebnis.update({
                    "erwartet": erwartet,
                    "abweichung": round(ende - erwartet, 2),
                    "stimmt": abs(ende - erwartet) <= 0.005,
                })
            return ergebnis

        ergebnis["stimmt"] = None
        return ergebnis
