# Datenmodell (Phase 1 – final)

Finalisiertes ER-Modell der Haushaltsfinanz-App. Maßgeblich umgesetzt in
[`db/schema.sql`](../db/schema.sql); die Stammdaten werden über
[`scripts/init_db.py`](../scripts/init_db.py) erzeugt.

## Überblick

```
benutzer ──< buchungen.erstellt_von
konten   ──< buchungen.konto_id          (NULL bei Bareinkauf)
kategorien ─< buchungen.kategorie_id      (Selbstreferenz: uebergeordnet_id → 2 Stufen)
projekte ──< buchungen.projekt_id
buchungen ─< buchung_tags >─ tags         (n:m)
buchungen ─< belege                       (Kassenzettel-Fotos)
buchungen ─< buchung_positionen           (Beleg-Aufteilung auf Kategorien)
wiederkehrende_buchungen ─< buchungen.wiederkehrend_id
projekte  ─< darlehen_raten               (Tilgungsplan, vgl. Sheet "Haus")
kategorien ─< planung                     (Jahresbudget, vgl. "Planung Gehalt")
```

## Tabellen (Kurzform)

| Tabelle | Zweck |
|---|---|
| `benutzer` | Login, Rollen `admin`/`bearbeiter` (Auth-Logik in Phase 2) |
| `konten` | Giro/Spar/Darlehen/Depot, mit `startsaldo`/`startdatum` für Saldoberechnung |
| `kategorien` | Zweistufiger Baum über `uebergeordnet_id`, `art` = einnahme/ausgabe/beides |
| `tags` | Freie organisatorische Tags (n:m zu Buchungen) |
| `projekte` | Darlehen/Bauprojekt/Sonstiges (ersetzt fixe Sheets "Haus"/"Neubau") |
| `buchungen` | Zentrale Bewegungstabelle, `status` geplant/gebucht, `quelle` |
| `buchung_tags` | n:m Buchung↔Tag |
| `belege` | Datei-Anhänge (Pfad im Dateisystem) |
| `buchung_positionen` | Aufteilung eines Belegs auf mehrere Kategorien |
| `wiederkehrende_buchungen` | Vorlagen für Daueraufträge/Abos → erzeugen geplante Buchungen |
| `darlehen_raten` | Tilgungsplan je Darlehensprojekt |
| `planung` | Jahresbudget je Kategorie (Soll/Ist-Vergleich) |

## Wichtige Designentscheidungen

1. **Beträge als `REAL` in Euro**, Vorzeichen = Richtung (negativ = Ausgabe).
   Entspricht der bisherigen Excel-Logik und hält den Import einfach.
   (Alternative „Integer-Cent" wurde verworfen – mehr Reibung bei Import/Anzeige
   ohne praktischen Mehrwert für eine private App.)
2. **Datum/Zeitstempel als ISO-`TEXT`** (`YYYY-MM-DD`) – sortierbar, SQLite-idiomatisch.
3. **Eine Kategorie pro Buchung (Pflicht-Empfehlung) + 0–n Tags** – fachliche
   Auswertung über Kategorie, organisatorische Querschnitte über Tags/Projekt.
4. **Redundante Excel-Spalten zusammengeführt:** „Info/Info 1" → `empfaenger`,
   „Datum/Datum 1" → `datum`, die Betrag-Duplikat-Spalte entfällt.
5. **`import_hash` UNIQUE** = Hash aus (konto_id, datum, betrag, empfaenger)
   verhindert Doppelimport bei mehrfachem Excel-Einlesen.
6. **Pivot-Sheets entfallen** – Jahres-/Monatsübersichten werden zur Laufzeit
   per SQL berechnet (Phase 5), keine manuelle Pflege mehr.

## Aktueller Stand der erzeugten DB

`finanzen.db` enthält nach `init_db.py` die Stammdaten:
- **7 Konten:** zwei Girokonten · vier Sparkonten · ein Depot
- **31 Kategorien** (10 Obergruppen + Untergruppen, siehe `config-vorlagen/kategorien.json`)
- **8 Tags** (aus dem Mapping abgeleitet)
- **4 Projekte:** ein Darlehens-, ein Bauprojekt und zwei weitere

---

# Phase 8 (geplant) – Haushaltsbuch als eigenes Objekt

Bisher ist „Haushaltsbuch" kein eigener Typ, sondern eine `Buchung` mit
`quelle='haushaltsbuch'`. Phase 8 trennt die **Beleg-/Artikelebene** (was wurde
gekauft) sauber von der **Geldebene** (`buchungen`, Kontobewegung) und führt
Geschäfte als Stammdaten ein.

## Grundprinzip: HHB ist immer durch *eine* Buchung gedeckt

Jeder Haushaltsbucheintrag (HHB) referenziert genau eine `Buchung`
(`buchung_id NOT NULL`):

- **Bareinkauf** → automatisch erzeugte konto-lose Buchung
  (`quelle='haushaltsbuch'`, `konto_id NULL`). Zählt wie heute als Ausgabe in
  Saldo/Statistik → **keine Änderung an `statistik.py`/Export/Soll-Ist nötig**.
- **Karten-/Kontoeinkauf** → der HHB wird mit der echten Bank-`Buchung`
  verknüpft (`buchung_id` zeigt darauf).

Der **Abgleich** (Anf. 5) bedeutet damit: die anfangs erzeugte Platzhalter-
Buchung eines Eintrags wird beim Kontoauszug-Import durch die echte Bank-Buchung
*ersetzt* (Platzhalter gelöscht → keine Doppelzählung).

> Alternative „HHB ohne Buchung + UNION in der Statistik" wurde verworfen: sie
> berührt `statistik.py`, `export/csv`, `hochrechnung` und Soll/Ist und ist damit
> deutlich invasiver, ohne praktischen Mehrwert für eine private App.

## Neue Tabellen

```
geschaeft ──< haushaltsbuch_eintrag.geschaeft_id
empfaenger ─< geschaeft.empfaenger_id            (optional, für Abgleich)
geschaeft ──1:1─ kassenzettel_muster.geschaeft_id (Phase 15, unique, SET NULL)
buchungen  ─< haushaltsbuch_eintrag.buchung_id   (1:1, NOT NULL, Deckung)
haushaltsbuch_eintrag ─< haushaltsbuch_position  (Artikel, CASCADE)
haushaltsbuch_eintrag ─< belege.eintrag_id       (Fotos, generalisiert)
```

### `geschaeft` (Anf. 2 – Geschäfte als Auswahlliste)

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | INTEGER PK | |
| `name` | TEXT UNIQUE NOT NULL | Markt Müller, Sparmarkt, Baumarkt Süd … |
| `standard_kategorie_id` | FK kategorien (SET NULL) | Fallback-Kategorie für nicht aufgeteilte Belege |
| `empfaenger_id` | FK empfaenger (SET NULL) | Brücke zum Kontoauszug-Namen |
| `aktiv` | INTEGER DEFAULT 1 | |

Bewusst getrennt von `empfaenger`: „Geschäft" = Laden, in dem eingekauft wird;
`empfaenger` = was auf dem Kontoauszug steht (oft „MARKT MUELLER DANKT//…",
PayPal-Sammelbuchung). `empfaenger_id` macht den Abgleich auflösbar.

**Phase 15 – Verknüpfung mit `kassenzettel_muster`:** `kassenzettel_muster.geschaeft_id`
(FK, unique, SET NULL) koppelt jedes Geschäft 1:1 an sein OCR-Muster. Die
MwSt→Kategorie-Map (Artikel-Kategorisierung) wird darüber auf der Geschäfte-Seite
gepflegt; die technischen Parser-Felder bleiben in den Einstellungen. Früher war die
Kopplung nur lose über den Namen/Key.

### `haushaltsbuch_eintrag` (Anf. 1 – HHB-Objekt)

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | INTEGER PK | |
| `datum` | TEXT NOT NULL | ISO |
| `geschaeft_id` | FK geschaeft (RESTRICT/SET NULL) | |
| `betrag_gesamt` | REAL NOT NULL | > 0 (Ausgabe) |
| `bezahlart` | TEXT CHECK ('bar','karte','konto') | |
| `konto_id` | FK konten (SET NULL) | optional, bei Karte/Konto |
| `buchung_id` | FK buchungen (RESTRICT) NOT NULL | Deckung (s.o.) |
| `abgleich_status` | TEXT CHECK ('bar_ohne_konto','offen','verknuepft') | |
| `ocr_status` | TEXT CHECK ('keine','roh','geparst') DEFAULT 'keine' | |
| `ocr_rohtext` | TEXT | Roh-OCR für Re-Parsing |
| `notiz` | TEXT | |
| `erstellt_von` | FK benutzer (SET NULL) | |
| `erstellt_am` | TEXT DEFAULT CURRENT_TIMESTAMP | |

### `haushaltsbuch_position` (Anf. 4.2 – Artikel einzeln)

| Spalte | Typ | Zweck |
|---|---|---|
| `id` | INTEGER PK | |
| `eintrag_id` | FK haushaltsbuch_eintrag (CASCADE) NOT NULL | |
| `bezeichnung` | TEXT NOT NULL | Artikelname (aus OCR oder Hand) |
| `menge` | REAL DEFAULT 1 | |
| `einzelpreis` | REAL | |
| `gesamtpreis` | REAL NOT NULL | |
| `kategorie_id` | FK kategorien (SET NULL) | optionale Artikel-Kategorie |

Bewusst getrennt von `buchung_positionen` (= Konto-seitige Aufteilung einer
Buchung auf Kategorien). Hier sind es echte Warenkorb-Artikel.

## Änderung an `belege` (Anf. 3+4 – Foto ansehen/auswerten)

- `belege.buchung_id` → **nullable**
- neu: `belege.eintrag_id` FK haushaltsbuch_eintrag (nullable, CASCADE)
- CHECK: genau eines von (`buchung_id`, `eintrag_id`) gesetzt

Damit hängt ein Kassenzettel-Foto am HHB statt an einer Platzhalter-Buchung;
Anzeige/Download laufen unverändert über `routers/belege.py`.

## Abgleich HHB ↔ Buchung (Anf. 5)

Match-Kriterien: **Betrag** (exakt → ±Toleranz), **Datum** (±N Tage),
**Geschäft↔Empfänger** (`geschaeft.empfaenger_id` oder Fuzzy-Name, vgl.
`services/empfaenger_match.py`). Zwei Auslöser, am Muster aus 7.1/7.3 orientiert:

- **5.1 Kontoauszug-Import** (`routers/import_pdf.py`): nach Commit offene HHB
  gegen neue Buchungen vorschlagen; bei Bestätigung Platzhalter ersetzen.
- **5.2 Manuelle Buchung** (`components/BuchungForm.jsx`): passt Datum+Betrag+
  Geschäft zu offenem HHB → „Mit Haushaltsbuch-Eintrag verknüpfen?".

Ersetzt die generische `verknuepft_mit_id`-Logik aus 7.1 durch eine typisierte FK.

## OCR (Anf. 4 – Entscheidung: Tesseract lokal)

`pytesseract` + Tesseract-Binary auf dem Windows-Server (kostenlos, bleibt im
Heimnetz, keine externen Aufrufe). Foto → Rohtext (`ocr_rohtext`) → heuristischer
Zeilen-Parser (Artikel + Preis) → Vorschlags-Positionen, die der Nutzer vor dem
Speichern korrigiert. Qualität bei Kassenzetteln durchwachsen → Parser-Ergebnis
ist immer editierbar, nie automatisch verbindlich.

## Migration (Entscheidung: bestehende HHB-Buchungen migrieren)

`scripts/migrate_phase8.py` (additiv/idempotent wie Phase 7):
1. Neue Tabellen + `belege`-Spalten anlegen, `db/schema.sql` nachziehen.
2. Geschäfte aus distinkten `empfaenger`-Werten der `quelle='haushaltsbuch'`-
   Buchungen seeden.
3. Pro `quelle='haushaltsbuch'`-Buchung einen `haushaltsbuch_eintrag` anlegen
   (`buchung_id` = diese Buchung, `bezahlart='bar'`, `abgleich_status=
   'bar_ohne_konto'`), zugehörige `belege` auf `eintrag_id` umhängen.
   Die Buchung selbst bleibt erhalten → Saldo/Statistik unverändert.
