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

## Hinweise

- Beispiel-PDFs enthalten echte Kontodaten und werden **dauerhaft lokal**
  unter `kontoauszug_muster/` gespeichert (für spätere Parser-Tests).
- Rendering der Beispielseite erfolgt mit `pypdfium2` – keine externe Abhängigkeit.
- Die drei Bestandsbanken (Postbank/ING/Sparkasse) werden per Migration
  `e5f6a7b8c9d0` mit ihren bisher hartkodierten Keywords geseedet.
