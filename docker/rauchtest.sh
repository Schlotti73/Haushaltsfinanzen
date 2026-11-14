#!/bin/sh
# Prueft, ob ein gebautes Image wirklich anlaeuft - bevor es jemand bekommt.
#
#   ./docker/rauchtest.sh ghcr.io/schlotti73/haushaltsfinanz:v1.5.0
#
# Geprueft wird der Weg, den jeder neue Nutzer als erstes geht: leerer
# Datenordner, Container starten, anmelden koennen. Genau dieser Weg laesst
# sich auf dem Entwicklungsrechner nie versehentlich mittesten, weil dort
# immer schon eine Datenbank liegt.
#
# Der zweite Teil ist der Neustart: er muss das Schema in Ruhe lassen und darf
# kein zweites Passwort erfinden. Das ist die Zusage aus docs/docker.md -
# gesichert und migriert wird nur, wenn die Revision wirklich abweicht.
set -e

IMAGE="${1:?Aufruf: rauchtest.sh <image>}"
NAME="rauchtest-$$"
DATEN="$(mktemp -d)"
PORT="${RAUCHTEST_PORT:-18099}"

# Veroeffentlicht wird auf der LAN-Adresse des Hosts, nicht auf 127.0.0.1.
# Grund: bei einer Loopback-Veroeffentlichung schiebt Docker die Verbindung
# durch den Userland-Proxy, und im Container kommt 172.17.0.1 an - das
# Bridge-Gateway, das im Container bewusst NICHT als Heimnetz gilt. Ueber die
# LAN-Adresse bleibt die echte Absenderadresse erhalten; das ist der Weg, den
# ein Nutzer nimmt, und nur so sagt der Anmeldetest unten etwas aus.
HOST_IP=$(hostname -I 2>/dev/null | tr ' ' '\n' | grep -E '^(192\.168\.|10\.)' | head -1)
if [ -z "$HOST_IP" ]; then
  HOST_IP=127.0.0.1
  echo "HINWEIS: keine LAN-Adresse gefunden - der Anmeldetest wird uebersprungen."
fi
ZIEL="http://$HOST_IP:$PORT"

aufraeumen() {
  docker rm -f "$NAME" >/dev/null 2>&1 || true
  rm -rf "$DATEN"
}
trap aufraeumen EXIT

fehler() {
  echo "FEHLGESCHLAGEN: $1"
  echo "--- Log ---------------------------------------------------"
  docker logs "$NAME" 2>&1 | tail -40
  exit 1
}

echo "Image:        $IMAGE"
echo "Datenordner:  $DATEN (leer)"
echo "Erreichbar:   $ZIEL"

docker run -d --name "$NAME" \
  -u "$(id -u):$(id -g)" \
  -e FINANZ_SECRET_KEY=rauchtest-nur-fuer-diesen-lauf \
  -v "$DATEN:/daten" \
  -p "$HOST_IP:$PORT:8000" \
  "$IMAGE" >/dev/null

echo "Warte auf /api/health …"
i=0
while [ "$i" -lt 90 ]; do
  if curl -fsS "$ZIEL/api/health" >/dev/null 2>&1; then
    break
  fi
  # Ein abgestuerzter Container antwortet nie - das lieber sofort melden, als
  # 90 Sekunden auf etwas zu warten, das nicht mehr laeuft.
  if [ "$(docker inspect -f '{{.State.Running}}' "$NAME")" != "true" ]; then
    fehler "Container laeuft nicht mehr"
  fi
  i=$((i + 1))
  sleep 1
done
[ "$i" -lt 90 ] || fehler "/api/health antwortet nicht"
echo "  ok nach ${i}s"

echo "Pruefe Erststart-Saat …"
docker logs "$NAME" 2>&1 | grep -q "Passwort:" \
  || fehler "Im Log steht kein Anmeldepasswort"

[ -f "$DATEN/finanzen.db" ] || fehler "finanzen.db wurde nicht angelegt"

ANZAHL=$(docker exec "$NAME" python -c \
  "import sqlite3;print(sqlite3.connect('/daten/finanzen.db').execute('select count(*) from kategorien').fetchone()[0])")
[ "$ANZAHL" -gt 0 ] || fehler "Kein Kategorienbaum gesaet"
echo "  ok ($ANZAHL Kategorien, Passwort im Log)"

echo "Pruefe Ablagen …"
for ordner in belege kontoauszuege kontoauszug_muster kassenzettel_muster config; do
  [ -d "$DATEN/$ordner" ] || fehler "Ordner $ordner fehlt"
done
echo "  ok"

# Die Sprachdaten liegen nicht im Repository, der Bau laedt sie (Stufe 2 in
# docker/Dockerfile). Fehlen sie, scheitert nicht der Start, sondern erst die
# erste Texterkennung an einem Kassenzettel - also lange nach dem Release.
# engine.py erzwingt --tessdata-dir, deshalb hilft dann auch das mitgelieferte
# eng des Debian-Pakets nicht: die Erkennung faellt komplett aus.
echo "Pruefe Sprachdaten der Texterkennung …"
SPRACHEN=$(docker exec -i "$NAME" python - < "$(dirname "$0")/ocr_pruefung.py" 2>&1) \
  || fehler "Texterkennung nicht einsatzbereit: $SPRACHEN"
echo "  ok ($SPRACHEN, Probelauf bestanden)"

echo "Pruefe Oberflaeche …"
curl -fsS "$ZIEL/" | grep -qi '<div id="root"' \
  || fehler "Die Startseite liefert kein gebautes Frontend"
curl -fsS "$ZIEL/api/version" | grep -q '"betriebsart":"docker"' \
  || fehler "Die Betriebsart wird nicht als docker gemeldet"
echo "  ok"

# Der Grund fuer diesen Test: eine leere Heimnetz-Liste sperrt jeden aus. Ohne
# Heimnetz verlangt die Anmeldung einen zweiten Faktor, einrichten laesst der
# sich aber nur nach einer Anmeldung - eine geschlossene Schleife, aus der nur
# das Bearbeiten von server.json herausfuehrt. Genau das ist einmal passiert;
# seitdem steht es hier.
if [ "$HOST_IP" != "127.0.0.1" ]; then
  echo "Pruefe Anmeldung aus dem LAN (ohne zweiten Faktor) …"
  PASSWORT=$(docker logs "$NAME" 2>&1 | sed -n 's/.*Passwort:  *\([A-Za-z0-9]*\).*/\1/p' | head -1)
  [ -n "$PASSWORT" ] || fehler "Konnte das Passwort nicht aus dem Log lesen"

  ANTWORT=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$ZIEL/api/auth/login" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"Admin\",\"passwort\":\"$PASSWORT\"}")
  [ "$ANTWORT" = "200" ] \
    || fehler "Anmeldung scheitert mit HTTP $ANTWORT - gilt das LAN nicht als Heimnetz?"
  echo "  ok"
fi

echo "Pruefe Neustart (darf nichts migrieren) …"
docker restart "$NAME" >/dev/null
i=0
while [ "$i" -lt 60 ] && ! curl -fsS "$ZIEL/api/health" >/dev/null 2>&1; do
  i=$((i + 1)); sleep 1
done
[ "$i" -lt 60 ] || fehler "Container kommt nach Neustart nicht hoch"

docker logs "$NAME" 2>&1 | grep -q "Schema aktuell" \
  || fehler "Der Neustart hat das Schema nicht als aktuell erkannt"
[ "$(docker logs "$NAME" 2>&1 | grep -c "Passwort:")" -eq 1 ] \
  || fehler "Der Neustart hat ein zweites Passwort erzeugt"
[ -z "$(ls -A "$DATEN/backups" 2>/dev/null)" ] \
  || fehler "Der Neustart hat ohne Schema-Aenderung eine Sicherung geschrieben"
echo "  ok"

echo
echo "Rauchtest bestanden."
