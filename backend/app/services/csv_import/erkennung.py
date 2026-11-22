"""Erkennt die Struktur einer Kontoumsatz-CSV ohne Vorwissen über die Bank.

Der Sinn der Übung: beim PDF ist das Layout der Parser, bei CSV ist es die
Spaltenzuordnung. Bleibt die Zuordnung Daten statt Code, braucht ein geänderter
Bankexport kein Release, sondern eine Korrektur in der Oberfläche. Diese Datei
rät dafür alles, was sich raten lässt – Kodierung, Trennzeichen, Kopfzeile,
Spaltenbedeutung, Datums- und Zahlenformat –, damit in der Maske im Regelfall
nur noch bestätigt wird.
"""

from __future__ import annotations

import csv
import re
from datetime import datetime
from typing import Optional

# Kandidaten in der Reihenfolge, in der sie ausprobiert werden.
TRENNZEICHEN = [";", ",", "\t", "|"]

DATUM_FORMATE = ["%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"]

# Zielfeld -> Suchbegriffe, absteigend nach Trennschärfe. Jede Spalte wird nur
# einmal vergeben, und die Felder werden in der Reihenfolge dieses Wörterbuchs
# bedient. Deshalb steht `verwendungszweck` vor `umsatzart`: die ING hat beide
# Spalten ("Verwendungszweck" und "Buchungstext"), eine Bank mit nur
# "Buchungstext" meint damit aber den Verwendungszweck.
SYNONYME: dict[str, list[str]] = {
    "datum":             ["buchungstag", "buchungsdatum", "buchung", "datum"],
    "betrag":            ["betrag", "umsatz", "summe"],
    "soll":              ["soll"],
    "haben":             ["haben"],
    "saldo":             ["saldo", "kontostand"],
    "valuta":            ["wertstellungsdatum", "wertstellung", "valuta", "wert"],
    "empfaenger":        ["begünstigter", "beguenstigter", "auftraggeber", "empfänger",
                          "empfaenger", "zahlungsempfänger", "zahlungspflichtiger",
                          "name", "kontoinhaber"],
    "empfaenger_zusatz": ["abweichender empfänger", "abweichender empfaenger",
                          "abw. empfänger", "abweichender zahlungsempfänger"],
    "iban":              ["iban", "kontonummer", "konto-nr", "gegenkonto"],
    "mandatsreferenz":   ["mandatsreferenz", "mandatsref", "mandat"],
    "referenz":          ["kundenreferenz", "end-to-end", "endtoend", "referenz"],
    "verwendungszweck":  ["verwendungszweck", "vwz", "buchungstext", "beschreibung",
                          "text"],
    "umsatzart":         ["umsatzart", "buchungsart", "buchungstext", "art",
                          "transaktionsart"],
}

# Begriffe, an denen die Spaltenzeile erkannt wird: eine Zeile, die sowohl nach
# Datum als auch nach Geldbetrag klingt, ist die Kopfzeile und keine Datenzeile.
KOPF_DATUM = ("buchungstag", "buchungsdatum", "buchung", "datum", "valuta",
              "wertstellung")
KOPF_BETRAG = ("betrag", "umsatz", "soll", "haben", "saldo", "summe")

ZAHL_RE = re.compile(r"^-?\d{1,3}(\.\d{3})*(,\d+)?$|^-?\d+(,\d+)?$|^-?\d+(\.\d+)?$")


def kodierung_erkennen(daten: bytes) -> str:
    """BOM schlägt alles, danach UTF-8, sonst cp1252.

    cp1252 und nicht latin-1: deutsche Bankexporte enthalten gelegentlich das
    Euro-Zeichen, das in latin-1 keinen Platz hat.
    """
    if daten.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig"
    try:
        daten.decode("utf-8")
        return "utf-8"
    except UnicodeDecodeError:
        return "cp1252"


def zeilen_lesen(daten: bytes, kodierung: str) -> list[str]:
    return daten.decode(kodierung, errors="replace").splitlines()


def trennzeichen_erkennen(zeilen: list[str]) -> str:
    """Das Zeichen, das über die Datei die gleichmäßigste Spaltenzahl ergibt.

    Nicht einfach das häufigste: ein Semikolon-Export mit Kommazahlen enthält
    mehr Kommas als Semikolons. Entscheidend ist, welche Aufteilung sich über
    viele Zeilen hinweg wiederholt.
    """
    beste, bester_wert = TRENNZEICHEN[0], -1.0
    for t in TRENNZEICHEN:
        zahlen = [len(z.split(t)) for z in zeilen[:60] if z.strip()]
        if not zahlen:
            continue
        haeufigste = max(set(zahlen), key=zahlen.count)
        if haeufigste < 3:
            continue
        # Wie viele Zeilen teilen die häufigste Spaltenzahl, mal deren Breite.
        wert = zahlen.count(haeufigste) * haeufigste
        if wert > bester_wert:
            beste, bester_wert = t, wert
    return beste


def kopfzeile_finden(tabelle: list[list[str]]) -> int:
    """Index der Spaltenzeile.

    Erst semantisch: die erste Zeile, die eine Datums- *und* eine
    Betragsüberschrift trägt. Das trifft beide bisher gesehenen Banken und hält
    auch dann, wenn im Kopf Zeilen mit vielen Feldern stehen. Nur wenn das
    nichts findet, strukturell: die erste Zeile, ab der die Feldzahl konstant
    bleibt.
    """
    for i, zeile in enumerate(tabelle[:40]):
        klein = [z.strip().lower() for z in zeile]
        if any(any(k.startswith(b) for b in KOPF_DATUM) for k in klein) and \
           any(any(b in k for b in KOPF_BETRAG) for k in klein):
            return i
    for i, zeile in enumerate(tabelle[:40]):
        n = len(zeile)
        if n >= 5 and all(len(z) == n for z in tabelle[i + 1:i + 3]):
            return i
    return 0


def _spalte_fuer(begriffe: list[str], kopf: list[str], vergeben: set[int]) -> Optional[str]:
    """Erste freie Spalte, deren Überschrift einen der Begriffe enthält.

    Begriffe stehen absteigend nach Trennschärfe; innerhalb eines Begriffs
    gewinnt die genaue Übereinstimmung vor dem Teiltreffer, damit "Buchung"
    nicht "Buchungstext" einsammelt, solange es eine Spalte "Buchung" gibt.
    """
    klein = [k.strip().lower() for k in kopf]
    for b in begriffe:
        for genau in (True, False):
            for i, k in enumerate(klein):
                if i in vergeben or not k:
                    continue
                if (k == b) if genau else (b in k):
                    vergeben.add(i)
                    return kopf[i]
    return None


def zuordnung_raten(kopf: list[str]) -> dict:
    vergeben: set[int] = set()
    zuordnung: dict = {}
    for feld, begriffe in SYNONYME.items():
        treffer = _spalte_fuer(begriffe, kopf, vergeben)
        if treffer:
            zuordnung[feld] = treffer
    # Liegt eine eigene Betragsspalte vor, sind Soll und Haben nur ihre
    # Aufspaltung (so bei der Postbank) und werden nicht gebraucht.
    if zuordnung.get("betrag"):
        zuordnung.pop("soll", None)
        zuordnung.pop("haben", None)
    return zuordnung


def datum_format_raten(werte: list[str]) -> Optional[str]:
    for fmt in DATUM_FORMATE:
        passend = 0
        for w in werte:
            try:
                datetime.strptime(w.strip(), fmt)
                passend += 1
            except ValueError:
                pass
        if werte and passend >= max(1, int(len(werte) * 0.9)):
            return fmt
    return None


def dezimal_raten(werte: list[str]) -> str:
    """Komma oder Punkt als Dezimaltrenner.

    Entschieden am letzten Trennzeichen eines Wertes: "1.234,56" endet auf
    Komma, "1,234.56" auf Punkt. Werte ohne Nachkommastellen zählen nicht mit.
    """
    komma = punkt = 0
    for w in werte:
        w = w.strip()
        if "," in w and "." in w:
            if w.rfind(",") > w.rfind("."):
                komma += 1
            else:
                punkt += 1
        elif re.search(r",\d{1,2}$", w):
            komma += 1
        elif re.search(r"\.\d{1,2}$", w):
            punkt += 1
    return "." if punkt > komma else ","


def saldo_marken_raten(kopfzeilen: list[list[str]],
                       fusszeilen: list[list[str]]) -> dict:
    """Findet im Kopf und im Fuß die Zeilen, die einen Kontostand tragen.

    Die Postbank schreibt den Anfangssaldo in den Kopf ("Letzter Kontostand")
    und den Endsaldo in die letzte Zeile ("Kontostand"). Beides steht außerhalb
    der Tabelle, ist für die Abstimmung nach dem Import aber Gold wert.
    """
    marken: dict = {}
    for zeile in kopfzeilen:
        if zeile and any(w in zeile[0].strip().lower() for w in ("kontostand", "saldo")):
            if any(ZAHL_RE.match(z.strip()) for z in zeile[1:]):
                marken["anfang_marke"] = zeile[0].strip()
    for zeile in fusszeilen:
        if zeile and any(w in zeile[0].strip().lower() for w in ("kontostand", "saldo")):
            if any(ZAHL_RE.match(z.strip()) for z in zeile[1:]):
                marken["ende_marke"] = zeile[0].strip()
    return marken


def erkennen(daten: bytes) -> dict:
    """Vollständiger Vorschlag für Struktur und Zuordnung einer CSV.

    Liefert nur Vorschläge; gespeichert wird, was in der Maske bestätigt wurde.
    `kopf_signatur` ist der Fingerabdruck, an dem dieselbe Datei beim nächsten
    Mal ihr Profil wiedererkennt.
    """
    kodierung = kodierung_erkennen(daten)
    zeilen = zeilen_lesen(daten, kodierung)
    if not any(z.strip() for z in zeilen):
        return {"fehler": "Die Datei enthält keine Zeilen."}

    trenner = trennzeichen_erkennen(zeilen)
    tabelle = list(csv.reader(zeilen, delimiter=trenner))
    kopf_index = kopfzeile_finden(tabelle)
    kopf = [z.strip() for z in tabelle[kopf_index]]
    breite = len(kopf)

    daten_zeilen = [z for z in tabelle[kopf_index + 1:] if len(z) == breite]
    fuss_zeilen = [z for z in tabelle[kopf_index + 1:] if len(z) != breite and any(z)]

    zuordnung = zuordnung_raten(kopf)
    index = {name: i for i, name in enumerate(kopf) if name}

    def spalte(feld: str) -> list[str]:
        name = zuordnung.get(feld)
        if not name or name not in index:
            return []
        i = index[name]
        return [z[i] for z in daten_zeilen[:200] if len(z) > i and z[i].strip()]

    struktur = {
        "kodierung": kodierung,
        "trennzeichen": trenner,
        "kopfzeile": kopf_index,
        "datum_format": datum_format_raten(spalte("datum")) or "%d.%m.%Y",
        "dezimal": dezimal_raten(spalte("betrag") or spalte("soll") + spalte("haben")),
        "betrag_modus": "betrag" if zuordnung.get("betrag") else "soll_haben",
        # Ein Saldo an jeder Zeile erlaubt die Prüfung jeder einzelnen Buchung
        # und schlägt deshalb den Dateisaldo, wo beides vorkommt.
        "saldo_modus": "zeile" if zuordnung.get("saldo") else "datei",
    }
    if struktur["saldo_modus"] == "datei":
        marken = saldo_marken_raten(tabelle[:kopf_index], fuss_zeilen)
        struktur.update(marken)
        if not marken:
            struktur["saldo_modus"] = "keiner"

    return {
        "struktur": struktur,
        "zuordnung": zuordnung,
        "kopf": kopf,
        "kopf_signatur": kopf,
        "kopfzeilen_text": [trenner.join(z) for z in tabelle[:kopf_index] if any(z)],
        "zeilen_gesamt": len(daten_zeilen),
        "probe": [dict(zip(kopf, z)) for z in daten_zeilen[:5]],
    }
