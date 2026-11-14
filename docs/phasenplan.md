# Detaillierter Phasenplan – Haushaltsfinanz-App

Abgeleitet aus [`.docs/Projektplan_Haushaltsfinanz-App.md`](../.docs/Projektplan_Haushaltsfinanz-App.md).
Jede Aufgabe mit Modell-Empfehlung.

**Modell-Logik:**
🔵 **Opus** = Architektur, Datenmodell, knifflige Logik (Aggregationen, Abgleich, Mapping-Design).
🟢 **Sonnet** = Boilerplate, CRUD, UI-Komponenten, Skripte, Doku.
🟣 **opusplan** = gemischte Aufgaben (erst Design mit Opus, dann Umsetzung mit Sonnet automatisch).

Fortschritt: `[x]` erledigt · `[ ]` offen

---

## ✅ Phase 1 – Konzept & Datenmodell  *(abgeschlossen)*

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Vorhandene Arbeitsmappe analysieren (Sheets, Klasse-Werte, Häufigkeiten) | 🔵 Opus | Datengrundlage |
| [x] | Finales ER-Modell festlegen | 🔵 Opus | [`db/schema.sql`](../db/schema.sql) |
| [x] | Kategorie-Baum definieren (zweistufig) | 🔵 Opus | [`config-vorlagen/kategorien.json`](../config-vorlagen/kategorien.json) |
| [x] | Kategorien-Mapping „Klasse" → Kategorie/Tag/Projekt | 🔵 Opus | [`config-vorlagen/mapping.json`](../config-vorlagen/mapping.json), [`docs/kategorien-mapping.md`](kategorien-mapping.md) |
| [x] | Liste wiederkehrender Zahlungen erfassen | 🔵 Opus | [`docs/wiederkehrende-buchungen.md`](wiederkehrende-buchungen.md) |
| [x] | Lauffähige `finanzen.db` mit Stammdaten erzeugen | 🟢 Sonnet | [`scripts/init_db.py`](../scripts/init_db.py) |
| [x] | Datenmodell dokumentieren | 🟢 Sonnet | [`docs/datenmodell.md`](datenmodell.md) |

**Offen (Rückfragen an den Auftraggeber, blockieren Phase 3 nicht):**
- [ ] „Sonstiges" (1015×) belassen oder beim Import per Empfänger feiner klassifizieren?
- [ ] „Miete" = nur Einnahme, oder auch ausgehende Mietzahlungen darunter?
- [ ] „Rente" (Vorsorgevertrag) unter Versicherungen korrekt, oder eigene Kategorie „Vorsorge"?
- [ ] Haus vs. Neubau als zwei getrennte Projekte ok?

---

## ✅ Phase 2 – Backend-Grundgerüst  *(abgeschlossen)*

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Projektstruktur `backend/` (venv, `requirements.txt`) | 🟢 Sonnet | [`backend/requirements.txt`](../backend/requirements.txt) |
| [x] | SQLAlchemy-Modelle (alle 12 Tabellen) | 🟢 Sonnet | [`backend/app/models.py`](../backend/app/models.py) |
| [x] | Alembic einrichten, Initial-Migration | 🟢 Sonnet | [`backend/alembic/`](../backend/alembic/) |
| [x] | DB-Session/Dependency, Config | 🟢 Sonnet | [`backend/app/database.py`](../backend/app/database.py), [`backend/app/config.py`](../backend/app/config.py) |
| [x] | Pydantic-Schemas (Request/Response) je Entität | 🟢 Sonnet | [`backend/app/schemas.py`](../backend/app/schemas.py) |
| [x] | CRUD-Endpunkte: Konten (inkl. Saldo-Berechnung) | 🟢 Sonnet | [`backend/app/routers/konten.py`](../backend/app/routers/konten.py) |
| [x] | CRUD-Endpunkte: Kategorien (Baum+flach), Tags, Projekte | 🟢 Sonnet | routers/kategorien.py, tags.py, projekte.py |
| [x] | CRUD-Endpunkte: Buchungen (Filter, Tags, Positionen) | 🟢 Sonnet | [`backend/app/routers/buchungen.py`](../backend/app/routers/buchungen.py) |
| [x] | CRUD-Endpunkte: Wiederkehrende Buchungen | 🟢 Sonnet | [`backend/app/routers/wiederkehrend.py`](../backend/app/routers/wiederkehrend.py) |
| [x] | Auth: Login, Session-Cookie, bcrypt-Hashing | 🟢 Sonnet | [`backend/app/auth.py`](../backend/app/auth.py) |
| [x] | Rollenmodell (`admin`/`bearbeiter`) als Dependency/Guard | 🟢 Sonnet | `require_admin` in auth.py |
| [x] | Seed Admin-Benutzer `admin` in `init_db.py` | 🟢 Sonnet | `--passwort` Parameter |
| [x] | Endpunkte getestet (43 Routen, Login, CRUD, Saldo) | 🟢 Sonnet | curl-Tests ✓ |
| [x] | Als Windows-Dienst einrichten (NSSM) | 🟢 Sonnet | [`scripts/prod/install_service.ps1`](../scripts/prod/install_service.ps1) |

Server starten: `backend\start.bat` oder `uvicorn app.main:app --host 0.0.0.0 --port 8000`
API-Doku: http://localhost:8000/api/docs

---

## ✅ Phase 3 – Excel-Import  *(abgeschlossen)*

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Import-Grundgerüst (pandas/openpyxl), CLI mit Dry-Run-Option | 🟢 Sonnet | `import_excel.py` (Einmal-Werkzeug, nicht im Repository) |
| [x] | Mapping-Engine: `mapping.json` anwenden | 🟢 Sonnet | Klasse `Mapper` in import_excel.py |
| [x] | Import Postbank + ING (Info1 bevorzugt, Duplikate per hash) | 🟢 Sonnet | 1408 + 101 Buchungen |
| [x] | `import_hash` + Duplikatprüfung | 🟢 Sonnet | 16 Duplikate korrekt erkannt |
| [x] | Import Sparen (Bauspar-/Vorsorge-/Giro-/Haus-Sparkonten, Depot) | 🟢 Sonnet | 513 Buchungen |
| [x] | Import Haus → `darlehen_raten` | 🟢 Sonnet | 40 Raten |
| [x] | Import Neubau → Buchungen, Projekt Neubau | 🟢 Sonnet | 5 Buchungen |
| [x] | Import Nebenkosten → Tag je Art | 🟢 Sonnet | 96 Buchungen |
| [x] | Import Planung Gehalt → `planung` | 🟢 Sonnet | 149 Einträge |
| [x] | Import-Log (importiert/übersprungen/Fehler) | 🟢 Sonnet | Farbige Ausgabe ✓ |

**Ergebnis:** 2272 Netto-Datensätze importiert, 0 Fehler, 56 übersprungen (16 Buchungs-Duplikate + 40 Planungs-Überschreibungen). Voll idempotent: zweiter `--commit`-Lauf importiert 0.
Das Skript war ein Einmal-Werkzeug zur Altdatenübernahme und liegt nicht mehr im
Repository (siehe [`docs/beispieldaten.md`](beispieldaten.md)).

> **Fix 2026-06-14 (Test aller Phasen):** `darlehen_raten` hatte keinen Duplikatschutz und verdoppelte sich bei jedem Lauf (40→80→…). Behoben via Existenzprüfung auf `(projekt_id, datum)` in `insert_darlehen_rate`. Planungs-Zähler korrigiert (zählt Überschreibungen jetzt als „übersprungen").

---

## ✅ Phase 4 – Frontend: Erfassung & Verwaltung (PWA)  *(abgeschlossen)*

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | React + Vite + Tailwind aufsetzen, API-Client (axios + Proxy) | 🟢 Sonnet | [`frontend/`](../frontend/) |
| [x] | Auth-Flow (Login-Seite, Session-Cookie, geschützte Routen) | 🟢 Sonnet | `AuthContext.jsx`, `pages/Login.jsx` |
| [x] | Buchungsliste mit Filtern (Konto/Zeitraum/Kategorie/Status/Suche) + Paginierung | 🟢 Sonnet | `pages/Buchungen.jsx` |
| [x] | Formular Buchung anlegen/bearbeiten (inkl. Mehrfach-Tags, Modal) | 🟢 Sonnet | `components/BuchungForm.jsx` |
| [x] | Dashboard mit Saldo-Karten je Konto + letzte Buchungen | 🟢 Sonnet | `pages/Dashboard.jsx` |
| [x] | Verwaltung Konten (Saldo live berechnet) | 🟢 Sonnet | `pages/Konten.jsx` |
| [x] | Verwaltung Kategorien (Baum) + Tags | 🟢 Sonnet | `pages/Kategorien.jsx` |
| [x] | Verwaltung Projekte + Darlehensverlauf-Tabelle | 🟢 Sonnet | `pages/Projekte.jsx` |
| [x] | Verwaltung Benutzer (nur Admin) | 🟢 Sonnet | `pages/Benutzer.jsx` |
| [x] | Rollenbasierte Sichtbarkeit (Admin-Bereich in Sidebar) | 🟢 Sonnet | `components/Layout.jsx` |
| [x] | PWA: Web-App-Manifest (installierbar) | 🟢 Sonnet | `public/manifest.json` |

Frontend starten: `node node_modules/vite/bin/vite.js` (in `frontend/`)
Läuft auf: http://localhost:5173 mit Proxy zu Backend :8000

---

## ✅ Phase 5 – Haushaltsbuch, Wiederkehrende Buchungen & Dashboard  *(abgeschlossen)*

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Bareinkauf-Formular mit Foto-Upload (Kamera am Smartphone) | 🟢 Sonnet | `pages/Haushaltsbuch.jsx` |
| [x] | Beleg-Handling: Datei speichern, referenzieren, anzeigen/löschen | 🟢 Sonnet | `routers/belege.py` + `belegeApi` |
| [x] | Verwaltung wiederkehrender Buchungen (CRUD, Rhythmus, Aktiv-Toggle) | 🟢 Sonnet | `pages/Wiederkehrend.jsx` |
| [x] | Generierung geplanter Zukunftsbuchungen (Vorschau + Ausführen) | 🔵 Opus | `routers/generierung.py` |
| [x] | Liquiditätsvorschau (Kontostand heute + geplante Buchungen) | 🔵 Opus | `pages/Liquiditaet.jsx` |
| [x] | Monats-/Jahresübersicht mit Balkendiagramm | 🔵 Opus | `routers/statistik.py` |
| [x] | Ausgaben nach Kategorie (Donut-Chart + Tabelle) | 🔵 Opus | `Statistik.jsx` Tab Kategorien |
| [x] | Soll/Ist-Vergleich (Planung vs. Ist, Jahr) | 🔵 Opus | `Statistik.jsx` Tab Soll/Ist |
| [x] | Sparkonten-Entwicklung über Zeit (Linienchart, quartalsweise) | 🟢 Sonnet | `Statistik.jsx` Tab Sparkonten |
| [x] | Export als CSV | 🟢 Sonnet | `GET /api/statistik/export/csv` |
| [ ] | Abgleich geplant ↔ echt (Status geplant → gebucht) | 🔵 Opus | – offen – |
| [ ] | Beleg-Aufteilung auf mehrere Kategorien (`buchung_positionen`) | 🔵 Opus | – offen – |
| [x] | Projekt-Dashboard: Budget vs. Ist (Neubau) | 🟢 Sonnet | `routers/projekte.py` + `pages/Projekte.jsx` |
| [x] | Darlehensverlauf (Restschuld-Kurve) | 🟢 Sonnet | `pages/Projekte.jsx` (Tab-Ansicht) |

**Neue Routen (Backend):** `/api/statistik/*`, `/api/belege/*`, `/api/generierung/*` (56 Routen gesamt)
**Neue Seiten (Frontend):** Statistik, Haushaltsbuch, Liquidität, Wiederkehrend

> **Fix 2026-06-14 (Test aller Phasen):** Beleg-Upload akzeptierte nur den vom Client gemeldeten MIME-Typ und wies legitime Bilder ab, wenn der Client `application/octet-stream` sendet. Jetzt Fallback auf die Dateiendung (`_ermittle_mime`). Generierung end-to-end getestet inkl. Idempotenz (zweiter Lauf erzeugt 0).

---

## ✅ Phase 6 – Backup & Betrieb  *(abgeschlossen)*

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Backup-Skript: `finanzen.db` + Belege-Ordner (Zeitstempel, 30 behalten) | 🟢 Sonnet | [`scripts/backup.py`](../scripts/backup.py) |
| [x] | Windows-Aufgabenplanung für tägliches Backup | 🟢 Sonnet | [`scripts/prod/register_backup_task.ps1`](../scripts/prod/register_backup_task.ps1) |
| [x] | Optional: Ablage in Cloud-Sync-Ordner (OneDrive/Dropbox) | 🟢 Sonnet | `--ziel` Parameter in `backup.py` + `register_backup_task.ps1` |
| [x] | Betriebs-Doku: Installation, Start/Stop, Wiederherstellung, PWA-Installation | 🟢 Sonnet | [`docs/betrieb.md`](betrieb.md) |

**Backup manuell:** `python scripts/backup.py` oder `python scripts/backup.py --ziel C:/OneDrive/Backups/Haushalt`

### 6.1 – Prod-Umgebung als Windows-Systemdienst (NSSM)

Detailbeschreibung: [`.docs/Projektplan_Haushaltsfinanz-App.md`](../.docs/Projektplan_Haushaltsfinanz-App.md) Abschnitt „6.1 Prod-Umgebung als Windows-Systemdienst".

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | FastAPI liefert Frontend-Build per `StaticFiles` aus (SPA-Fallback, in Dev abschaltbar) | 🔵 Opus | [`backend/app/main.py`](../backend/app/main.py) |
| [x] | Health-Endpoint `GET /api/health` | 🟢 Sonnet | [`backend/app/main.py`](../backend/app/main.py) |
| [x] | Dienst-Installation via NSSM (Autostart, Auto-Restart, Logs nach `logs/`) | 🟢 Sonnet | [`scripts/prod/install_service.ps1`](../scripts/prod/install_service.ps1) |
| [x] | Update-Routine (stop → Backup → pull → deps → migrate → build → start → Health-Check) | 🔵 Opus | [`scripts/prod/update.ps1`](../scripts/prod/update.ps1) |
| [x] | Dienst-Deinstallation | 🟢 Sonnet | [`scripts/prod/uninstall_service.ps1`](../scripts/prod/uninstall_service.ps1) |
| [x] | Status-/Diagnose-Skript (Dienststatus + Logs + Health) | 🟢 Sonnet | [`scripts/prod/status.ps1`](../scripts/prod/status.ps1) |
| [x] | Prod-Doku: Erstinstallation + Update-Ablauf | 🟢 Sonnet | [`docs/betrieb.md`](betrieb.md) |

### 6.2 – Dev-Stop-Skript (Entwickler-PC)

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Stop-Skript: beendet Prozesse auf Dev-Ports 8000 (uvicorn) + 5173 (Vite) gezielt | 🟢 Sonnet | [`scripts/dev/stop.ps1`](../scripts/dev/stop.ps1) |
| [x] | Optional: symmetrisches Start-Skript (Backend `--reload` + Vite als Hintergrundprozesse) | 🟢 Sonnet | [`scripts/dev/start.ps1`](../scripts/dev/start.ps1) |

---

## ✅ Phase 7 – Erweiterungen & Integrationen  *(abgeschlossen)*

Detailbeschreibung: [`.docs/Projektplan_Haushaltsfinanz-App.md`](../.docs/Projektplan_Haushaltsfinanz-App.md) Abschnitt „Phase 7 – Erweiterungen & Integrationen (Detailplan)".

**Empfohlene Reihenfolge:** 7.4 → 7.2 → 7.3 → 7.1 → 7.6 → 7.5
**Migrationen:** additiv per `scripts/migrate_phase7.py` (`ALTER TABLE` / `CREATE TABLE IF NOT EXISTS`, idempotent) **und** `db/schema.sql` nachziehen — kein Alembic.

### 7.4 – Empfänger-Stammdaten  *(zuerst – Grundlage für 7.2/7.5)* · ~1–1,5 PT

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Migration: Tabelle `empfaenger` + `buchungen.empfaenger_id` | 🔵 Opus | [`scripts/migrate_phase7.py`](../scripts/migrate_phase7.py), [`db/schema.sql`](../db/schema.sql) |
| [x] | Modell `Empfaenger` + Relationship in `models.py` | 🟢 Sonnet | [`backend/app/models.py`](../backend/app/models.py) |
| [x] | Match-Service (IBAN exakt, Name-Fuzzy ~0.85) | 🔵 Opus | [`backend/app/services/empfaenger_match.py`](../backend/app/services/empfaenger_match.py) |
| [x] | Router CRUD + `?suche=` + `/{id}/zusammenfuehren` | 🟢 Sonnet | [`backend/app/routers/empfaenger.py`](../backend/app/routers/empfaenger.py) |
| [x] | Verwaltungsseite (Liste, Anlegen, Merge, IBAN-Suche) | 🟢 Sonnet | [`frontend/src/pages/Empfaenger.jsx`](../frontend/src/pages/Empfaenger.jsx) |
| [x] | Autocomplete + Kategorie-Vorbelegung im Buchungsformular | 🟢 Sonnet | [`components/BuchungForm.jsx`](../frontend/src/components/BuchungForm.jsx) |

### 7.2 – PDF-Kontoauszüge importieren · ~2,5–3,5 PT

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | `pdfplumber` in `requirements.txt` | 🟢 Sonnet | [`backend/requirements.txt`](../backend/requirements.txt) |
| [x] | `import_hash` aus `import_excel.py` in geteilten Service extrahieren | 🟢 Sonnet | [`backend/app/services/import_hash.py`](../backend/app/services/import_hash.py) |
| [x] | Parser-Architektur (`BankParser`-Basis + Postbank/ING) | 🔵 Opus | [`backend/app/services/pdf_import/`](../backend/app/services/pdf_import/) |
| [x] | Dublettenlogik: hart (hash) + weich (Datum+Betrag → „Verdacht") | 🔵 Opus | `routers/import_pdf.py` |
| [x] | Endpunkte `POST /import/pdf/vorschau` + `/commit` (zweistufig) | 🟢 Sonnet | [`backend/app/routers/import_pdf.py`](../backend/app/routers/import_pdf.py) |
| [x] | Import-Seite (Upload, Konto-Auswahl, Vorschau-Tabelle, Commit) | 🟢 Sonnet | [`frontend/src/pages/Import.jsx`](../frontend/src/pages/Import.jsx) |

### 7.3 – Buchungen ↔ Konten (Sparkonten-Transfers) · ~1,5–2 PT

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Migration: `buchungen.gegenbuchung_id` + `ist_transfer` | 🟢 Sonnet | `migrate_phase7.py`, `schema.sql` |
| [x] | Transfer-Kandidaten-Erkennung (Betrag −Betrag, Datum ±Toleranz) | 🔵 Opus | `routers/buchungen.py` |
| [x] | Endpunkt `POST /buchungen/{id}/transfer-verknuepfen` + Validierung | 🟢 Sonnet | `routers/buchungen.py` |
| [x] | Statistik: interne Transfers per Default ausblenden (`ist_transfer=0`) | 🔵 Opus | `routers/statistik.py` |
| [x] | UI: Transfer-Badge + Verknüpfen-Dialog | 🟢 Sonnet | `pages/Buchungen.jsx` |

### 7.1 – Buchungen ↔ Haushaltsbuch-Einträge · ~1,5–2 PT

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Migration: `buchungen.verknuepft_mit_id` + `verknuepfung_typ` | 🟢 Sonnet | `migrate_phase7.py`, `schema.sql` |
| [x] | Kandidaten-Vorschlag (Betrag ±Toleranz, Datum ±Tage, `quelle='haushaltsbuch'`) | 🔵 Opus | `routers/buchungen.py` |
| [x] | Endpunkte HH-Verknüpfen/-Lösen | 🟢 Sonnet | `routers/buchungen.py` |
| [x] | UI: Badge + Verknüpfen-Dialog | 🟢 Sonnet | `pages/Buchungen.jsx` |

### 7.6 – Wiederkehrende Buchungen in Statistik hochrechnen · ~1,5–2 PT

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Virtuelle Projektion (kein Persist) | 🔵 Opus | `routers/statistik.py` |
| [x] | Endpunkt `GET /statistik/hochrechnung` (Ist vs. Prognose) | 🔵 Opus | `routers/statistik.py` |
| [x] | Chart Ist vs. Prognose getrennt eingefärbt | 🟢 Sonnet | `pages/Statistik.jsx` (Tab „Hochrechnung") |

### 7.5 – Amazon-Abgleich (CSV, Stufe 1)  *(optionalste, zuletzt)* · ~2–2,5 PT

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Migration: Tabelle `amazon_bestellungen` + `einstellungen` (key/value) | 🟢 Sonnet | `migrate_phase7.py`, `schema.sql` |
| [x] | CSV-Parser + Abgleich Bestellung↔Buchung (Betrag+Datum, Kandidaten-Match) | 🔵 Opus | [`backend/app/routers/amazon.py`](../backend/app/routers/amazon.py) |
| [x] | Admin-Einstellungen (Amazon-IBAN, Empfängername) | 🟢 Sonnet | `routers/amazon.py` + Settings-UI in Amazon.jsx |
| [x] | UI: Bestellungsliste + Abgleich + CSV-Import | 🟢 Sonnet | [`frontend/src/pages/Amazon.jsx`](../frontend/src/pages/Amazon.jsx) |
| [ ] | ~~Stufe 2 Live-Artikelabruf (API/Scraping)~~ – **verworfen** (keine API für private Käufe; Scraping AGB-/2FA-problematisch) | – | nicht eingeplant |

**Aufwand Phase 7 gesamt:** ~10–13,5 PT. Tokens grob: Sonnet ~0,7–1,3 Mio, Opus ~1,1–2,0 Mio.

---

## ✅ Phase 8 – Haushaltsbuch als eigenes Objekt  *(abgeschlossen)*

Promoviert das bisherige `quelle='haushaltsbuch'` zu einem eigenen Domänenobjekt
(Beleg-/Artikelebene), getrennt von `buchungen` (Geldebene). Objektmodell-Details:
[`docs/datenmodell.md`](datenmodell.md) Abschnitt „Phase 8".

**Entscheidungen (Auftraggeber, 2026-06-16):** OCR = Tesseract lokal · bestehende
HHB-Buchungen werden migriert · Bar-HHB zählt als Ausgabe (jeder HHB ist durch
genau eine Buchung gedeckt → keine Statistik-Umbauten).

**Empfohlene Reihenfolge:** 8.1 → 8.2 → 8.3 → 8.5 → 8.4
**Migration:** additiv per `scripts/migrate_phase8.py` + `db/schema.sql` nachziehen.

### 8.1 – Schema, Modelle & Migration · ~1,5–2 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel |
|---|---|---|---|
| [x] | Tabellen `geschaeft`, `haushaltsbuch_eintrag`, `haushaltsbuch_position`; `belege` generalisieren (`eintrag_id`, `buchung_id` nullable, CHECK) | 🔵 Opus | `db/schema.sql` |
| [x] | SQLAlchemy-Modelle + Relationships | 🟢 Sonnet | `backend/app/models.py` |
| [x] | `migrate_phase8.py`: Tabellen + Datenmigration HHB-Buchungen → Einträge, Geschäfte aus Empfängern seeden, Belege umhängen | 🔵 Opus | `scripts/migrate_phase8.py` |

### 8.2 – Backend CRUD · ~2 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel |
|---|---|---|---|
| [x] | Router `geschaeft` (CRUD, `?suche=`, Aktiv-Toggle) | 🟢 Sonnet | `routers/geschaeft.py` |
| [x] | Router `haushaltsbuch` (Eintrag + Positionen, erzeugt Deckungs-Buchung bei Bar) | 🔵 Opus | `routers/haushaltsbuch.py` |
| [x] | Pydantic-Schemas; Beleg-Endpunkte für Einträge (`belege.py`) | 🟢 Sonnet | `schemas.py` |

### 8.3 – Frontend: Erfassung & Foto-Ansicht · ~2–2,5 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel (Anf.) |
|---|---|---|---|
| [x] | `Haushaltsbuch.jsx` umbauen: Geschäft-Dropdown (+ Schnellanlage), Artikel-Tabelle | 🟢 Sonnet | 1, 2, 4.2 |
| [x] | Beleg-Galerie mit Vollbild-/Zoom-Ansicht | 🟢 Sonnet | 3 |
| [x] | Geschäfte-Verwaltungsseite (Liste, Anlegen, Standard-Kategorie, Empfänger-Link) | 🟢 Sonnet | 2 |

### 8.4 – OCR: Foto → Artikel · ~2–3 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel (Anf.) |
|---|---|---|---|
| [x] | `pytesseract` + Tesseract-Setup, Service `services/ocr/` (Bild → Rohtext) | 🟢 Sonnet | 4.1 |
| [x] | Zeilen-Parser Kassenzettel → Artikel-Kandidaten (Bezeichnung, Menge, Preis) | 🔵 Opus | 4.2 |
| [x] | Endpunkt `POST /haushaltsbuch/{id}/ocr` (Vorschau) + UI-Übernahme mit Korrektur | 🟢 Sonnet | 4 |

### 8.5 – Abgleich HHB ↔ Buchung · ~2 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel (Anf.) |
|---|---|---|---|
| [x] | Match-Service (Betrag/Datum/Geschäft↔Empfänger), Platzhalter-Ersetzung | 🔵 Opus | 5 |
| [x] | Auslöser Kontoauszug-Import: Vorschläge nach Commit | 🔵 Opus | 5.1 |
| [x] | Auslöser manuelle Buchung: Verknüpfen-Dialog in `BuchungForm.jsx` | 🟢 Sonnet | 5.2 |

**Aufwand Phase 8 gesamt:** ~9,5–11,5 PT.

---

## ✅ Phase 9 – Kontoauszug-Muster verwalten  *(abgeschlossen)*

Quelle: [`.docs/Einstellung-Kontoauszug.md`](../.docs/Einstellung-Kontoauszug.md).
Macht die heute **fest codierten** PDF-Parser (Postbank/ING/Sparkasse, hartkodierte
Bank-Erkennung in `dispatcher.py`) zu einer im Einstellungsbereich **sichtbaren,
verwaltbaren Muster-Registry** mit Beispiel-Screenshot und Feld→DB-Visualisierung.

**Ausgangslage (Stand heute):** Parser unter
[`backend/app/services/pdf_import/`](../backend/app/services/pdf_import/) (`base.py`
mit `BankParser`/`ParsedBuchung`, je ein Regex-Parser pro Bank). Erkennung über
Keywords im Code (`dispatcher.py:_detect_bank`). Import-UI:
[`Import.jsx`](../frontend/src/pages/Import.jsx). Einstellungen heute nur Backup:
[`Einstellungen.jsx`](../frontend/src/pages/Einstellungen.jsx).

**Ziel-DB-Attribute eines Musters** (aus `ParsedBuchung` → `buchungen`):
`datum`, `betrag`, `empfaenger`, `verwendungszweck`, `iban_empfaenger`
(→ `import_iban`), plus `konto_hinweis` (Konto-IBAN aus dem Header).

**Architekturentscheidung:** Hybrid – Code-Parser bleiben (robust), aber Erkennung,
Doku, Beispiel-Screenshot und Feld-Mapping werden datengetrieben. Kein UI-Regex-Editor
(zu brüchig für Laien); neue Banken bekommen einen Code-Parser, das Muster ist die
sichtbare Registrierungs-/Doku-Stelle. Rendering der Beispielseite per `pypdfium2`
(bereits installiert – **keine neue Abhängigkeit**). Migration per **Alembic**
(neuer Stil seit Backup-/Alembic-Startup) + `db/schema.sql` nachziehen.

**Empfohlene Reihenfolge:** 9.1 → 9.2 → 9.3 → 9.4 → 9.5

### 9.1 – Schema, Modell & Migration · ~1 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel |
|---|---|---|---|
| [x] | Tabelle `kontoauszug_muster` (`id`, `name`, `bank_key`, `parser_key` nullable, `erkennung_keywords` JSON, `beispiel_pdf_pfad`, `screenshot_pfad`, `feld_markierungen` JSON, `aktiv`, `notiz`, `erstellt_am`) | 🔵 Opus | [`db/schema.sql`](../db/schema.sql) |
| [x] | SQLAlchemy-Modell `KontoauszugMuster` | 🟢 Sonnet | [`backend/app/models.py`](../backend/app/models.py) |
| [x] | Alembic-Migration (additiv) + Seed der 3 bestehenden Banken (Keywords aus `_detect_bank` übernommen) | 🔵 Opus | [`backend/alembic/versions/e5f6a7b8c9d0_kontoauszug_muster.py`](../backend/alembic/versions/e5f6a7b8c9d0_kontoauszug_muster.py), `db/schema.sql` |

### 9.2 – Dispatcher datengetrieben · ~1 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel |
|---|---|---|---|
| [x] | `_detect_bank` liest Erkennungs-Keywords aus aktiven Mustern statt hartkodiert; `parser_key` → Code-Parser-Registry (`PARSER_REGISTRY`) | 🔵 Opus | [`services/pdf_import/dispatcher.py`](../backend/app/services/pdf_import/dispatcher.py) |
| [x] | Generischer Best-Effort-Parser (`generic.py`) für noch ungemappte Muster (Datum/Betrag/Empfänger-Heuristik) | 🔵 Opus | [`services/pdf_import/generic.py`](../backend/app/services/pdf_import/generic.py) |
| [x] | Regressionssicherung: Postbank/ING/Sparkasse routen weiter auf ihren Code-Parser (verifiziert) | 🟢 Sonnet | manueller Test |

### 9.3 – Screenshot-Rendering & Beispiel-Upload · ~1–1,5 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel |
|---|---|---|---|
| [x] | Service: erste PDF-Seite → PNG via `pypdfium2`, Ablage in `kontoauszug_muster/` | 🟢 Sonnet | [`services/pdf_import/render.py`](../backend/app/services/pdf_import/render.py), `config.py` |
| [x] | Endpunkte: `GET/PUT/DELETE /einstellungen/kontoauszug-muster`, Upload Beispiel-PDF → Muster + Screenshot, `GET …/{id}/screenshot`, `…/ziel-attribute` | 🟢 Sonnet | [`routers/einstellungen.py`](../backend/app/routers/einstellungen.py) |
| [x] | „Neues Muster": Upload erzeugt ungemapptes Muster, generischer Parser liefert Probevorschau | 🔵 Opus | `routers/einstellungen.py` |

### 9.4 – Einstellungs-UI „Kontoauszug" · ~1,5–2 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel |
|---|---|---|---|
| [x] | Neue Gruppe in `Einstellungen.jsx`: Muster-Liste (Name, Bank, aktiv-Toggle, Keywords, Parser-Status) | 🟢 Sonnet | [`pages/Einstellungen.jsx`](../frontend/src/pages/Einstellungen.jsx), [`components/KontoauszugMuster.jsx`](../frontend/src/components/KontoauszugMuster.jsx) |
| [x] | Muster-Detailansicht: Beispiel-Screenshot + Marker-Editor (Rechteck ziehen → Attribut) + Legende | 🟢 Sonnet | `components/KontoauszugMuster.jsx` |
| [x] | „Neues Muster" (Beispiel-PDF hochladen, Name/Keywords erfassen, Probevorschau) | 🟢 Sonnet | `KontoauszugMuster.jsx` + [`api.js`](../frontend/src/api.js) |

### 9.5 – Doku · ~0,5 PT *(abgeschlossen)*

| Status | Aufgabe | Modell | Ziel |
|---|---|---|---|
| [x] | Erweiterungsdoku „neue Bank ergänzen" (Muster anlegen + Code-Parser registrieren) | 🟢 Sonnet | [`docs/kontoauszug-muster.md`](kontoauszug-muster.md) |

**Aufwand Phase 9 gesamt:** ~5–6 PT.

**Entscheidungen (Auftraggeber, 2026-06-19):**
- Feld-Markierungen **manuell** als Klick-Rechtecke auf dem Screenshot → `feld_markierungen` speichert pro Attribut die Bounding-Box (x/y/w/h relativ); Detailansicht in 9.4 braucht einen kleinen Rechteck-Zeichner.
- Beispiel-PDFs werden **dauerhaft gespeichert** (in `kontoauszug_muster/`), damit Parser später erneut getestet/angepasst werden können – sensible Kontodaten verbleiben lokal.

---

## ✅ Phase 12 – Projekte: geplante Ausgaben (Plan vs. Ist) & Darlehenskonto  *(abgeschlossen)*

Ziel (aus [`.docs/Optimierung.md`](../.docs/Optimierung.md)): geplante Ausgaben mit echten
Buchungen verknüpfen, Abweichung Plan ↔ Ist je Posten ermitteln; Darlehenskonto verknüpfen.

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Datenmodell: Tabelle `geplante_ausgabe` (Posten je Projekt), `buchungen.geplante_ausgabe_id` (Posten ↔ n Buchungen), `projekte.darlehen_konto_id` (→ Konto typ=darlehen) | 🔵 Opus | [`models.py`](../backend/app/models.py), [`db/schema.sql`](../db/schema.sql) |
| [x] | Alembic-Migration `h8c9d0e1f2a3` + idempotentes [`scripts/migrate_projekte_plan.py`](../scripts/migrate_projekte_plan.py) | 🟢 Sonnet | Migration additiv |
| [x] | Backend: CRUD `/projekte/{id}/geplante-ausgaben`, `…/verknuepfen` + `…/loesen`, `GET …/plan-vs-ist` (geplant/ist/abweichung je Posten + Summen) | 🔵 Opus | [`routers/projekte.py`](../backend/app/routers/projekte.py), [`schemas.py`](../backend/app/schemas.py) |
| [x] | Frontend: Detail-Tab „Planung" (Posten Plan/Ist/Abweichung, CRUD, Buchungen verknüpfen/lösen, aufklappbare Buchungsliste), Darlehenskonto-Auswahl im Projektformular | 🟢 Sonnet | [`pages/Projekte.jsx`](../frontend/src/pages/Projekte.jsx), [`api.js`](../frontend/src/api.js) |

**Entscheidungen (Auftraggeber, 2026-06-23):**
- Buchungs-Verknüpfung **1 Posten → n Buchungen** (Teilzahlungen abbildbar; `Ist` = Summe der verknüpften Buchungen).
- Darlehenskonto über **`projekte.darlehen_konto_id`** an ein Konto mit `typ='darlehen'`.
- `Abweichung` vorzeichenunabhängig: `abs(ist) − abs(geplant)`, `> 0` = Budget überschritten.

> **Offen (Modul „Konten" aus Optimierung.md, noch nicht umgesetzt):** Annuitäten-Darlehen direkt am Konto (Zinsen, Sondertilgung, Hochrechnung kommender Jahre, Transfer).

---

## ✅ Phase 13 – Konten: Annuitäten-Darlehen  *(abgeschlossen)*

Ziel (aus [`.docs/Optimierung.md`](../.docs/Optimierung.md)): Annuitäten-Darlehen direkt am
Konto – Zinsen, Sondertilgung, Hochrechnung kommender Jahre, Transfer. „Planung und reale Abzahlung".

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | Datenmodell: Loan-Felder an `konten` (`darlehen_betrag`, `zinssatz`, `rate`, `tilgung_start`, `zinsbindung_bis`), Tabelle `sondertilgung` | 🔵 Opus | [`models.py`](../backend/app/models.py), [`db/schema.sql`](../db/schema.sql) |
| [x] | Alembic-Migration `i9d0e1f2a3b4` (guarded) + idempotentes [`scripts/migrate_konten_darlehen.py`](../scripts/migrate_konten_darlehen.py) | 🟢 Sonnet | additiv |
| [x] | Backend: `GET /konten/{id}/darlehen-hochrechnung` (Annuitäten-Tilgungsplan monatlich + Jahres-Zusammenfassung + Eckdaten, inkl. Sondertilgungen, realer Saldo zum Vergleich), CRUD `/konten/{id}/sondertilgungen` | 🔵 Opus | [`routers/konten.py`](../backend/app/routers/konten.py), [`schemas.py`](../backend/app/schemas.py) |
| [x] | Frontend: Darlehensfelder im Konto-Formular, Darlehens-Detailansicht (Eckdaten, Restschuld-Kurve, Tilgungsplan, Sondertilgung-Verwaltung, Toggle „mit Sondertilgung") | 🟢 Sonnet | [`pages/Konten.jsx`](../frontend/src/pages/Konten.jsx), [`api.js`](../frontend/src/api.js) |

**Entscheidungen (Auftraggeber, 2026-06-23):**
- Loan-Parameter direkt am **Konto** (1:1), Hochrechnung wird **on-the-fly** berechnet (nicht gespeichert) → projekt-bezogene `DarlehenRate` bleibt unangetastet.
- **Zinsen**: monatlich `Restschuld × Zinssatz/12`; **Tilgung** = Rate − Zins; Annuität bis Restschuld 0 (Guard gegen Nicht-Tilgung & Endlosschleife, max. 70 Jahre).
- **Sondertilgung**: eigene Tabelle (geplant/real), wird monatsweise eingerechnet; Toggle für Szenario mit/ohne.
- **Transfer**: durch bestehende Transfer-Funktion (Phase 7.3) abgedeckt – reale Abzahlungen sind Transfers aufs Darlehenskonto und fließen über den realen Saldo (`real_restschuld`) in den Plan-vs-Ist-Vergleich ein.

> Damit sind **beide Module** aus `Optimierung.md` umgesetzt (Projekte = Phase 12, Konten = Phase 13).

---

## ✅ Phase 14 – OCR-Bildverbesserung Stufe 2 (CLAHE, Schatten, Schärfung)  *(abgeschlossen)*

Erweiterung von Phase 11 um drei weitere klassische CV-Varianten, die als Kandidaten
in die bestehende Wettbewerbs-Logik eingehängt werden. Kein neues Dependency, kein KI-Modell.

| Status | Aufgabe | Modell | Ergebnis |
|---|---|---|---|
| [x] | CLAHE-Variante (`clahe_adaptiv`): lokale Kontrastverstärkung für ungleichmäßige Beleuchtung | 🟢 Sonnet | `_clahe()` in preprocess.py |
| [x] | Schatten-Entfernung (`schatten_adaptiv`): Bild ÷ dilated Hintergrundmodell | 🟢 Sonnet | `_schatten_entfernen()` in preprocess.py |
| [x] | Unsharp Masking (`scharf_adaptiv`): Schärfungsvorstufe für leicht unscharfe Fotos | 🟢 Sonnet | `_unscharf_maskieren()` in preprocess.py |
| [x] | `_alle_varianten()`: 5 Varianten für Ganzbild-Pfad; Warp-Pfad behält 2 Basis-Varianten | 🟢 Sonnet | preprocess.py |

**Architektur-Entscheidung:** Die drei neuen Varianten werden nur auf das Ganzbild angewendet
(9 OCR-Läufe statt 6). Der Warp-Pfad (Perspektivkorrektur) nutzt weiterhin nur die beiden
Basis-Varianten, da die Beleuchtung nach Entzerrung meist gleichmäßig genug ist.

**Offen (Stufe 2/KI, falls Stufe 1 nicht ausreicht):**
- [ ] Real-ESRGAN (ONNX) als optionaler Super-Resolution-Schritt vor der Pipeline – nur bei Konfidenz < Schwellwert auslösen

---

## ✅ Phase 15 – Geschäfte & Artikel-Kategorien vereinheitlicht  *(abgeschlossen)*

Zwei zusammenhängende Verbesserungen rund um Geschäfte und Kategorien.

### 15.1 – Statistik nach Geschäft + Kategorien auf Artikelebene
| Status | Aufgabe | Ergebnis |
|---|---|---|
| [x] | Neuer Statistik-Tab/Endpoint „Geschäfte" (Ausgaben je Laden aus HHB-Belegen: Summe, Belege, Ø/Beleg) | `routers/statistik.py` `/statistik/geschaefte`, `Statistik.jsx` |
| [x] | Kategorien-Auswertung nutzt erfasste Artikel (`haushaltsbuch_position`): aufgeteilte Belege zählen auf Artikel-Kategorien statt der einen Buchungskategorie; Rest fällt auf Buchungskategorie zurück; negative Zeilen (Pfand/Rabatt) netten korrekt | `routers/statistik.py` `/statistik/kategorien` (CTE A/B/C) |

### 15.2 – Geschäft ↔ Kassenzettel-Muster echt verknüpft (FK)
Zuvor lebten die Standard-Kategorie (Geschäfte-Seite) und die MwSt→Kategorie-Map
(Einstellungen/Kassenzettel-Muster) getrennt und waren nur lose über den Namen gekoppelt.

| Status | Aufgabe | Ergebnis |
|---|---|---|
| [x] | FK `kassenzettel_muster.geschaeft_id` (unique, SET NULL) + 1:1-Relationship | `models.py`, Alembic `o5d6e7f8a9b0` |
| [x] | Migration verknüpft Bestandsdaten: je Muster gleichnamiges Geschäft finden/anlegen (10 Muster → 10 Geschäfte) | `o5d6e7f8a9b0` |
| [x] | Geschäft-Router liefert/speichert `mwst_kategorie_map` über das verknüpfte Muster (legt Muster bei Bedarf an) | `routers/geschaeft.py`, `schemas.py` (`MwstKatEintrag` zentralisiert) |
| [x] | MwSt→Kategorie-Editor direkt im Geschäfte-Formular + Map-Spalte in der Tabelle | `pages/Geschaefte.jsx` |
| [x] | Einstellungen-Muster zeigt Verknüpfung; Hinweis, dass die Map gleichwertig auf der Geschäfte-Seite pflegbar ist | `components/KassenzettelMuster.jsx` |

**Entscheidung:** Ein Geschäft ist die eine Stelle für „so werden meine Artikel
kategorisiert". Die technischen OCR-Parser-Felder (Marker, Regex, Beispielfoto)
bleiben in den Einstellungen; beide Seiten bearbeiten dasselbe verknüpfte Muster.
Standard-Kategorie = Fallback für nicht aufgeteilte Belege.

### 15.3 – „Rest = Standard-Kategorie" (nur Abweichler erfassen)
Idee: Nur die vom Laden-Standard abweichenden Artikel eintippen; der nicht erfasste
Rest des Belegs zählt automatisch auf die Standard-Kategorie.

| Status | Aufgabe | Ergebnis |
|---|---|---|
| [x] | (A) Standard-Kategorien für Seed-Läden (Supermärkte→Lebensmittel, Rossmann/dm→Drogerie) | Alembic `o6d7e8f9a0b1` (idempotent, nur wo NULL, per Kategorie-Name) |
| [x] | (B) Statistik-Rest härten: `COALESCE(Buchungskategorie, Geschäft.standard_kategorie_id)` in Part A+C | `routers/statistik.py` |
| [x] | (C) HHB-Formular zeigt beim Teil-Erfassen „Rest X € → Standard-Kategorie" (+ Warnung bei Überschreitung) | `pages/Haushaltsbuch.jsx` |

---

## Modell-Empfehlung pro Phase (Schnellüberblick)

| Phase | Empfohlener Session-Start | Begründung |
|---|---|---|
| 1 – Konzept & Datenmodell ✅ | 🔵 Opus | Strukturentscheidungen |
| 2 – Backend | 🟣 opusplan | Modelle/Auth (Opus) + viel CRUD (Sonnet) |
| 3 – Import | 🟣 opusplan | Mapping/Zusammenführung kniffliger als der Rest |
| 4 – Frontend PWA | 🟢 Sonnet | überwiegend UI-Boilerplate |
| 5 – Haushaltsbuch & Dashboard | 🟣 opusplan | komplexe Aggregations-/Abgleichlogik |
| 6 – Backup & Betrieb | 🟢 Sonnet | Skripte + Doku |
| 7 – Erweiterungen & Integrationen | 🟣 opusplan | Migrationen/Abgleich-/Parser-Logik (Opus) + CRUD/UI (Sonnet) |
| 8 – Haushaltsbuch als eigenes Objekt ✅ | 🟣 opusplan | Schema/Match-/Parser-Logik (Opus) + CRUD/UI (Sonnet) |
| 9 – Kontoauszug-Muster verwalten | 🟣 opusplan | Schema/Dispatcher-/Generic-Parser (Opus) + UI/Render/CRUD (Sonnet) |
| 14 – OCR-Bildverbesserung Stufe 2 ✅ | 🟢 Sonnet | rein klassische CV, kein Design-Aufwand |

> Faustregel: **Opus für „wie strukturieren/berechnen wir das?", Sonnet für „schreib den Code dafür".**
> Opus ist ~4–5× teurer pro Token — `opusplan` gibt automatisch die Design-Phase an Opus und die Umsetzung an Sonnet.
