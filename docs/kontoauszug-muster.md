# Kontoauszug-Muster (PDF-Import)

Der PDF-Kontoauszug-Import (`Import`-Seite) erkennt die Bank über **Muster**, die
unter **Einstellungen → Kontoauszug-Muster** verwaltet werden. Jedes Muster
verbindet eine Bank mit Erkennungs-Keywords, optional einem Code-Parser sowie
einem Beispiel-Screenshot, auf dem die Ziel-Datenbankfelder markiert sind.

## Datenmodell

Tabelle `kontoauszug_muster` (Modell `KontoauszugMuster`):

| Feld | Zweck |
|---|---|
| `name` | Anzeigename (z. B. „Postbank Giro") |
| `bank_key` | eindeutiger Schlüssel, zugleich Dateiname von Beispiel-PDF/-PNG |
| `parser_key` | Registrierter Code-Parser (`postbank`/`ing`/`sparkasse`); `NULL` = generischer Parser |
| `erkennung_keywords` | JSON-Array; kommt eines im PDF-Text vor, greift dieses Muster |
| `beispiel_pdf_pfad` | gespeichertes Beispiel-PDF (in `kontoauszug_muster/`) |
| `screenshot_pfad` | gerendertes PNG der ersten Seite |
| `feld_markierungen` | JSON `[{attribut,label,x,y,w,h}]`, Koordinaten relativ (0..1) |
| `aktiv` | nur aktive Muster werden bei der Erkennung berücksichtigt |

**Ziel-Attribute** einer Markierung: `datum`, `betrag`, `empfaenger`,
`verwendungszweck`, `iban_empfaenger`, `konto_hinweis`.

## Ablauf Erkennung & Import

1. `dispatcher.parse_pdf(pdf_bytes, db)` liest den Text der ersten Seite.
2. `_muster_fuer_text` sucht das erste **aktive** Muster, dessen Keyword im Text steht.
3. `_parser_fuer_muster` wählt den Code-Parser laut `parser_key`, sonst den
   generischen Best-Effort-Parser (`generic.py`).
4. Das Ergebnis (`ParseResult`) fließt unverändert in die bestehende Import-Vorschau.

## Neue Bank ergänzen

**Variante A – nur Muster (ohne Code, generischer Parser):**

1. Einstellungen → Kontoauszug-Muster → *Neues Muster aus Beispiel-Kontoauszug*.
2. Name + Erkennungs-Keywords angeben, Beispiel-PDF hochladen → Muster wird
   angelegt, Screenshot gerendert, Probe-Extraktion angezeigt.
3. Im Beispiel-Screenshot die Felder markieren (Rechteck aufziehen, Attribut wählen),
   speichern. Der generische Parser deckt einfache „Datum … Betrag"-Zeilen ab.

**Variante B – eigener Code-Parser (robust für komplexe Layouts):**

1. Neue Klasse `XyzParser(BankParser)` unter
   `backend/app/services/pdf_import/xyz.py` (analog `postbank.py`/`ing.py`/`sparkasse.py`).
2. In `dispatcher.PARSER_REGISTRY` unter einem `parser_key` registrieren.
3. Im Muster (Einstellungen) den `parser_key` eintragen → ab sofort wird der
   Code-Parser statt des generischen verwendet.

## CSV-Zeitraum sperrt das PDF

CSV-Exporte derselben Bank laufen über `csv_profil` (Spaltenzuordnung) durch
dieselben Endpunkte wie ein PDF — die Weiche ist der Dateikopf, nicht die Endung.
Da die CSV zur gleichen Zahlung mehr Felder liefert (IBAN, Umsatzart,
Mandatsreferenz), ist sie die bessere Quelle; das PDF bleibt als lesbares Archiv
erwünscht, soll aber keine Buchungen mehr anlegen, wo schon eine CSV liegt.

Ein Hash-Vergleich über die Formate hinweg ist unmöglich: `import_hash` enthält
den `bank_key`, und der Empfängertext einer CSV-Spalte lautet anders als der aus
einer geparsten PDF-Zeile. Gemeinsames Kriterium ist deshalb der **Zeitraum**.

Am Archiveintrag (`kontoauszug`) stehen dazu:

| Feld | Zweck |
|---|---|
| `format` | `'pdf'` / `'csv'` / `NULL` (Altbestand, sperrt nichts) |
| `zeitraum_von` / `zeitraum_bis` | abgedeckter Zeitraum |
| `zeitraum_bestaetigt` | `1` = vom Nutzer gesetzt, `0` = aus min/max Buchungsdatum abgeleitet |

Beim CSV-Import fragt der Dialog Von/Bis ab (vorbelegt aus den Buchungsdaten).
Lädt man danach ein PDF, markiert die Vorschau jede gedeckte Zeile. **Gesperrt**
wird sie aber nur, wenn es dazu auch eine Gegenbuchung gibt (Treffer-Vorschlag
oder Teil einer Sammelbuchung) — sonst könnte nichts doppelt gezählt werden und
die Zeile bleibt importierbar. So heilt ein abgeschnittener CSV-Export sich
selbst. Der Commit setzt die Sperre serverseitig durch, nicht nur im Frontend.

Zeitraum und Format lassen sich im Auszugs-Archiv nachträglich korrigieren
(Stift-Symbol, `PATCH /import/pdf/auszuege/{id}`) — nötig für Altbestände, deren
Format aus der Dateiendung migriert wurde.

## Hinweise

- Beispiel-PDFs enthalten echte Kontodaten und werden **dauerhaft lokal**
  unter `kontoauszug_muster/` gespeichert (für spätere Parser-Tests).
- Rendering der Beispielseite erfolgt mit `pypdfium2` – keine externe Abhängigkeit.
- Die drei Bestandsbanken (Postbank/ING/Sparkasse) werden per Migration
  `e5f6a7b8c9d0` mit ihren bisher hartkodierten Keywords geseedet.
