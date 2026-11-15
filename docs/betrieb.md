# Betriebsdokumentation – Haushaltsfinanz-App

## Voraussetzungen

| Software | Version | Dev | Prod | Anmerkung |
|---|---|---|---|---|
| Python | 3.11 (exakt) | ✓ | ✓ | venv unter `backend/.venv` bzw. im Versionsordner |
| Node.js | 20+ | ✓ | – | nur für den Frontend-Build; das Paket bringt `frontend/dist` fertig mit |
| Tesseract-OCR | 5+ | ✓ | ✓ | per winget, Sprachdaten liegen im Paket |
| WinSW | 2.12 | – | ✓ | Dienst-Wrapper, wird beim Setup von GitHub geladen |
| App Installer (`winget`) | – | – | (✓) | nur nötig, solange Python oder Tesseract fehlen; sonst wird er nie aufgerufen |
| Git | beliebig | ✓ | – | die Versionsnummer kommt aus den Tags |
| SQLite | (via Python) | ✓ | ✓ | keine separate Installation nötig |

Auf dem Prod-PC installiert das Setup Python und Tesseract selbst. Internet
braucht es dort nur dafür – die Python-Pakete liegen als Wheels im Paket.

> **Python-Version:** `install_service.ps1` prüft die Minor-Version (`$pyZiel`,
> aktuell 3.11) und sucht den Interpreter über den `py`-Launcher — ein beliebiges
> `python` im PATH genügt nicht. Eine venv ist an ihre Minor-Version gebunden:
> passt sie nicht, wird `backend\.venv` gelöscht und neu gebaut, statt sie zu
> aktualisieren. Wer die Zielversion anhebt, ändert `$pyZiel` **und** die
> winget-ID `$pyWinget` im Skript, diese Tabelle und das Docker-Basisimage weiter
> unten — und prüft vorher, ob es für `numpy`, `opencv-python-headless`,
> `pypdfium2` und `bcrypt` Wheels für die neue Version gibt.
>
> **Aufrufe immer über `python.exe -m <modul>`:** die Konsolen-EXEn einer venv
> (`pip.exe`, `uvicorn.exe`) haben den venv-Pfad fest eingebacken und schlagen
> nach einem Verschieben oder Kopieren des Ordners stumm fehl (Exitcode 1, keine
> Ausgabe). Der Dienst startet deshalb ebenfalls `python.exe -m uvicorn`.

---

## Entwicklungsbetrieb (Dev)

```powershell
# Beide Dienste starten (je ein eigenes Terminal-Fenster):
.\scripts\dev\start.ps1

# Einzeln starten:
cd backend; .venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
cd frontend; node node_modules\vite\bin\vite.js --port 5173

# Beide Dienste stoppen:
.\scripts\dev\stop.ps1
```

Frontend läuft auf http://localhost:5173, proxyt API auf http://localhost:8000.

> **Regel:** In der Entwicklung nie auf der produktiven Datenbank arbeiten – vorher
> `.\scripts\dev\copy_prod_db.ps1` aufrufen (legt eine Kopie an und schaltet sie in
> `config/datenbanken.json` aktiv). Details:
> [`dev-workflow.md`](dev-workflow.md#grundregel-niemals-auf-der-produktiven-datenbank-entwickeln).

---

## Produktion: Ablage und Grundregel

Die Produktion läuft aus einem **Release-Paket**, nicht aus einem Git-Checkout.
Der Prod-PC braucht deshalb **kein Git, kein Node.js und kein Internet**.
Programm und Daten liegen getrennt:

```
C:\Program Files\Haushaltsfinanzen\ ← Programmordner
  versionen\v1.4.2\                   Vorversion, bleibt für den Rollback liegen
  versionen\v1.4.3\                   Code, Migrationen, backend\static, wheels\, .venv\
  current  ──►  Junction auf versionen\v1.4.3
  dienst\                             WinSW-Wrapper, zeigt dauerhaft auf current\
  letztes-update.json                 was ein Rollback zurückzulegen hätte

C:\ProgramData\Haushaltsfinanzen\   ← Datenordner
  finanzen.db · belege\ · kontoauszuege\ · kontoauszug_muster\
  kassenzettel_muster\ · databases\ · logs\ · backups\
  config\  →  server.json · datenbanken.json · backup.json
```

> **Grundregel:** Der Programmordner ist Paketinhalt und jederzeit restlos
> ersetzbar. Der Datenordner wird von einem Update **nie** angefasst.

Die Anwendung findet den Datenordner über `FINANZ_DATEN_DIR`, gesetzt in der
Dienst-Konfiguration. Siehe [`../backend/app/pfade.py`](../backend/app/pfade.py)
für alle vier Ablageorte (Programm, Daten, Einstellungen, Vorlagen) und
[`release-paket.md`](release-paket.md) für die Begründung.

Beide Ordner sind wählbar: `-Programm` und `-Daten` an `install_service.ps1`.
Danach stehen sie in der Registry, und Update, Rollback und Deinstallation
finden sie von allein wieder.

### Vorlagen und Einstellungen

| Art | Dateien | Ort | Beim Update |
|---|---|---|---|
| **Vorlage** – read-only, aus dem Repo | `config-vorlagen\kategorien.json`, `kategorien_minimal.json`, `mapping.json` | Programmordner | wird mit ersetzt |
| **Einstellung** – maschinenspezifisch, von der App beschrieben | `server.json`, `datenbanken.json`, `backup.json` | Datenordner, `config\` | bleibt unberührt |

> **Faustregel für neue Konfigurationsdateien:** Schreibt die App hinein, ist es
> eine Einstellung. Liest sie nur daraus und steht die Datei im Repo, ist es
> eine Vorlage.

---

## Release-Paket erstellen (auf dem Entwicklungsrechner)

```powershell
cd frontend; npm run build; cd ..
.\scripts\prod\create_prod_zip.ps1
```

Das Skript prüft, dass das Arbeitsverzeichnis sauber ist und das gebaute
Frontend unter `backend\static` existiert (**harter Abbruch**, keine Warnung –
ein Paket ohne Frontend fällt sonst erst auf dem Prod-PC auf), zählt die neuen
Alembic-Migrationen seit dem letzten Tag und fragt dann die Versionsnummer ab:

```
Letztes Release:  v1.4.2  (vor 11 Commits)
Neue Alembic-Migrationen: 2
  -> Empfehlung: Minor, weil ein Rollback nicht verlustfrei wäre

  [1] v1.4.3   Patch  - Fehlerkorrekturen, kein Schema-Wechsel
  [2] v1.5.0   Minor  - neue Funktion und/oder Migration   (empfohlen)
  [3] v2.0.0   Major  - Installation braucht manuellen Eingriff
  [4] eigene Nummer eingeben
  [5] ohne Tag bauen (Vorabpaket zum Testen)
```

| Stufe | Wann | Rollback |
|---|---|---|
| **Patch** | Fehlerkorrektur, **keine** neue Migration | verlustfrei, Junction genügt |
| **Minor** | neue Funktion und/oder neue Migration | nur über das DB-Backup |
| **Major** | Installation braucht manuellen Eingriff | siehe Release-Notiz |

Die Stufe sagt damit zugleich, **was ein Rollback kostet**. Eine Patch-Nummer
bei neuer Migration lehnt das Skript ab.

Danach legt es `git tag -a <version>` an, lädt die Python-Wheels
(`pip download --only-binary=:all:`) und schreibt
`Haushaltsfinanz_<version>.zip` (~100 MB). Der Tag ist zunächst nur lokal –
`git push --tags` nicht vergessen.

Die Versionsnummer lebt nur im **Git-Tag** und in der **`VERSION`-Datei im
Paket**; `package.json` und `main.py` tragen sie bewusst nicht, sonst entstünde
ein Zyklus aus Nummer-eintragen, Committen und Taggen. `main.py` liest die
`VERSION`-Datei zur Laufzeit, im Entwicklungsbetrieb steht dort `dev`.
Dieselbe Nummer liefert `GET /api/version` aus; die Oberfläche zeigt sie
unten links unter dem Anmeldenamen an.

```powershell
.\scripts\prod\create_prod_zip.ps1 -Version v1.5.0   # ohne Rückfrage
.\scripts\prod\create_prod_zip.ps1 -OhneTag          # Vorabpaket, Name trägt "-vorab"
```

---

## Erstinstallation (Produktion)

1. ZIP auf den Rechner bringen und **freigeben**: Rechtsklick → Eigenschaften →
   „Zulassen" ankreuzen. Ohne das blockt Windows die enthaltenen `.ps1`-Dateien
   per Mark-of-the-Web. `setup.cmd` entsperrt sie zwar selbst, aber nur wenn es
   selbst starten darf.
2. Entpacken.
3. `setup.cmd` im Paketstamm starten – Adminrechte holt es sich selbst.

Ohne Angabe landet das Programm unter `%ProgramFiles%\Haushaltsfinanzen`, die
Daten unter `%ProgramData%\Haushaltsfinanzen`. Das geht, weil der Dienst als
`LocalSystem` läuft und dort schreiben darf; 64-Bit-Python wird nicht
virtualisiert. Beides lässt sich frei überschreiben:

```powershell
.\setup.cmd -Programm D:\Apps\Haushaltsfinanzen -Daten D:\Daten\HF -Port 8080
```

Pfade mit Leerzeichen gehören in Anführungszeichen – aber **ohne**
abschließenden Backslash. `"D:\Meine Apps\HF\"` kommt als `D:\Meine Apps\HF"`
an, weil der Backslash das Anführungszeichen aufhebt; `NormalisierePfad`
schneidet das inzwischen ab, schöner ist es trotzdem ohne.

Fehlt `winget`, bricht das Setup ab, **bevor** es etwas anfasst – aber nur,
wenn Python oder Tesseract tatsächlich fehlen. Liegt beides schon vor, läuft es
auch ohne App Installer durch; das ist die Lage auf einem Windows Server ohne
Microsoft Store. Die Meldung nennt beide Bezugswege (Store und das
`.msixbundle` von `microsoft/winget-cli`) sowie den Ausweg, Python und
Tesseract von Hand zu installieren und `setup.cmd` erneut zu starten.

Das Setup installiert per winget **Python 3.11** und **Tesseract-OCR**, lädt
WinSW, kopiert das Paket nach `versionen\<version>\`, baut die Python-Umgebung
**offline aus `wheels\`** (`pip install --no-index`), legt den Datenordner an,
erzeugt Datenbank und Admin-Benutzer (interaktive Abfrage), setzt die Junction
`current`, richtet Dienst, Firewall-Regel, Registry-Eintrag und optional die
Backup-Aufgabe ein, startet den Dienst und prüft `/api/health`.

Node.js wird **nicht** installiert – das Frontend ist im Paket vorgebaut.
Scheitert die Installation aus `wheels\`, ist das Paket unvollständig, nicht das
Internet schuld.

Der Dienst läuft mit **WinSW** als `dienst\Haushaltsfinanzen.exe`, damit er im
Taskmanager unter eigenem Namen erscheint; die Konfiguration entsteht unter
gleichem Basisnamen als `dienst\Haushaltsfinanzen.xml` (WinSW-Konvention). Alle
Pfade darin zeigen auf `current\` – deshalb muss sie bei einem Update nicht neu
geschrieben werden. Die Firewall-Regel gilt für Inbound TCP im Profil „Privat",
damit die App im Heimnetz (z. B. vom Smartphone) erreichbar ist.

Danach ist die App unter **http://localhost:8000** und `http://<PC-IP>:8000`
erreichbar.

### Tägliches Backup registrieren (als Administrator)

```powershell
.\scripts\prod\register_backup_task.ps1
# Mit Cloud-Sync-Ordner (z. B. OneDrive):
.\scripts\prod\register_backup_task.ps1 -ZielOrdner "C:\Users\<Benutzer>\OneDrive\Backups\Haushalt"
```

Die Aufgabe startet `dienst\backup.cmd`, einen generierten Wrapper: der
Aufgabenplaner kann selbst keine Umgebungsvariablen setzen, `backup.py` braucht
aber `FINANZ_DATEN_DIR`. Der Wrapper zeigt auf `current\`, bleibt also über
Updates hinweg gültig.

---

## Update-Erkennung in der Anwendung

Die Anwendung prüft selbst, ob ein neueres Release vorliegt, und lädt das
Paket auf Wunsch herunter. **Installiert wird nichts** – das übernimmt ein
Doppelklick auf `<Programm>\update.cmd` bzw. `update.ps1` in einer
Administrator-Konsole, siehe nächster Abschnitt.
Der Grund: das Update stoppt genau den Dienst, der die Oberfläche ausliefert.

Zu finden unter **Einstellungen → Programm-Update**. Ist eine neuere Version
da, erscheint der Hinweis zusätzlich unten links in der Seitenleiste, unter
dem Anmeldenamen.

### Woher die Pakete kommen

Gefragt wird ein **eigenes, öffentliches Repository**, das nichts als die
Pakete enthält:

```
https://github.com/Schlotti73/Haushaltsfinanz-Releases
```

Der Quellcode bleibt im privaten Entwicklungs-Repository. Die Abfrage braucht
damit **keine Zugangsdaten**, und es kann nichts ablaufen.

Warum nicht einfach das private Repository? Dort bräuchte jede Installation
ein Personal Access Token, und dessen kleinste passende Berechtigung
(`Contents: Read`) umfasst zwangsläufig den gesamten Quellcode – eine
Beschränkung auf „nur die Release-Anhänge" kennt GitHub nicht. Dazu laufen
Token ab, je Installation einzeln, und GitHub erneuert sie nicht von selbst.
Das ZIP enthält ohnehin den Quellcode; die Trennung schützt also nichts, was
ein Token zu schützen hätte.

Ein Token lässt sich trotzdem eintragen, falls die Pakete später wieder
privat liegen. Es landet dann in `<Datenordner>\config\update.json`, steht in
`.gitignore` und wird von der API nie zurückgeliefert – die Oberfläche
erfährt nur, *ob* eines hinterlegt ist. Ein leeres Feld lässt das vorhandene
stehen.

### Release veröffentlichen

`create_prod_zip.ps1` legt nur Tag und ZIP an und nennt am Ende den passenden
Befehl. Das Hochladen bleibt ein bewusster Schritt:

```powershell
git push --tags
gh release create v1.5.0 .\Haushaltsfinanz_v1.5.0.zip `
   --repo Schlotti73/Haushaltsfinanz-Releases `
   --title v1.5.0 --notes "..."
```

Erst damit sehen die laufenden Installationen das Update. Das Tag im
öffentlichen Repository zeigt auf dessen `main` – es ist nur eine Marke am
Release, die Historie liegt weiter im privaten Repository.

### Download

Das geladene Paket landet in `<Datenordner>\updates\`, wird gegen die von
GitHub gemeldete SHA256-Summe geprüft und bei Abweichung verworfen. Ältere
Pakete räumt die Anwendung dort selbst weg – zum Zurückrollen dient die vorige
Installation, nicht das ZIP.

Die Release-Abfrage wird 15 Minuten zwischengespeichert. Ohne Token lässt
GitHub 60 Anfragen je Stunde und IP zu; mit dem Zwischenspeicher sind es
höchstens vier.

---

## Updates einspielen (Produktion)

Der bequeme Weg ist ein Doppelklick auf den Starter im Programmordner:

```
C:\Program Files\Haushaltsfinanzen\update.cmd
```

Er nimmt die neueste ZIP aus `<Datenordner>\updates\` – also das, was die
Anwendung unter Einstellungen → Programm-Update geladen hat –, fordert die
Administratorrechte selbst an und zeigt alles in **einem** Fenster, das bis zum
Tastendruck offen bleibt. Eine ZIP von anderswo lässt sich auf die Datei
ziehen; ein mitgegebener Pfad gewinnt immer vor dem Automatismus.

Aus einem **entpackten** Paket heraus geht es ebenso: dort liegt neben
`setup.cmd` eine `update.cmd`. Sie benutzt den entpackten Ordner direkt als
Quelle (`-Ordner`), es wird nichts ein zweites Mal entpackt.

> Warum eine `.cmd` und keine `.exe`: Stapelverarbeitungsdateien unterliegen
> weder der ExecutionPolicy noch einer Signaturprüfung und dürfen PowerShell
> mit `-ExecutionPolicy Bypass` aufrufen. Eine unsignierte `.exe` löste das
> Signaturthema nicht, sie verschöbe es nur – und handelte sich zusätzlich
> SmartScreen ein.

Der Starter wird **erzeugt**, nicht aus dem Paket kopiert: er zeigt auf
`current\` und bleibt darum über Updates hinweg gültig. Angelegt wird er von
`install_service.ps1` und bei jedem Update von `update.ps1` – eine Installation
aus der Zeit davor bekommt ihn also beim ersten Update nachgereicht. Zeigt
`current` nach einem Rollback auf eine Version ohne `scripts\prod\update.cmd`,
sagt der Starter das und nennt den Konsolenbefehl.

Die Erhöhung macht die `.cmd` selbst und nicht `update.ps1`: sonst gäbe es zwei
Fenster – ein wartendes ohne Ausgabe und ein erhöhtes, das sich am Ende sofort
schließt.

Der Weg über die Konsole bleibt unverändert und ist für Fernwartung und
Fehlersuche weiterhin der richtige:

```powershell
.\scripts\prod\update.ps1 -Paket D:\Austausch\Haushaltsfinanz_v1.5.0.zip
.\scripts\prod\update.ps1 -Ordner D:\Austausch\Haushaltsfinanz_v1.5.0
.\scripts\prod\update.ps1 -AusUpdates
```

Der Pfad darf alles sein: USB-Stick, Netzwerkfreigabe
(`\\dein-pc\releases\...`), lokaler Ordner.

| Schritt | Dienst |
|---|---|
| 1. Paket nach `versionen\<neu>\` entpacken | läuft weiter |
| 2. Python-Umgebung offline aus `wheels\` bauen | läuft weiter |
| 3. Alembic-Revision der Datenbank notieren | läuft weiter |
| 4. Dienst stoppen | **gestoppt** |
| 5. Pflicht-Backup der Datenbank (samt `-wal`/`-shm`) | gestoppt |
| 6. Alembic-Migration, explizit mit der neuen Umgebung | gestoppt |
| 7. Junction `current` umlegen | gestoppt |
| 8. Dienst starten, Health-Check | läuft |
| 9. Alte Versionen aufräumen (die letzten zwei bleiben) | läuft |

> Der teure Teil läuft, **während der Dienst noch die alte Version bedient**.
> Gestoppt wird nur für Backup, Migration und das Umlegen – die Ausfallzeit
> bleibt bei Sekunden.
>
> Scheitert etwas in den Schritten 1 bis 6, ist die Junction noch nicht
> umgelegt: die alte Version läuft weiter, und es braucht gar keinen Rollback.

Das Pflicht-Backup heißt nach alter und neuer Version:

```
C:\ProgramData\Haushaltsfinanzen\backups\vor-v1.5.0_von-v1.4.2_20261107-1830.db
```

---

## Rollback

```powershell
.\scripts\prod\rollback.ps1
.\scripts\prod\rollback.ps1 -Version v1.4.2   # auf eine bestimmte Version
```

**Code und Datenbank sind beim Rollback untrennbar.** Die Anwendung migriert auf
`head`; eine zurückgerollte Version kennt die Revision der neueren nicht und
verweigert den Start mit einer Schema-Abweichung. Die
`downgrade()`-Funktionen sind dafür kein Weg: sie sind destruktiv
(`drop_column`, `drop_table`) und teils absichtlich unvollständig.

`rollback.ps1` liest `letztes-update.json` und entscheidet danach:

| Fall | Was passiert |
|---|---|
| Schema **unverändert** (Patch-Update) | nur die Junction wird zurückgelegt – **verlustfrei** |
| Schema **geändert** | Junction **und** Datenbank aus dem Pflicht-Backup; alles seit dem Update ist verloren. Verlangt eine zweite Bestätigung durch Eingabe der Zielversion. Die jetzige Datenbank wird vorher als `verworfen-<version>_<zeit>.db` zur Seite gelegt. |

---

## Status & Diagnose

```powershell
.\scripts\prod\status.ps1
```

Zeigt: Version · aktive Junction und die Versionen daneben · letztes Update mit
Schema-Änderung und zugehöriger Sicherung · Dienststatus · Health-Check · die
letzten 30 Log-Zeilen · ein nicht leeres Fehlerprotokoll.

Logs liegen im Datenordner unter `logs\`.

> Startet der Dienst nicht, ist die häufigste Ursache eine **Schema-Abweichung**:
> in der Produktion migriert der Dienst nicht selbst
> (`FINANZ_AUTO_MIGRATE=0`), sondern prüft nur und nennt im Log, was zu tun ist.
> Siehe [Migration](#migration-nur-das-update-skript).

---

## Migration: nur das Update-Skript

| Umgebung | `FINANZ_AUTO_MIGRATE` | Verhalten beim Start |
|---|---|---|
| Dev | `1` (Vorgabe) | migriert selbst – jeder Start zieht das Schema nach |
| Prod (Dienst-XML) | `0` | **prüft nur** und verweigert bei Abweichung den Start |

Gründe: Mit Versionsordnern wird die neue Version aufgebaut, während die alte
noch läuft – migrierte dabei etwas, sähe der laufende alte Code mitten im
Betrieb ein unbekanntes Schema. Und eine Selbstmigration machte **jeden**
Neustart zu einem möglichen Schema-Änderer ohne Backup, auch den Neustart nach
dem Zurückspielen einer alten Datenbank.

Migrieren darf deshalb allein `update.ps1` (bzw. `install_service.ps1` bei der
Erstinstallation), und beide legen vorher ein Backup an. Siehe
[`pruefe_schema`](../backend/app/db_init.py).

---

## Dienst-Deinstallation (als Administrator)

```powershell
C:\Haushaltsfinanzen\dienst\uninstall_service.ps1
```

Liegt beim Dienst-Wrapper, nicht in einem Versionsordner – damit sie auch dann
noch funktioniert, wenn keine Version mehr vorhanden ist. Fragt einzeln nach
Dienst, Firewall-Regeln, Registry-Eintrag, Programmordner und Tesseract.

> Der **Datenordner wird nie angetastet**: Datenbank, Belege, Kontoauszüge,
> Sicherungen und Einstellungen bleiben liegen, eine Neuinstallation nimmt sie
> wieder auf. Wer sie wirklich loswerden will, löscht den Ordner von Hand – das
> Skript nennt ihn am Ende.

---

## Manuelles Backup

```powershell
python scripts\backup.py
# Alternativ mit Zielordner:
python scripts\backup.py --ziel "C:\OneDrive\Backups\Haushalt"
```

Backups liegen unter `backups\` (Standard), max. 30 werden behalten.

---

## Wiederherstellung

1. Dienst stoppen: `nssm stop Haushaltsfinanz`
2. `db\finanzen.db` durch Backup-Datei ersetzen
3. `data\belege\` durch gesicherten Ordner ersetzen (falls vorhanden)
4. Dienst starten: `nssm start Haushaltsfinanz`
5. Health-Check: `Invoke-RestMethod http://localhost:8000/api/health`

---

## PWA-Installation (Smartphone/PC)

1. App im Browser öffnen: `http://<heimnetz-ip>:8000`
2. Browser-Menü → „Zum Startbildschirm hinzufügen" (Android/iOS) oder
   Adressleiste-Symbol → „App installieren" (Chrome Desktop)

---

## Admin-Passwort ändern

1. Einloggen als Administrator
2. Menü → Benutzer → Bearbeiten → neues Passwort setzen

---

## Konfiguration: server.json

Eine Datei für Dienst und Anwendung – Ports, SSL und die Frage, welche Netze als
Heimnetz gelten. Sie liegt im **Einstellungsordner**:

| Umgebung | Pfad |
|---|---|
| Dev | `config\server.json` |
| Prod | `C:\ProgramData\Haushaltsfinanzen\config\server.json` |

```json
{
  "port": 8000,
  "https": { "aktiviert": false, "port": 8443, "zertifikat": "", "schluessel": "" },
  "dev": { "backend_port": 8000, "frontend_port": 5173 },
  "zugriff": {
    "vertrauenswuerdige_netze": ["127.0.0.1/32", "192.168.0.0/16"],
    "vertrauenswuerdige_proxys": [],
    "mfa_immer_erforderlich": false
  }
}
```

Im Produktivbetrieb liefert **ein** uvicorn API und Frontend aus; `port` ist
also der einzige Port, der nach außen zählt. Die Werte unter `dev` gelten nur
für den Entwicklungsbetrieb mit Vite (und steuern die CORS-Freigabe).

Nach einer Änderung genügt `Restart-Service Haushaltsfinanz`. Bei geändertem
Port zusätzlich `install_service.ps1` erneut ausführen, damit Dienst-XML und
Firewall-Regel passen – die Datei selbst bleibt dabei erhalten, sie liegt im
Datenordner.

---

## HTTPS

1. Zertifikat und Schlüssel als PEM-Dateien ablegen (z. B. `C:\certs\haushalt.pem`
   und `C:\certs\haushalt.key`).
2. In `server.json` (Einstellungsordner) unter `https` eintragen und
   `aktiviert` auf `true`.
3. `install_service.ps1` erneut ausführen.

uvicorn liest die Dateien beim Start. Ein Drittanbieter-Tool (acme.sh,
win-acme, Certify) darf sie jederzeit überschreiben – danach genügt ein
Neustart des Dienstes, ein erneutes Einrichten ist nicht nötig. Fehlt das
Zertifikat, startet der Dienst mit einem Hinweis ohne HTTPS statt gar nicht.

---

## Zwei-Faktor-Anmeldung

Der Code wird nur verlangt, wenn die Quell-IP **nicht** in
`zugriff.vertrauenswuerdige_netze` liegt; mit `mfa_immer_erforderlich` gilt er
überall. Einrichtung: Einstellungen → Zwei-Faktor-Anmeldung → QR-Code mit einer
Authenticator-App scannen → Code bestätigen. Dabei entstehen acht
Wiederherstellungscodes, die genau einmal angezeigt werden.

Wichtig bei einem vorgeschalteten Reverse Proxy: `X-Forwarded-For` wird nur
ausgewertet, wenn die Verbindung von einer der unter
`vertrauenswuerdige_proxys` eingetragenen Adressen kommt. Ohne diesen Eintrag
sieht die App nur die Proxy-IP – steht die im Heimnetz, würde jeder Zugriff als
intern gelten. Also entweder den Proxy eintragen **oder**
`mfa_immer_erforderlich` setzen.

Wer von außen kommt und keinen zweiten Faktor eingerichtet hat, wird
abgewiesen. Die Einrichtung muss daher aus dem Heimnetz erfolgen.

---

## Backup auf einen Netzwerkpfad

```powershell
# Zugangsdaten einmalig hinterlegen (Passwort wird DPAPI-verschlüsselt)
backend\.venv\Scripts\python.exe scripts\netzlaufwerk.py --passwort-setzen

# Ziel in backup.json (Einstellungsordner) eintragen, z. B.
#   "ziel_ordner": "\\\\nas\\backups\\haushalt"
backend\.venv\Scripts\python.exe scripts\backup.py
```

Das Passwort kann nur derselbe Windows-Benutzer auf demselben Rechner
entschlüsseln (DPAPI, Scope `CurrentUser`). Der Dienst läuft als `LocalSystem`,
die Backup-Aufgabe als `SYSTEM` – ein unter dem eigenen Konto gesetztes Passwort
ist dort **nicht** entschlüsselbar, und das Backup scheitert stumm. Für ein
Netzwerkziel muss es deshalb als SYSTEM gesetzt werden:

```powershell
psexec -s -i "C:\Haushaltsfinanzen\current\backend\.venv\Scripts\python.exe" "C:\Haushaltsfinanzen\current\scripts\netzlaufwerk.py" --passwort-setzen
```

`register_backup_task.ps1` weist bei einem UNC-Ziel darauf hin. Ist das Ziel nicht erreichbar, bricht das
Skript mit einer Fehlermeldung ab, statt still kein Backup zu schreiben.

---

## Betrieb unter Linux / Docker

Noch nicht als fertiges Image im Repo – der Aufbau im Überblick:

```dockerfile
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr tesseract-ocr-deu libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ /app/backend/
COPY frontend/dist/ /app/frontend/dist/
COPY config/ /app/config/
WORKDIR /app/backend
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Zu beachten:

* **Frontend vorher bauen** (`npm ci && npm run build`); das Image liefert nur
  das fertige `dist/` aus, wie der Dienst unter Windows auch.
* **Volumes** für alles, was bleiben soll: `finanzen.db`, `belege/`,
  `kassenzettel_muster/`, `kontoauszug_muster/`, `logs/`, `config/`.
* **Tesseract-Pfad**: unter Linux liegt die Binärdatei in `/usr/bin/tesseract`.
  Über `FINANZ_TESSERACT_CMD=/usr/bin/tesseract` und
  `FINANZ_TESSDATA_DIR=/usr/share/tesseract-ocr/5/tessdata` setzen – die
  Vorgaben in `backend/app/config.py` zeigen auf Windows-Pfade.
* **Netzwerk-Backup**: DPAPI gibt es unter Linux nicht. Die Freigabe dort auf
  dem Host mounten (`cifs`, Zugangsdaten in einer Credentials-Datei) und den
  Mount als Volume durchreichen, statt das Passwort in der App zu halten.
* **Datenbank**: SQLite auf einem Netzlaufwerk ist keine gute Idee – die Datei
  gehört auf lokalen Speicher, das Backup wandert ins Netz.

---

## Erreichbarkeit von außen (DynDNS)

`haushalt.meine-domain.beispiel` funktioniert auch bei täglich wechselnder IP,
wenn der Router den DynDNS-Dienst selbst aktualisiert (Fritzbox:
Internet → Freigaben → DynDNS). Nach der Zwangstrennung meldet er die neue
Adresse; bis alle Auflöser nachziehen, vergehen je nach TTL ein paar Minuten.

Für ein automatisch erneuerbares Zertifikat ist die **DNS-01-Prüfung** der
richtige Weg: Let's Encrypt prüft dabei einen TXT-Eintrag in der Zone, nicht die
Erreichbarkeit auf Port 80. HTTP-01 scheitert, sobald Port 80 geschlossen ist
oder die IP gerade gewechselt hat. Der DNS-Anbieter muss dafür eine API haben,
die das Erneuerungs-Tool bedienen kann.

Voraussetzungen für den Zugriff von außen, der Reihe nach:

1. Portfreigabe im Router auf den PC und den Port aus `server.json`.
2. HTTPS einrichten (siehe oben) – ohne Verschlüsselung gehen Passwörter im
   Klartext durchs Netz.
3. Zwei-Faktor-Anmeldung einrichten, solange man noch im Heimnetz ist; von außen
   ist sie Pflicht.
4. Prüfen, ob die Anmeldung von außen wirklich nach einem Code fragt –
   andernfalls gilt die Verbindung fälschlich als intern (siehe Hinweis zum
   Reverse Proxy oben).

---

## Port ändern

Port in `server.json` setzen und `install_service.ps1` erneut ausführen
(Dienst und Firewall-Regel werden dabei angepasst). Der Parameter `-Port` am
Skript übersteuert die Datei für einen einzelnen Lauf.
