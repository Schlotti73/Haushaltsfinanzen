# Betrieb im Container

Die App gibt es bei jedem Release auf zwei Wegen mit **derselben
Versionsnummer**: als Windows-Paket (siehe [`betrieb.md`](betrieb.md)) und als
Container-Image. Dieses Dokument beschreibt den zweiten Weg.

Die Zuordnung zum Windows-Konzept in einem Satz: **das Image ist der
Versionsordner, der Tag ist die Version, `docker compose pull` ist das Update
und der alte Tag ist der Rollback.** Die Entscheidungen dahinter stehen in
[`release-paket.md`](release-paket.md); sie gelten hier unverändert, nur mit
anderen Werkzeugen.

---

## Installation

```bash
mkdir -p ~/docker/haushaltsfinanzen/daten
cd ~/docker/haushaltsfinanzen
```

`compose.yaml` anlegen (Vorlage: `docker/compose.yaml` im Repository):

```yaml
services:
  app:
    image: ghcr.io/schlotti73/haushaltsfinanz:${TAG:-latest}
    container_name: haushaltsfinanz
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    environment:
      TZ: ${TZ:-Europe/Berlin}
      FINANZ_SECRET_KEY: ${FINANZ_SECRET_KEY:?FINANZ_SECRET_KEY fehlt}
    volumes:
      - ./daten:/daten
    ports:
      - "${PORT:-8000}:8000"

  backup:
    image: ghcr.io/schlotti73/haushaltsfinanz:${TAG:-latest}
    container_name: haushaltsfinanz-backup
    restart: unless-stopped
    user: "${PUID:-1000}:${PGID:-1000}"
    command: ["backup-daemon"]
    environment:
      TZ: ${TZ:-Europe/Berlin}
      FINANZ_SECRET_KEY: ${FINANZ_SECRET_KEY:?FINANZ_SECRET_KEY fehlt}
    volumes:
      - ./daten:/daten
    depends_on:
      - app
```

`.env` daneben (Vorlage: `docker/.env.beispiel`):

```bash
printf 'FINANZ_SECRET_KEY=%s\nTAG=latest\nPORT=8000\nTZ=Europe/Berlin\nPUID=%s\nPGID=%s\n' "$(openssl rand -hex 32)" "$(id -u)" "$(id -g)" > .env
```

Starten und das Anmeldepasswort abholen:

```bash
docker compose up -d
```

```bash
docker compose logs app | grep -A4 "Erster Start"
```

Das Passwort steht **genau einmal** im Log und wird danach nirgends mehr
abgelegt – in der Datenbank liegt nur der bcrypt-Hash. Es ist zufällig
erzeugt: ein Vorgabewert in der `.env` wäre der schwächste Punkt einer
Anwendung, die sonst MFA und Netzbeschränkung mitbringt, und würde
erfahrungsgemäß nie geändert. Wer die Anlage trotzdem steuern will, setzt
`FINANZ_ADMIN_BENUTZER` und `FINANZ_ADMIN_PASSWORT` – sie wirken nur, solange
noch kein Benutzer existiert.

Die App läuft danach auf `http://<server>:8000`.

---

## Was wo liegt

```
~/docker/haushaltsfinanzen/
  compose.yaml   .env          <- gehören dem Betreiber, überleben jedes Update
  daten/  -> /daten            <- das einzige Mount
    config/                    server.json, datenbanken.json, backup.json, update.json
    finanzen.db
    databases/                 weitere Datenbanken der Mehrfach-Verwaltung
    belege/ kontoauszuege/ kontoauszug_muster/ kassenzettel_muster/
    backups/  logs/
```

Das Programm steckt im Image unter `/app` und wird nie gemountet. Wer dort
hineinfasst, hat beim nächsten `pull` einen anderen Stand als den, der getestet
wurde – deshalb gibt es den Weg nicht.

Ablagen für weitere Datenbanken (`belege/db-2/` usw.) legt die Anwendung selbst
an; ein zweites Mount braucht es dafür nicht.

---

## Update

```bash
docker compose pull && docker compose up -d
```

Denselben Befehl zeigt die Oberfläche unter *Einstellungen → Programm-Update*,
sobald ein neueres Release vorliegt.

Beim Start vergleicht der Container die Alembic-Revision der Datenbank mit der
des Images:

* **Gleich** – es wird nichts angefasst, auch keine Sicherung geschrieben.
  Sonst lägen nach zehn Neustarts zehn gleiche Dateien im Backup-Ordner.
* **Verschieden** – erst eine Sicherung nach
  `daten/backups/vor-<version>-<zeit>.db`, dann die Migration. Das ist die
  Windows-Zusage „keine Migration ohne Sicherung", hier vom Containerstart
  eingelöst statt von `update.ps1`.
* **Die Datenbank kennt Revisionen, die das Image nicht kennt** – dann ist die
  Datenbank neuer als das Programm. Der Container bricht ab und sagt, was zu
  tun ist (siehe Rollback). Er migriert nicht und läuft auch nicht weiter.

Die Versionsnummer im Namen der Sicherung ist die **alte**: `vor-v1.4.2-….db`
ist der Stand, mit dem v1.4.2 lief.

---

## Rollback

Code und Datenbank gehören zusammen – die `downgrade()`-Funktionen der
Migrationen sind als Rückweg untauglich ([`release-paket.md`](release-paket.md)
begründet das ausführlich). Ein Rollback legt deshalb **beides** zurück.

Container anhalten:

```bash
docker compose down
```

Passende Sicherung heraussuchen:

```bash
ls daten/backups/vor-*
```

Datenbank zurücklegen (die aktuelle vorher beiseitelegen):

```bash
cp daten/finanzen.db daten/finanzen.db.alt && cp daten/backups/vor-v1.4.2-2026-11-13_18-02.db daten/finanzen.db
```

Alten Tag in der `.env` eintragen und starten:

```bash
sed -i 's/^TAG=.*/TAG=v1.4.2/' .env && docker compose up -d
```

Hat das Update das Schema nicht angefasst (reines Fehlerbehebungs-Release),
liegt gar keine Sicherung vor – dann genügt der letzte Schritt und der Rollback
ist verlustfrei.

---

## Backup

Das nächtliche Backup löst der Container `backup` aus; er liest dieselbe
`config/backup.json`, die in der Oberfläche unter *Einstellungen → Backup*
steht. `aktiviert`, `uhrzeit` und `behalten` wirken also unmittelbar, ohne
Neustart. Gesichert werden Datenbank **und** alle vier Datei-Ablagen in einem
ZIP – die Datenbank allein genügt nicht, sonst zeigte nach einem Restore jeder
Beleg ins Leere.

```bash
docker compose logs backup
```

```bash
docker compose exec app python scripts/backup.py
```

Der Zielordner ist ein Pfad **im Container**; leer bedeutet `/daten/backups`.
Soll die Sicherung auf ein NAS, mountet der Host es unterhalb von `daten/`. Ein
Pfad außerhalb von `/daten` liegt im Container und ist beim nächsten `up -d`
weg.

---

## Zugriff von außen und MFA

Die Anwendung verlangt einen zweiten Faktor, sobald eine Anmeldung **nicht**
aus dem Heimnetz kommt. Welche Netze das sind, steht in
`daten/config/server.json` unter `zugriff.vertrauenswuerdige_netze`.

Das funktioniert im Container wie unter Windows: Docker leitet veröffentlichte
Ports per iptables-DNAT weiter und **erhält dabei die Absenderadresse**. Ein
Zugriff aus dem LAN erscheint als `192.168.x.y`, einer aus dem Internet mit
seiner öffentlichen Adresse – die MFA-Pflicht greift also dort, wo sie soll.
(Nur Verbindungen vom Host selbst laufen über den Userland-Proxy und erscheinen
als `127.0.0.1`.)

Ein Unterschied zu Windows bleibt: **`172.16.0.0/12` fehlt in der Vorgabe.**
Genau in diesem Bereich legt Docker seine Container-Netze an. Stünde er drin,
gälte ein Reverse-Proxy im Nachbarcontainer als Heimnetz – und damit jeder, der
durch ihn kommt, ohne dass es jemand entschieden hätte.

Voreingestellt sind daher `127.0.0.1/32`, `192.168.0.0/16` und `10.0.0.0/8`.
Liegt das eigene Heimnetz in `172.16.x` bis `172.31.x`, gehört es von Hand
eingetragen.

### Hinter einem Reverse-Proxy

Dann ist die Gegenstelle der Proxy, nicht der Mensch. Damit die Anwendung die
echte Adresse wieder sieht, gehört der Proxy unter
`vertrauenswuerdige_proxys` – erst dann wertet sie `X-Forwarded-For` aus:

```json
{
  "zugriff": {
    "vertrauenswuerdige_proxys": ["172.18.0.0/16"],
    "vertrauenswuerdige_netze": ["192.168.178.0/24"]
  }
}
```

Die Adresse des Proxy-Netzes nennt
`docker network inspect haushaltsfinanzen_default`. Danach den Container neu
starten – `server.json` wird beim Start gelesen.

Caddy davor:

```
finanzen.example.net {
    reverse_proxy haushaltsfinanz:8000
}
```

HTTPS gehört in diesem Aufbau zum Proxy, nicht in die App: die `https`-Angaben
in `server.json` bedient der Windows-Dienst, nicht der Container.

### Ausgesperrt

Gilt kein Netz als Heimnetz, verlangt **jede** Anmeldung einen zweiten Faktor –
einrichten lässt der sich aber nur nach einer Anmeldung. Wer die Liste leert,
sperrt sich also aus. Heraus führt nur die Datei:

```bash
nano daten/config/server.json
```

Das eigene Netz unter `vertrauenswuerdige_netze` eintragen, dann:

```bash
docker compose restart app
```

---

## Fehlersuche

```bash
docker compose logs -f app
```

```bash
docker compose exec app sh
```

(`exec` geht am Entrypoint vorbei und startet das Programm direkt – deshalb
hier `sh` und nicht das Stichwort `shell`, das nur bei `docker compose run`
wirkt.)

```bash
docker compose run --rm app migrate
```

**Container startet nicht, Log nennt eine unbekannte Revision** – die Datenbank
ist neuer als das Image. Siehe Rollback.

**„Permission denied" beim Schreiben in `/daten`** – der Ordner gehört einem
anderen Benutzer als dem, unter dem der Container läuft:

```bash
sudo chown -R $(id -u):$(id -g) daten
```

**OCR findet nichts** – Tesseract steckt im Image, die Sprachdaten liegen aber
unter `backend/tessdata` und nicht im Debian-Pfad. `tesseract --list-langs`
zeigt sie deshalb **nicht** an, das ist kein Fehler. Richtig prüft man auf dem
Weg, den die Anwendung selbst geht – dasselbe Skript, das auch der Rauchtest
benutzt:

```bash
docker compose exec -T app python - < docker/ocr_pruefung.py
```

Erwartet wird `deu.traineddata eng.traineddata`. Die beiden Dateien lädt der
Bau selbst (Stufe 2 in `docker/Dockerfile`, Fassung und Prüfsummen stehen in
[`docker/tessdata_laden.py`](../docker/tessdata_laden.py)). Meldet das Skript
sie als fehlend, stammt das Image aus einem Bau **vor** dieser Änderung –
Images bis einschließlich `v0.2.5` haben keine Sprachdaten, weil
`backend/tessdata` nicht im Repository liegt und der Workflow aus dem
Repository baut. Abhilfe: neu bauen.

---

## Einmalig am Paket: Sichtbarkeit und Schreibrecht

Zwei Einstellungen am ghcr-Paket, die kein Workflow setzen kann.

**Sichtbarkeit.** Ein neues ghcr-Paket erbt die Sichtbarkeit des Repositories,
aus dem es gepusht wurde – und das war anfangs das private
Entwicklungs-Repository. Beim allerersten Release ist das Image deshalb privat,
und ein fremder `docker pull` scheitert mit `unauthorized`:

> github.com/users/<Konto>/packages/container/haushaltsfinanz/settings
> → *Danger Zone* → *Change visibility* → **Public**

**Schreibrecht des bauenden Repositories.** Gepusht wird das Image aus
`Schlotti73/Haushaltsfinanzen` (siehe
[`veroeffentlichen.md`](veroeffentlichen.md)), während das Paket noch dem
Repository gehört, aus dem es ursprünglich kam. Fehlt das neue in der Liste,
scheitert der Push mit `permission_denied` – und zwar mitten im Release,
nachdem der Quellstand schon draußen ist:

> …/packages/container/haushaltsfinanz/settings
> → *Manage Actions access* → *Add repository* → `Haushaltsfinanzen`, Rolle **Write**

Zwei Stolperstellen auf dieser Seite: Direkt unter *Manage Actions access*
steht das gleich aussehende *Manage Codespaces access* – ein Eintrag dort
hilft dem Workflow nichts. Und ein frisch hinzugefügtes Repository bekommt
die Rolle *Read*; sie muss von Hand auf *Write* gestellt werden. Beides endet
im selben Fehler: `permission_denied: write_package`.

Nachsehen lässt sich das, ohne auf ein Release zu warten: im öffentlichen
Repository den Workflow *Docker-Image* von Hand starten (*Actions* → *Run
workflow*) und „veroeffentlichen" auf `true` setzen. Das pusht ein
`dev-<datum>-<sha>`-Image und lässt `latest` unberührt.

Die Sichtbarkeit prüft man nur unangemeldet – ein `docker logout ghcr.io`
vorweg, sonst zieht der eigene Rechner das Image über die eigenen Rechte und
die Antwort sagt nichts aus:

```bash
docker logout ghcr.io && docker pull ghcr.io/schlotti73/haushaltsfinanz:latest
```

Dasselbe gilt für die Überlegung aus `update.py`: Die Versionsprüfung fragt ein
öffentliches Repository, damit sie ohne Zugangsdaten auskommt. Ein privates
Image würde dieselbe Zusage wieder einreißen – die Installation sähe das
Update, könnte es aber nicht holen.

---

## Für Entwickler: Image bauen und testen

```bash
docker build -f docker/Dockerfile -t haushaltsfinanz:test --build-arg VERSION=v0.0.0-test .
```

```bash
./docker/rauchtest.sh haushaltsfinanz:test
```

Der Rauchtest startet das Image mit leerem Datenordner, wartet auf
`/api/health`, prüft Saat, Ablagen und Oberfläche und startet den Container
anschließend neu – der Neustart darf weder migrieren noch ein zweites Passwort
erzeugen. Denselben Test läuft `.github/workflows/docker.yml` vor jedem Push
nach ghcr.io.

Dieser Workflow läuft in **beiden** Repositories, denn er liegt im Baum und
der Baum wird veröffentlicht. Ein Versions-Tag im privaten Repository lässt ihn
bauen und rauchtesten, aber nichts pushen; gepusht wird nur aus
`Schlotti73/Haushaltsfinanzen`, wohin `veroeffentlichen.ps1` den Tag mitnimmt.
Das Image stammt damit aus dem Quellstand, der öffentlich einsehbar ist – und
der Lauf im privaten Repository ist der Torwächter davor.

Was ein Workflow nicht prüfen kann, ist das **Update einer bestehenden
Installation**: Revisionsvergleich, Sicherung, Migration. Dafür gibt es auf dem
Prüfstand eine dauerhafte Installation mit einer älteren Version, die vor jedem
Release einmal hochgezogen wird.

Damit der Prüfstand das auch wirklich prüft, muss seine Datenbank **hinter dem
Image zurückliegen**. Wandert sie mit jedem Release mit, meldet der Start brav
„Schema aktuell", der Test sieht grün aus und hat den Migrationsweg kein
einziges Mal angefasst. Vor dem Test daher eine Revision zurücksetzen:

```bash
docker compose exec -w /app/backend app python -m alembic downgrade -1
```

Erwartet werden danach drei Zeilen im Startprotokoll – Abweichung erkannt,
Sicherung angelegt, Migration abgeschlossen – und eine Datei
`daten/backups/vor-<version>-<zeit>.db`. Die Sicherung muss die *alte* Revision
tragen; steht dort schon die neue, wurde zu spät gesichert und der
Rückkehrpunkt wäre wertlos.
