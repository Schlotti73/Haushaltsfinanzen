# Dev-Umgebung: Starten und Beenden

## Grundregel: niemals auf der produktiven Datenbank entwickeln

Entwicklung und Tests laufen **immer** auf einer Kopie der produktiven Datenbank,
nie auf der Produktivdatei selbst. Das gilt auch für "nur mal kurz schauen":
schon ein Start der App schreibt in die Datei (WAL, Migrationen, Login-Zeitstempel).

**Ablauf vor jeder Entwicklungssitzung** – ein Befehl erledigt alles:

```powershell
.\scripts\dev\copy_prod_db.ps1
```

Das Skript [`scripts/dev/copy_prod_db.ps1`](../scripts/dev/copy_prod_db.ps1)

1. beendet laufende Dev-Server auf Port 8000/5173 (sonst wird mitten im
   Schreibvorgang kopiert),
2. kopiert `finanzen.db` inkl. `-wal`/`-shm` nach `dev-db\dev_<Zeitstempel>.db`
   (die Produktivdatei wird dabei nur **gelesen**),
3. arbeitet das WAL in die Kopie ein und prüft sie (`quick_check`, Anzahl Buchungen),
4. trägt die Kopie in `config/datenbanken.json` ein und schaltet sie aktiv.

Danach `.\scripts\dev\run.ps1` starten – die App arbeitet auf der Kopie.

| Aufruf | Wirkung |
|---|---|
| `copy_prod_db.ps1` | Kopie `dev_<Zeitstempel>` anlegen und aktiv schalten |
| `copy_prod_db.ps1 -Name test` | eigener Name → `dev-db\test.db` |
| `copy_prod_db.ps1 -Name test -Force` | vorhandene Kopie gleichen Namens überschreiben |
| `copy_prod_db.ps1 -NurKopie` | nur kopieren, Registry nicht umstellen |
| `copy_prod_db.ps1 -Liste` | registrierte Datenbanken samt aktiver anzeigen |
| `copy_prod_db.ps1 -Zurueck` | Registry wieder auf die produktive `finanzen.db` stellen |
| `copy_prod_db.ps1 -NichtStoppen` | Dev-Server nicht beenden (nur wenn sicher nichts schreibt) |
| `copy_prod_db.ps1 -Quelle <pfad>` | andere Quelldatenbank statt `finanzen.db` |

Die Registry gewinnt immer – auch gegen `FINANZ_DB_PATH` und `.env`, siehe
[`backend/app/config.py`](../backend/app/config.py) und
[`backend/app/db_registry.py`](../backend/app/db_registry.py). Nach dem Start in der
App kontrollieren, dass die Kopie als aktive Datenbank angezeigt wird.

Händisch (falls das Skript nicht benutzt wird): `stop.ps1` → `Copy-Item` für
`finanzen.db`, `finanzen.db-wal`, `finanzen.db-shm` → Kopie in
`config/datenbanken.json` mit absolutem `dateipfad` als einzigen Eintrag mit
`"aktiv": true`.

**Weitere Regeln:**

- Migrations- und Setup-Skripte (`scripts/migrate_*.py`, `scripts/init_db.py --force`,
  `scripts/setup_fresh.py`) laufen zuerst auf der Kopie. Auf der Produktivdatenbank
  erst, wenn die Migration auf der Kopie fehlerfrei durchgelaufen ist – und davor
  ein Backup: `python scripts/backup.py`.
- Die Dev-Kopie wird **nie** zurückgeschrieben. Änderungen am produktiven
  Datenbestand entstehen nur durch die App selbst oder durch ein auf der Kopie
  geprüftes Migrationsskript.
- Dev-Kopien liegen unter `dev-db\` und gehören nicht ins Repository (`*.db` ist
  `.gitignore`t). Nicht mehr gebrauchte Kopien löschen und den Registry-Eintrag
  in `config/datenbanken.json` entfernen (oder in der App unter Einstellungen).
- Dasselbe gilt für Dateianhänge: `belege/`, `kontoauszuege/` und
  `kassenzettel_muster/` beim Testen nur lesen oder vorher kopieren, nie die
  produktiven Ordner überschreiben.

---

## Veröffentlichen

Der Weg vom privaten Arbeitsstand ins öffentliche Repository (und damit auf
die Seite unter GitHub Pages) steht in [`docs/veroeffentlichen.md`](veroeffentlichen.md):

```powershell
.\scripts\prod\veroeffentlichen.ps1 -Trockenlauf
```

---

## Variante A – getrennt starten/stoppen

```powershell
# Aus dem Projekt-Root:
.\scripts\dev\start.ps1
```

- Beendet automatisch alte Instanzen auf Port 8000 und 5173
- Öffnet zwei separate PowerShell-Fenster:
  - **„Haushaltsfinanzen – Backend :8000"** → uvicorn mit `--reload`
  - **„Haushaltsfinanzen – Frontend :5173"** → Vite Dev-Server (`--host`, im Heimnetz erreichbar)
- Backend braucht ~2–3 Sekunden bis es erreichbar ist

```powershell
# Aus dem Projekt-Root:
.\scripts\dev\stop.ps1
```

- Beendet alle Prozesse auf Port 8000 (Backend) und 5173 (Frontend)
- Alternativ: PowerShell-Fenster direkt schließen

## Variante B – ein Skript, bleibt aktiv (empfohlen)

```powershell
# Aus dem Projekt-Root:
.\scripts\dev\run.ps1
```

- Startet Backend + Frontend (jeweils eigenes Fenster) und bleibt selbst im aufrufenden Fenster **aktiv**, solange der Dev-Server läuft
- Mit **ENTER** in diesem Fenster werden nach Bestätigung beide Server (inkl. Reloader-Kindprozesse) zuverlässig beendet
- Praktisch für ein einzelnes Terminal/IDE-Fenster statt drei offenen Fenstern

## Vom Smartphone/anderen Gerät im Heimnetz testen

```powershell
# Einmalig als Administrator – gibt Port 8000 + 5173 in der Firewall frei:
.\scripts\dev\setup-firewall.ps1
```

- Legt Inbound-Regeln für das Profil „Privat" an und zeigt die LAN-IP des PCs an
- Auf dem Smartphone (im selben WLAN) im Browser öffnen: `http://<PC-IP>:5173`
- Die IP des PCs lässt sich auch manuell per `ipconfig` (IPv4-Adresse) ermitteln
- API-Aufrufe laufen über den Vite-Proxy (`/api` → `127.0.0.1:8000` auf dem PC), daher ist kein zusätzlicher CORS-Eintrag nötig

## URLs

| Dienst   | URL                       | Beschreibung              |
|----------|---------------------------|---------------------------|
| Frontend | http://localhost:5173      | React-App (Login etc.)    |
| Backend  | http://localhost:8000      | FastAPI                   |
| API-Docs | http://localhost:8000/docs | Swagger UI                |

## Login

Standard-Zugangsdaten (Entwicklung):

| Feld       | Wert       |
|------------|------------|
| Benutzername | `admin`  |
| Passwort   | `admin123` |

> Vor Produktivbetrieb in `scripts/init_db.py` ändern.

## Fehlerbehebung

### „Name oder Passwort falsch" im Browser

Meist läuft das Backend nicht. Prüfen:

```powershell
netstat -ano | Select-String ":8000"
```

Wenn keine Ausgabe → Backend neu starten:

```powershell
.\scripts\dev\start.ps1
```

### Backend startet nicht / fehlendes Modul

Fehlende Python-Pakete im venv nachinstallieren (immer über `python.exe -m pip`:
`pip.exe` hat den venv-Pfad fest eingebacken und schlaegt nach einem Kopieren des
Ordners stumm fehl):

```powershell
cd backend
.venv\Scripts\python.exe -m pip install <paketname>
```

**Bekannte Pakete die manuell nachinstalliert werden mussten:**

| Paket       | Grund                     |
|-------------|---------------------------|
| `pdfplumber` | PDF-Import (Phase 7)     |
| `pytesseract` | OCR Kassenzettel (Phase 8.4) |

### OCR-Setup (Tesseract, Phase 8.4)

Texterkennung für Kassenzettel-Fotos braucht zusätzlich die Tesseract-Programmdatei und
deutsche Sprachdaten (beide **nicht** Teil des Python-venv):

1. Tesseract-Binary installieren (einmalig, falls nicht vorhanden):
   ```powershell
   winget install --id UB-Mannheim.TesseractOCR
   ```
   Standardpfad: `C:\Program Files\Tesseract-OCR\tesseract.exe` (siehe `settings.tesseract_cmd`).
2. Sprachdaten nach `backend/tessdata/` legen (Ordner ist `.gitignore`t, da
   Binärdateien – nicht im Repo). Dieselbe Fassung, die auch das Container-Image
   beim Bauen lädt, damit Windows und Docker gleich erkennen (siehe
   [`docker/tessdata_laden.py`](../docker/tessdata_laden.py)):
   ```
   https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/deu.traineddata
   https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/eng.traineddata
   ```
   Nicht `main` statt `4.1.0` nehmen: dort können die Modelle wechseln, und dann
   erkennt der Entwicklungsrechner anders als das Image.
3. Prüfen: `tesseract --tessdata-dir backend/tessdata --list-langs` sollte `deu` und `eng` zeigen.

### Mehrere Instanzen laufen

`start.ps1` beendet beim Aufruf automatisch alte Prozesse auf den Ports.
Manuell prüfen und beenden:

```powershell
netstat -ano | Select-String ":8000|:5173"
# PID aus letzter Spalte ablesen, dann:
Stop-Process -Id <PID> -Force
```

## Abhängigkeiten prüfen

```powershell
# Python-Pakete im venv:
cd backend
.venv\Scripts\python.exe -m pip list

# Node-Pakete:
cd frontend
node --version
```
