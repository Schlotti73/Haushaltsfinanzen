"""
seed_demo.py – Erzeugt eine Demo-Datenbank mit erfundenen Daten.

Gedacht für Screenshots, Vorstellung und Ausprobieren. Alle Namen kommen aus
der Platzhalter-Welt in docs/beispieldaten.md – es wird nichts aus einer
echten Datenbank oder einem Backup gelesen, das Skript baut alles selbst.

Aufruf (aus Projektwurzel, mit dem Backend-Interpreter):
    backend/.venv/Scripts/python.exe scripts/seed_demo.py
    backend/.venv/Scripts/python.exe scripts/seed_demo.py --ziel dev-db/demo.db --force

Danach die Datei in den Einstellungen als Datenbank registrieren (oder in
config/datenbanken.json eintragen) und umschalten.

Die Daten sind bewusst deterministisch: derselbe Aufruf erzeugt dieselbe
Datenbank, damit Screenshots reproduzierbar bleiben. Bezugspunkt ist der
heutige Monat: 13 Monate Ist-Daten und drei Monate geplant nach vorn, damit
Dashboard, Statistik und Liquidität gefüllt aussehen.
"""

from __future__ import annotations

import argparse
import random
import sqlite3
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

ANMELDUNG = ("Demo", "demo1234")
SAAT = 20261114  # fester Zufallskern -> gleiche Demo-Daten bei jedem Lauf


# ── Hilfsmittel ──────────────────────────────────────────────────────────────

def monat_minus(ref: date, monate: int) -> date:
    """Erster Tag des Monats, der `monate` vor `ref` liegt.

    Ein negativer Wert zeigt nach vorn - so laesst sich dieselbe Funktion fuer
    die geplanten Monate verwenden.
    """
    jahr, monat = ref.year, ref.month - monate
    while monat <= 0:
        monat += 12
        jahr -= 1
    while monat > 12:
        monat -= 12
        jahr += 1
    return date(jahr, monat, 1)


def tag(basis: date, tag_im_monat: int) -> str:
    """ISO-Datum im Monat von `basis`, Tag auf die Monatslänge begrenzt."""
    letzter = 28 if basis.month == 2 else 30
    return date(basis.year, basis.month, min(tag_im_monat, letzter)).isoformat()


def passwort_hash(passwort: str) -> str:
    import bcrypt

    return bcrypt.hashpw(passwort.encode(), bcrypt.gensalt()).decode()


# ── Schema ───────────────────────────────────────────────────────────────────

def lege_schema_an(ziel: Path) -> None:
    """Volles Schema über die Anwendung selbst, nicht über db/schema.sql.

    schema.sql ist der Stand von Phase 1; Gebäude, Zähler und Import-Regeln
    kamen später als Migration dazu. Über init_db_schema entsteht derselbe
    Stand, den die laufende App erwartet.
    """
    from sqlalchemy import create_engine

    import app.models  # noqa: F401 – fuellt Base.metadata, sonst bleibt die DB leer
    from app.db_init import init_db_schema

    engine = create_engine(f"sqlite:///{ziel}")
    init_db_schema(engine)
    engine.dispose()


# ── Stammdaten ───────────────────────────────────────────────────────────────

KATEGORIEN = {
    "Einnahmen": ("einnahme", ["Gehalt", "Nebeneinkünfte", "Zinsen"]),
    "Wohnen": ("ausgabe", ["Miete", "Strom", "Wasser", "Heizung"]),
    "Lebenshaltung": ("ausgabe", ["Lebensmittel", "Haushaltswaren", "Drogerie"]),
    "Mobilität": ("ausgabe", ["Kraftstoff", "Bahn & Bus", "Werkstatt"]),
    "Versicherungen": ("ausgabe", ["Hausrat", "Haftpflicht", "Kfz"]),
    "Freizeit": ("ausgabe", ["Restaurant", "Abos", "Urlaub"]),
    "Haus & Garten": ("ausgabe", ["Material", "Handwerker", "Werkzeug"]),
    "Finanzen": ("beides", ["Darlehenszinsen", "Sparen", "Gebühren"]),
}

# Dritte Ebene: ein Zähler bzw. ein Posten je eigener Kategorie unter
# "Nebenkosten" - genau der Fall, für den die dritte Ebene da ist.
NEBENKOSTEN = ("Nebenkosten", "ausgabe", {
    "Musterweg 1": ["Strom Haus", "Wasser Haus", "Grundsteuer"],
})

KONTEN = [
    # name, typ, bank, iban, startsaldo, startdatum-Offset in Monaten
    ("Girokonto", "giro", "Beispielbank", "DE02120300000000202051", 2450.0, 13),
    ("Sparkonto", "spar", "Beispielbank", "DE02500105170137075030", 11800.0, 13),
    ("Depot", "depot", "Beispielbank", None, 7400.0, 13),
]

EMPFAENGER = [
    ("Wohnbau Beispielstadt", "DE02120300000000202052", "Miete", "Vermieter"),
    ("Stadtwerke Beispielstadt", "DE02120300000000202053", "Strom", "Strom und Wasser"),
    ("Beispiel Versicherung AG", "DE02120300000000202054", "Hausrat", None),
    ("Markt Müller", None, "Lebensmittel", "Supermarkt um die Ecke"),
    ("Getränke Nord", None, "Lebensmittel", "Getränkemarkt"),
    ("Baumarkt Süd", None, "Material", None),
    ("Pizza Primo", None, "Restaurant", None),
    ("Streamflix", None, "Abos", None),
    ("PayPal", "LU89751000135104712", None, "Zahlungsdienst, trägt beliebige Läden"),
    ("Mustermann, Erika", None, None, "Privat"),
]

GESCHAEFTE = [
    # name, Standard-Kategorie, verknüpfter Empfänger
    ("Markt Müller", "Lebensmittel", "Markt Müller"),
    ("Getränke Nord", "Lebensmittel", None),       # läuft über den Zahlungsdienst
    ("Baumarkt Süd", "Material", "Baumarkt Süd"),
    ("Sparmarkt", "Lebensmittel", None),
]

# Wiederkehrend: betrag, empfaenger, kategorie, rhythmus, Tag im Monat
WIEDERKEHREND = [
    (2800.0, "Arbeitgeber Beispiel GmbH", "Gehalt", "monatlich", 28),
    (-500.0, "Wohnbau Beispielstadt", "Miete", "monatlich", 1),
    (-95.0, "Stadtwerke Beispielstadt", "Strom", "monatlich", 5),
    (-12.99, "Streamflix", "Abos", "monatlich", 8),
    (-420.0, "Beispielbank", "Darlehenszinsen", "monatlich", 30),
    (-186.0, "Beispiel Versicherung AG", "Hausrat", "jaehrlich", 15),
]

# Alltagsbuchungen: empfaenger, kategorie, Betragsbereich, Anzahl im Monat
ALLTAG = [
    ("Markt Müller", "Lebensmittel", (-78.0, -22.0), 3),
    ("Sparmarkt", "Lebensmittel", (-46.0, -14.0), 2),
    ("Getränke Nord", "Lebensmittel", (-34.0, -11.0), 1),
    ("Drogerie Beispiel", "Drogerie", (-28.0, -8.0), 1),
    ("Tankstelle Beispielstadt", "Kraftstoff", (-92.0, -48.0), 1),
    ("Pizza Primo", "Restaurant", (-39.0, -16.0), 1),
    ("Baumarkt Süd", "Material", (-140.0, -18.0), 1),
]


def seed(con: sqlite3.Connection, heute: date) -> dict:
    rnd = random.Random(SAAT)
    zahl = lambda a, b: round(rnd.uniform(a, b), 2)  # noqa: E731

    # Benutzer
    con.execute(
        """INSERT INTO benutzer (name, passwort_hash, rolle, aktiv, erstellt_am, mfa_aktiv)
           VALUES (?, ?, 'admin', 1, datetime('now'), 0)""",
        (ANMELDUNG[0], passwort_hash(ANMELDUNG[1])),
    )

    # Kategorien (zwei Ebenen) + Nebenkosten-Baum (drei Ebenen)
    kat: dict[str, int] = {}
    for name, (art, kinder) in KATEGORIEN.items():
        top = con.execute(
            "INSERT INTO kategorien (name, art, uebergeordnet_id, aktiv) VALUES (?, ?, NULL, 1)",
            (name, art),
        ).lastrowid
        kat[name] = top
        for kind in kinder:
            kat[kind] = con.execute(
                "INSERT INTO kategorien (name, art, uebergeordnet_id, aktiv) VALUES (?, ?, ?, 1)",
                (kind, art if art != "beides" else "ausgabe", top),
            ).lastrowid

    nk_name, nk_art, nk_baum = NEBENKOSTEN
    nk_top = con.execute(
        "INSERT INTO kategorien (name, art, uebergeordnet_id, aktiv) VALUES (?, ?, NULL, 1)",
        (nk_name, nk_art),
    ).lastrowid
    kat[nk_name] = nk_top
    for haus, posten in nk_baum.items():
        haus_id = con.execute(
            "INSERT INTO kategorien (name, art, uebergeordnet_id, aktiv) VALUES (?, ?, ?, 1)",
            (haus, nk_art, nk_top),
        ).lastrowid
        kat[haus] = haus_id
        for p in posten:
            kat[p] = con.execute(
                "INSERT INTO kategorien (name, art, uebergeordnet_id, aktiv) VALUES (?, ?, ?, 1)",
                (p, nk_art, haus_id),
            ).lastrowid

    # Konten
    konto: dict[str, int] = {}
    for i, (name, typ, bank, iban, start, offset) in enumerate(KONTEN):
        konto[name] = con.execute(
            """INSERT INTO konten (name, typ, bank, iban, startsaldo, startdatum, sortierung, aktiv)
               VALUES (?, ?, ?, ?, ?, ?, ?, 1)""",
            (name, typ, bank, iban, start, monat_minus(heute, offset).isoformat(), i),
        ).lastrowid

    # Annuitätendarlehen mit Sondertilgung
    konto["Darlehen Hausbau"] = con.execute(
        """INSERT INTO konten
           (name, typ, bank, startsaldo, startdatum, sortierung, aktiv,
            darlehen_betrag, zinssatz, rate, tilgung_start,
            vollauszahlung_datum, zinsbindung_jahre)
           VALUES (?, 'darlehen', 'Beispielbank', ?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
        (
            "Darlehen Hausbau",
            # Startsaldo so gewaehlt, dass der Kontostand nach den vier
            # Projektausgaben (36.018,40 EUR) genau dem Darlehensbetrag
            # entspricht - sonst stuende mehr auf dem Konto als aufgenommen.
            -113981.60,
            monat_minus(heute, 36).isoformat(),
            3,
            150000.0,
            3.5,
            760.0,
            monat_minus(heute, 35).isoformat(),
            monat_minus(heute, 36).isoformat(),
            10,
        ),
    ).lastrowid
    con.execute(
        "INSERT INTO sondertilgung (konto_id, datum, betrag, notiz) VALUES (?, ?, ?, ?)",
        (konto["Darlehen Hausbau"], monat_minus(heute, 11).isoformat(), 5000.0, "Weihnachtsgeld"),
    )

    # Empfänger
    empf: dict[str, int] = {}
    for name, iban, kategorie, notiz in EMPFAENGER:
        empf[name] = con.execute(
            "INSERT INTO empfaenger (name, iban, kategorie_id, notiz) VALUES (?, ?, ?, ?)",
            (name, iban, kat.get(kategorie), notiz),
        ).lastrowid

    # Geschäfte
    gesch: dict[str, int] = {}
    for name, standard, empfaenger in GESCHAEFTE:
        gesch[name] = con.execute(
            """INSERT INTO geschaeft (name, standard_kategorie_id, empfaenger_id, aktiv)
               VALUES (?, ?, ?, 1)""",
            (name, kat.get(standard), empf.get(empfaenger) if empfaenger else None),
        ).lastrowid

    # Wiederkehrende Vorlagen
    wdk: dict[str, int] = {}
    for betrag, empfaenger, kategorie, rhythmus, tag_im_monat in WIEDERKEHREND:
        start = tag(monat_minus(heute, 12), tag_im_monat)
        wdk[empfaenger] = con.execute(
            """INSERT INTO wiederkehrende_buchungen
               (konto_id, betrag, empfaenger, kategorie_id, rhythmus, start_datum, aktiv)
               VALUES (?, ?, ?, ?, ?, ?, 1)""",
            (konto["Girokonto"], betrag, empfaenger, kat.get(kategorie), rhythmus, start),
        ).lastrowid

    # Projekt mit Plan-Posten
    projekt = con.execute(
        """INSERT INTO projekte (name, typ, budget, start_datum, darlehen_konto_id, aktiv)
           VALUES (?, 'bauprojekt', ?, ?, ?, 1)""",
        ("Sanierung Beispielhaus", 48000.0, monat_minus(heute, 8).isoformat(),
         konto["Darlehen Hausbau"]),
    ).lastrowid
    posten: dict[str, int] = {}
    for i, (bez, betrag, kategorie) in enumerate([
        ("Dach", 22000.0, "Handwerker"),
        ("Fenster", 14000.0, "Material"),
        ("Heizung", 9000.0, "Handwerker"),
        ("Werkzeug & Kleinteile", 1200.0, "Werkzeug"),
    ]):
        posten[bez] = con.execute(
            """INSERT INTO geplante_ausgabe
               (projekt_id, bezeichnung, betrag, kategorie_id, sortierung, erledigt)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (projekt, bez, betrag, kat.get(kategorie), i),
        ).lastrowid

    # Planung (Soll fürs laufende Jahr, Monatswerte)
    for kategorie, monatswert in [
        ("Lebensmittel", 420.0), ("Miete", 500.0), ("Strom", 95.0),
        ("Kraftstoff", 110.0), ("Restaurant", 60.0), ("Abos", 25.0),
    ]:
        con.execute(
            "INSERT INTO planung (kategorie_id, jahr, betrag_geplant) VALUES (?, ?, ?)",
            (kat[kategorie], heute.year, monatswert),
        )

    # ── Buchungen: 13 Monate zurück bis einen Monat voraus ──────────────────
    anzahl = 0

    def buche(konto_id, datum, betrag, empfaenger, kategorie, notiz=None,
              status="gebucht", quelle="manuell", wdk_id=None, transfer=0,
              gegen=None, posten_id=None):
        nonlocal anzahl
        anzahl += 1
        return con.execute(
            """INSERT INTO buchungen
               (konto_id, datum, betrag, empfaenger, kategorie_id, notiz, status, quelle,
                wiederkehrend_id, wiederkehrend_termin, empfaenger_id, ist_transfer,
                gegenbuchung_id, geplante_ausgabe_id, projekt_id, erstellt_am)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))""",
            (konto_id, datum, betrag, empfaenger, kat.get(kategorie), notiz, status, quelle,
             wdk_id, datum if wdk_id else None, empf.get(empfaenger), transfer,
             gegen, posten_id, projekt if posten_id else None),
        ).lastrowid

    for zurueck in range(13, -4, -1):
        monat = monat_minus(heute, zurueck)
        kuenftig = monat > date(heute.year, heute.month, 1)
        status = "geplant" if kuenftig else "gebucht"

        # Wiederkehrendes
        for betrag, empfaenger, kategorie, rhythmus, tag_im_monat in WIEDERKEHREND:
            if rhythmus == "jaehrlich" and monat.month != 3:
                continue
            buche(konto["Girokonto"], tag(monat, tag_im_monat), betrag, empfaenger,
                  kategorie, status=status, quelle="wiederkehrend",
                  wdk_id=wdk[empfaenger])

        if kuenftig:
            continue  # künftige Monate nur mit den geplanten Vorlagen

        # Alltag
        for empfaenger, kategorie, (von, bis), menge in ALLTAG:
            for n in range(menge):
                buche(konto["Girokonto"], tag(monat, 3 + n * 9 + rnd.randint(0, 3)),
                      zahl(von, bis), empfaenger, kategorie, quelle="import")

        # Monatlicher Übertrag aufs Sparkonto als Transfer-Paar
        ab = buche(konto["Girokonto"], tag(monat, 29), -250.0, "Sparkonto", "Sparen",
                   notiz="Übertrag", transfer=1)
        auf = buche(konto["Sparkonto"], tag(monat, 29), 250.0, "Girokonto", "Sparen",
                    notiz="Übertrag", transfer=1, gegen=ab)
        con.execute("UPDATE buchungen SET gegenbuchung_id = ? WHERE id = ?", (auf, ab))

        # Nebenkosten des Hauses
        buche(konto["Girokonto"], tag(monat, 12), zahl(-46.0, -31.0),
              "Stadtwerke Beispielstadt", "Wasser Haus", quelle="import")

    # Projektausgaben, auf Posten verknüpft
    for monate_zurueck, bez, betrag, empfaenger in [
        (6, "Dach", -18400.0, "Handwerk Beispiel GmbH"),
        (4, "Fenster", -13250.0, "Baumarkt Süd"),
        (2, "Heizung", -4100.0, "Handwerk Beispiel GmbH"),
        (1, "Werkzeug & Kleinteile", -268.4, "Baumarkt Süd"),
    ]:
        monat = monat_minus(heute, monate_zurueck)
        kategorie = "Handwerker" if "Handwerk" in empfaenger else "Material"
        # Ueber das Darlehenskonto, nicht ueber das Girokonto: so bleibt der
        # Alltag im Giro lesbar und die Bauausgaben stehen dort, wo sie
        # finanziert wurden.
        buche(konto["Darlehen Hausbau"], tag(monat, 18), betrag, empfaenger, kategorie,
              notiz=bez, posten_id=posten[bez])

    # ── Haushaltsbuch: Belege mit Positionen ────────────────────────────────
    belege = [
        (1, "Markt Müller", "karte", [
            ("Brot", 1, 3.49), ("Milch 1,5%", 2, 1.19), ("Äpfel 1 kg", 1, 2.99),
            ("Spülmittel", 1, 2.45), ("Kaffee 500 g", 1, 6.99),
        ], "Haushaltswaren"),
        (1, "Getränke Nord", "karte", [
            ("Wasser 12x1l", 2, 5.94), ("Saft 6x1l", 1, 8.94),
        ], None),
        (2, "Baumarkt Süd", "karte", [
            ("Dübel-Set", 1, 7.95), ("Silikon", 2, 4.49), ("Pinsel", 3, 2.95),
        ], "Werkzeug"),
        (2, "Markt Müller", "bar", [
            ("Gemüse", 1, 4.25), ("Nudeln", 3, 0.99), ("Käse", 1, 3.79),
        ], None),
    ]
    for monate_zurueck, laden, bezahlart, positionen, rest_kategorie in belege:
        monat = monat_minus(heute, monate_zurueck)
        datum = tag(monat, 14)
        summe = round(sum(menge * preis for _, menge, preis in positionen) + 3.80, 2)
        standard = next(g[1] for g in GESCHAEFTE if g[0] == laden)
        bar = bezahlart == "bar"
        b_id = buche(None if bar else konto["Girokonto"], datum, -summe, laden,
                     standard, notiz="Kassenzettel", quelle="haushaltsbuch")
        e_id = con.execute(
            """INSERT INTO haushaltsbuch_eintrag
               (datum, geschaeft_id, betrag_gesamt, bezahlart, konto_id, buchung_id,
                abgleich_status, ocr_status, ocr_konfidenz, notiz, erstellt_am)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'geparst', ?, ?, datetime('now'))""",
            (datum, gesch[laden], -summe, bezahlart,
             None if bar else konto["Girokonto"], b_id,
             "bar_ohne_konto" if bar else "verknuepft", 0.93, None),
        ).lastrowid
        for bez, menge, preis in positionen:
            con.execute(
                """INSERT INTO haushaltsbuch_position
                   (eintrag_id, bezeichnung, menge, einzelpreis, gesamtpreis, kategorie_id)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (e_id, bez, menge, preis, round(menge * preis, 2),
                 kat.get(rest_kategorie) if rest_kategorie and bez in ("Spülmittel", "Pinsel")
                 else kat.get(standard)),
            )

    # ── Gebäude mit Zählern und Ablesungen ──────────────────────────────────
    gebaeude = con.execute(
        "INSERT INTO gebaeude (name, strasse, plz, ort, notiz, aktiv) VALUES (?, ?, ?, ?, ?, 1)",
        ("Beispielhaus", "Musterweg 1", "12345", "Beispielstadt", "Demo-Gebäude"),
    ).lastrowid

    zaehler = {}
    for name, art, einheit, richtung, kategorie, sortierung in [
        ("Strom Haus", "strom", "kWh", "bezug", "Strom Haus", 0),
        ("PV-Einspeisung", "strom", "kWh", "einspeisung", "Strom Haus", 1),
        ("Wasser Haus", "wasser", "m³", "bezug", "Wasser Haus", 2),
        ("Wasser Garten", "wasser", "m³", "bezug", None, 3),
    ]:
        zaehler[name] = con.execute(
            """INSERT INTO zaehler
               (gebaeude_id, name, seriennummer, art, einheit, richtung, sortierung,
                kategorie_id, aktiv)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (gebaeude, name, f"SN-{1000 + sortierung}", art, einheit, richtung,
             sortierung, kat.get(kategorie)),
        ).lastrowid

    # Gartenzähler wird im Hauswasserzähler mitgemessen, PV mit dem Bezug verrechnet
    con.execute("UPDATE zaehler SET uebergeordneter_zaehler_id = ? WHERE id = ?",
                (zaehler["Wasser Haus"], zaehler["Wasser Garten"]))
    con.execute("UPDATE zaehler SET gegenzaehler_id = ? WHERE id = ?",
                (zaehler["Strom Haus"], zaehler["PV-Einspeisung"]))

    staende = {
        "Strom Haus": (14200, 3100),
        "PV-Einspeisung": (2600, 4200),
        "Wasser Haus": (412, 118),
        "Wasser Garten": (38, 22),
    }
    for name, (start, pro_jahr) in staende.items():
        for i, jahr in enumerate(range(heute.year - 2, heute.year + 1)):
            con.execute(
                """INSERT INTO zaehler_ablesung (zaehler_id, datum, jahr, stand, art, notiz)
                   VALUES (?, ?, ?, ?, 'jahr', NULL)""",
                (zaehler[name], f"{jahr}-12-31", jahr, start + i * pro_jahr),
            )
        # eine Zwischenablesung, die nichts verändert
        con.execute(
            """INSERT INTO zaehler_ablesung (zaehler_id, datum, jahr, stand, art, notiz)
               VALUES (?, ?, ?, ?, 'zwischen', 'Kontrollablesung')""",
            (zaehler[name], f"{heute.year}-06-30", heute.year,
             start + 2 * pro_jahr + pro_jahr // 2),
        )

    # Kostenkategorie ohne Zähler (Grundsteuer)
    con.execute(
        "INSERT INTO gebaeude_kostenkategorie (gebaeude_id, kategorie_id, sortierung) VALUES (?, ?, 0)",
        (gebaeude, kat["Grundsteuer"]),
    )
    for jahr in (heute.year - 1, heute.year):
        buche(konto["Girokonto"], f"{jahr}-02-15", -214.0, "Stadt Beispielstadt",
              "Grundsteuer", notiz="Grundsteuer")
    for jahr in (heute.year - 1, heute.year):
        buche(konto["Girokonto"], f"{jahr}-01-20", -1180.0, "Stadtwerke Beispielstadt",
              "Strom Haus", notiz="Jahresabrechnung Strom")

    con.commit()
    return {"buchungen": anzahl, "kategorien": len(kat), "konten": len(konto)}


# ── Einstieg ─────────────────────────────────────────────────────────────────

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--ziel", default="dev-db/demo.db", help="Pfad der Demo-Datenbank")
    p.add_argument("--force", action="store_true", help="vorhandene Datei überschreiben")
    args = p.parse_args()

    ziel = (ROOT / args.ziel).resolve() if not Path(args.ziel).is_absolute() else Path(args.ziel)
    if ziel.exists():
        if not args.force:
            print(f"Abbruch: {ziel} existiert bereits (--force zum Überschreiben).")
            return 1
        ziel.unlink()
    ziel.parent.mkdir(parents=True, exist_ok=True)

    lege_schema_an(ziel)

    con = sqlite3.connect(ziel)
    con.execute("PRAGMA foreign_keys = ON")
    try:
        ergebnis = seed(con, date.today())
    finally:
        con.close()

    print(f"Demo-Datenbank angelegt: {ziel}")
    print(f"  {ergebnis['buchungen']} Buchungen, {ergebnis['kategorien']} Kategorien, "
          f"{ergebnis['konten']} Konten")
    print(f"  Anmeldung: {ANMELDUNG[0]} / {ANMELDUNG[1]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
