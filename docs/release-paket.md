# Release-Paket und Prod-Update – Entscheidungen

> **Status: umgesetzt.** Wie Release, Installation, Update und Rollback
> *bedient* werden, steht in [`betrieb.md`](betrieb.md). Dieses Dokument hält
> fest, **warum** es so gebaut ist – damit die Begründungen nicht verloren
> gehen, wenn später etwas daran geändert werden soll.

---

## Ausgangslage

Der Prod-Betrieb lief über einen **Git-Checkout auf dem Zielrechner**:
`install_service.ps1` installierte per winget Python, Node.js und Tesseract,
baute die venv und das Frontend; `update.ps1` machte `git pull` und baute neu.
Parallel existierte `create_prod_zip.ps1`, das ein vorgebautes Paket erzeugte –
das aber **kein Skript installieren oder aktualisieren konnte**. Das Paket war
eine Sackgasse.

Jetzt ist das Paket der einzige Weg. Der Prod-PC braucht **kein Git, kein
Node.js und kein Internet** (außer einmalig für Python und Tesseract per
winget).

---

## Die zehn Entscheidungen

| # | Thema | Entscheidung | Warum |
|---|---|---|---|
| 1 | Bereitstellung | ZIP-Paket | Ein Build, der hier durchlief, kann dort nicht anders ausgehen. Eine Version ist ein archivierbares Artefakt statt „der Stand, den `git pull` gerade zog". |
| 2 | Layout | Programm- und Datenordner getrennt | Beantwortet „was darf das Update überschreiben?" strukturell statt per Pflegeliste: Programmordner = Paket, restlos ersetzbar; Datenordner = unberührt. Keine Ausnahmeliste, keine verwaisten Altdateien. |
| 3 | `config/` | Vorlagen beim Programm, Einstellungen beim Datenordner | Lägen die Vorlagen beim Datenordner, erreichten Verbesserungen am Kategorienbaum oder Mapping den Prod-PC nie – dort bliebe die Fassung der Erstinstallation liegen. |
| 4 | Update-Struktur | Versionsordner + `current`-Junction | Rollback in Sekunden statt Neuinstallation; Ausfallzeit von Minuten auf Sekunden; keine Dateisperren, weil der neue Ordner frisch ist; ein fehlgeschlagenes Update hinterlässt keine Trümmer. |
| 5 | Python-Pakete | Wheels im Paket, venv pro Version | Mit Versionsordnern entsteht die venv bei *jedem* Update – aus dem Netz wären das jedes Mal ~270 MB. Außerdem reproduzierbar: kein PyPI, kein Proxy, keine transitive Lücke. |
| 6 | Artefakt | ZIP + `setup.cmd` | Der Gewinn liegt nicht in der Hülle. Die Installationslogik ist nicht installer-förmig (winget, interaktive Admin-Anlage, venv-Prüfung), und eine unsignierte Setup.exe ist durch SmartScreen unbequemer als ein ZIP. |
| 7 | Rollback | Pflicht-Backup, Junction **und** DB zurück | Siehe „Warum Code und Datenbank untrennbar sind". |
| 8 | Migration | nur das Update-Skript | Siehe „Warum nur das Update-Skript migrieren darf". |
| 9 | Transport | Pfad-Parameter `-Paket <zip>` | Der Transport ist kein Architekturentscheid, sondern ein Argument: USB, Freigabe und lokaler Ordner teilen einen Codeweg. Eine feste Quelle auf dem Dev-PC fiele aus, wenn der aus ist. |
| 10 | Version | Git-Tag | Ein Rollback kann bedeuten, eine alte Version *nachzubauen*. Mit Tag ist das `git checkout v1.4.2`; mit einer gepflegten Datei müsste man den Commit raten. Und ein Tag lässt sich pro Commit nur einmal vergeben – Git wehrt sich gegen Vergessen. |

### Verworfen

* **Git-Checkout behalten** – ließe den Widerspruch zum ZIP-Skript stehen.
* **Beide Wege parallel** – man müsste beide testen; genau daran ist es vorher
  gescheitert.
* **Fertige venv ins Paket legen** – `pyvenv.cfg` zeigt auf
  `C:\Users\<name>\AppData\Local\Programs\Python\Python311`. Auf einem anderen
  Rechner existiert der Pfad nicht, die venv findet ihren Interpreter nicht.
* **venv zentral statt pro Version** – ein Code-Rollback liefe dann mit den
  *neuen* Paketen, also in einer nie getesteten Kombination. Der Rollback aus
  Entscheidung 4 wäre nur halb echt.
* **pip aus dem Internet** – jedes Update, auch ein Ein-Zeilen-Fix, zöge ~270 MB
  und hinge an PyPI, Proxy und Leitung.

---

## Warum Code und Datenbank untrennbar sind

1. Die Anwendung migrierte bei **jedem Start** selbst:
   `lifespan` → `_init_db()` → `init_db_schema()`.
2. `init_db_schema` ruft bei bekannter DB `command.upgrade(cfg, "head")`.
3. „head" und die bekannten Revisionen kommen aus `backend/alembic/versions/` –
   also **aus dem Versionsordner**.
4. Nach einem Code-Rollback steht die DB auf der Revision der neueren Version.
   Alembic findet sie nicht und wirft `Can't locate revision identified by '…'`.
5. Der Fehler fliegt im `lifespan` → uvicorn startet nicht → WinSW versucht per
   `onfailure action="restart" delay="10 sec"` endlos neu.

Die `downgrade()`-Funktionen sind als Rückweg untauglich: destruktiv
(`op.drop_column('buchungen', 'verwendungszweck')`,
`op.drop_table('kontoauszug_muster')`, `op.drop_table('sondertilgung')`) und
teils absichtlich unvollständig – `c3d4e5f6a7b8` hat `pass`, `i9d0e1f2a3b4`
notiert „Spalten in konten werden bewusst belassen (additive Migration)".

Deshalb: **Rollback legt Junction und Datenbank gemeinsam zurück.** Hat das
Update das Schema nicht angefasst (Patch-Release), erkennt `rollback.ps1` das an
den notierten Revisionen und bleibt bei der Datenbank – dann ist der Rollback
verlustfrei.

---

## Warum nur das Update-Skript migrieren darf

Vorher migrierten **zwei** Stellen unabhängig: `update.ps1` über
`seed_admin.py`, und der Dienst bei jedem Start.

* Mit Versionsordnern wird die neue Version aufgebaut, **während die alte
  läuft**. Migrierte dabei etwas, sähe der laufende alte Code mitten im Betrieb
  ein Schema, das er nicht kennt.
* Eine Selbstmigration macht **jeden** Neustart zu einem möglichen
  Schema-Änderer ohne Backup – auch den Neustart nach dem Zurückspielen einer
  alten Datenbank. Die Kopie, die das Sicherheitsnetz war, wäre danach
  verändert.
* Ein Migrationsfehler hätte beim Dienst-Start keinen guten Ort: WinSW startet
  endlos neu, der Health-Check meldet nur „fehlgeschlagen", die Ursache steht im
  Log. Bricht dagegen die Migration im Update ab, ist die Junction noch nicht
  umgelegt – die alte Version läuft weiter, und es braucht gar keinen Rollback.

Umsetzung: `FINANZ_AUTO_MIGRATE` (Dev `1`, Prod `0`), geprüft in
[`app/pfade.py`](../backend/app/pfade.py), ausgewertet in
[`app/main.py`](../backend/app/main.py); die Prüfung selbst ist
`pruefe_schema()` in [`app/db_init.py`](../backend/app/db_init.py). Sie
unterscheidet drei Fälle und nennt in jedem die Abhilfe: fehlende Datenbank,
ausstehende Migrationen, und eine Revision, die diese Programmversion nicht
kennt (= Code zurückgerollt, Datenbank nicht).

---

## Was umgebaut wurde

### Neu

| Datei | Aufgabe |
|---|---|
| [`backend/app/pfade.py`](../backend/app/pfade.py) | Zentrale Auflösung von Programm-, Daten-, Einstellungs- und Vorlagenordner; Version und Migrations-Schalter |
| [`scripts/prod/pfade.ps1`](../scripts/prod/pfade.ps1) | Dasselbe für die Skripte, plus Junction-Hilfen und Python-Suche |
| [`scripts/prod/setup.cmd`](../scripts/prod/setup.cmd) | Startpunkt nach dem Entpacken; entsperrt die Skripte (Mark-of-the-Web) |
| [`scripts/prod/rollback.ps1`](../scripts/prod/rollback.ps1) | Junction und Datenbank gemeinsam zurücklegen |

### Geändert

| Datei | Änderung |
|---|---|
| `create_prod_zip.ps1` | Sauberkeitsprüfung · harter Abbruch ohne gebautes Frontend · Migrationen zählen · Versionsabfrage mit Empfehlung · Tag anlegen · `pip download --only-binary` · `config-vorlagen` statt `config` · `netzlaufwerk.py` ergänzt |
| `install_service.ps1` | Installiert aus dem Paket nach `versionen\<v>\` · kein Node.js mehr · Datenordner · venv offline aus `wheels\` · Junction · `FINANZ_*` in der Dienst-XML · Datenordner in der Registry |
| `update.ps1` | Von `git pull` + `npm build` auf Paket-Entpacken, Pflicht-Backup (samt `-wal`/`-shm`), explizite Migration, Junction-Umschaltung, `letztes-update.json`, Aufräumen · Parametersätze `-Paket` / `-Ordner` / `-AusUpdates` · frischt `<Programm>\update.cmd` auf |
| `update.cmd` (neu) | Doppelklick-Starter: erhöht sich selbst, entsperrt Mark-of-the-Web, wählt die Quelle (entpacktes Paket, ZIP aus `<Daten>\updates\`, mitgegebener Pfad) und hält das Fenster offen. Im ZIP-Stamm erzeugt `create_prod_zip.ps1` einen Durchruf, im Programmstamm erzeugen Installer und Update einen, der auf `current\` zeigt |
| `uninstall_service.ps1` | Programmordner und Junction entfernen, **Datenordner behalten** und benennen |
| `register_backup_task.ps1` | Generierter Wrapper `dienst\backup.cmd`, der `FINANZ_DATEN_DIR` setzt und auf `current\` zeigt |
| `status.ps1` | Version, aktive Junction, letztes Update samt Rollback-Kosten, Logs aus dem Datenordner |
| `db_init.py`, `main.py` | `pruefe_schema()`; migrieren nur, wenn erlaubt; Version aus der `VERSION`-Datei |
| `server_config.py`, `db_registry.py`, `routers/einstellungen.py`, `routers/datenbanken.py`, `config.py` | Pfade über `app.pfade` statt relativ zum Code |
| `scripts/backup.py`, `netzlaufwerk.py`, `init_db.py` | ebenso |
| `alembic.ini`, `alembic/env.py` | Keine fest codierte Datenbank mehr; `env.py` nimmt `-x url=…`, sonst `app.config` |
| `requirements.txt` | `pillow` explizit (wurde direkt genutzt, kam nur transitiv mit) |
| `config/` → `config-vorlagen/` | `kategorien.json`, `kategorien_minimal.json`, `mapping.json` verschoben |

---

## Nebenbefunde

Beim Durchgehen des Ist-Zustands gefunden. Alle erledigt, bis auf Nummer 10.

| | Befund | Status |
|---|---|---|
| 1 | `create_prod_zip.ps1` brach bei fehlendem Frontend **nicht** ab, es warnte nur – das Paket hätte kein Frontend gehabt | behoben, harter Abbruch |
| 1b | Der geprüfte Ordner `frontend\dist` entsteht beim Build überhaupt nicht: `vite.config.js` baut nach `backend\static`, und `main.py` suchte das Frontend ebenfalls unter `frontend/dist` – **es wurde nie ausgeliefert** | behoben, alle drei Stellen auf `backend/static` |
| 2 | `config/` im Paket hätte die Prod-Konfiguration mit absoluten `D:\`-Pfaden des Entwicklungsrechners überschrieben | behoben, Aufteilung |
| 3 | `datenbanken.json` gewinnt über `FINANZ_DB_PATH` ([`config.py`](../backend/app/config.py)) | bewusst so; die Datei wird bei der Installation **nicht** vorab geschrieben, damit `FINANZ_DATEN_DIR` greift |
| 4 | `pyvenv.cfg` zeigt auf ein Benutzerprofil – eine mitgelieferte venv wäre auf dem Zielrechner tot | gelöst über Wheels |
| 5 | DPAPI verschlüsselt unter `CurrentUser`, Dienst und Backup-Aufgabe laufen als `SYSTEM` – ein Netzwerk-Backup scheitert sonst stumm | dokumentiert, `register_backup_task.ps1` warnt bei UNC-Zielen |
| 6 | `Pillow` wird direkt genutzt, stand nur transitiv über `pdfplumber` in den Abhängigkeiten | in `requirements.txt` aufgenommen |
| 7 | Mark-of-the-Web blockt `.ps1` aus einem heruntergeladenen ZIP | `setup.cmd` entsperrt, `update.ps1` ebenfalls |
| 8 | `alembic.ini` hatte eine fest codierte `sqlalchemy.url` auf `finanzen.db` – ein direkter `alembic`-Aufruf liefe im neuen Layout gegen die falsche Datei | behoben, `env.py` fällt auf `app.config` zurück |
| 9 | `routers/datenbanken.py` legte neue Datenbanken unter `<Code>\databases\` an | jetzt im Datenordner |
| 10 | `pandas` (63 MB) liegt in der venv, wird nirgends importiert und steht nicht in `requirements.txt` | **offen** – Überrest im Entwicklungs-venv; eine frisch gebaute venv ist dadurch ~270 statt 340 MB, das Paket enthält es ohnehin nicht |
| 12 | `exit $LASTEXITCODE` nach `Start-Process -Wait` gab in allen vier selbst erhöhenden Skripten **nicht** den Code des erhöhten Prozesses zurück – ein gescheitertes Setup meldete nach außen Erfolg, und `setup.cmd` schrieb „Setup beendet." | behoben, `-PassThru` + `.ExitCode` in `install_service.ps1`, `update.ps1`, `rollback.ps1`, `uninstall_service.ps1` |
| 11 | Alle `.ps1` lagen ohne BOM vor und nutzten `-SkipCertificateCheck`; unter Windows PowerShell 5.1 auf dem Ziel-PC scheiterte `setup.cmd` schon am Parser | behoben, siehe unten; `create_prod_zip.ps1` prüft das BOM vor jedem Paketbau |

---

## Drei Dinge, die beim Ändern leicht übersehen werden

* **Der Dienst-Wrapper liegt außerhalb der Versionsordner** (`dienst\`), und
  seine XML zeigt auf `current\`. Zeigte sie auf einen Versionsordner, müsste
  sie bei jedem Update neu geschrieben werden – und ein Rollback wäre kein
  Junction-Tausch mehr. Dasselbe gilt für die Backup-Aufgabe.
* **Eine Junction wird mit `rmdir` entfernt, nie mit `Remove-Item -Recurse`.**
  Letzteres folgt je nach PowerShell-Fassung dem Reparse-Point und löscht den
  *Inhalt* des Zielordners – also die Version, auf die gerade gezeigt wird.
  `SetzeJunction` in [`pfade.ps1`](../scripts/prod/pfade.ps1) macht es richtig.
* **Die Zielmaschine hat Windows PowerShell 5.1, nicht `pwsh` 7.** Daraus
  folgt zweierlei, und beides fällt beim Entwickeln nie auf, weil hier `pwsh`
  läuft:
  * Jede `.ps1` braucht ein **UTF-8-BOM**. Ohne BOM liest 5.1 die Datei als
    Windows-1252; aus den Rahmenzeichen der Abschnittsüberschriften wird dabei
    unter anderem ein `”`, und das beendet für PowerShell eine Zeichenkette.
    Das Skript stirbt beim Parsen, bevor eine einzige Zeile läuft.
    `create_prod_zip.ps1` prüft das und baut sonst kein Paket.
  * Cmdlet-Parameter aus PowerShell 7 fehlen. `-SkipCertificateCheck` etwa gibt
    es nicht; dafür steht `HealthAbfrage` in `pfade.ps1`, das unter 5.1 über
    `ServicePointManager` geht. Neue Skriptstellen gegen 5.1 prüfen, nicht nur
    gegen die hiesige Shell.
