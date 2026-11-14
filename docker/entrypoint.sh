#!/bin/sh
# Einstiegspunkt des Images. Ein Argument entscheidet, was der Container ist:
#
#   app             Die Anwendung (Vorgabe): Saat/Migration, dann uvicorn.
#   backup-daemon   Der Waechter, der das naechtliche Backup ausloest.
#   migrate         Nur Saat/Migration, dann Ende - fuer "docker compose run".
#   shell           Eine Shell im Container, fuer Fehlersuche. Gilt nur fuer
#                   `docker compose run`; `exec` startet das Programm direkt
#                   und braucht darum `docker compose exec app sh`.
#
# Alles andere wird unveraendert ausgefuehrt, damit `docker compose run app
# python scripts/backup.py` weiterhin moeglich bleibt.
set -e

befehl="${1:-app}"

case "$befehl" in
  app)
    python /app/docker/start.py
    # exec: uvicorn uebernimmt die Prozess-ID des Skripts, damit das Signal von
    # `docker stop` bei uvicorn ankommt und nicht bei einer Shell, die es
    # verschluckt. Ein Worker genuegt - SQLite vertraegt genau einen Schreiber,
    # und mehrere Worker haetten ausserdem jeder ihren eigenen Zwischenspeicher
    # fuer die Release-Abfrage.
    #
    # Bewusst OHNE --proxy-headers/--forwarded-allow-ips. Uvicorn wuerde damit
    # request.client.host aus X-Forwarded-For setzen, unabhaengig davon, wer
    # die Verbindung aufgebaut hat. Genau diese Pruefung macht die Anwendung
    # aber selbst und nur fuer eingetragene Proxys (app/server_config.py,
    # quell_ip) - haette uvicorn den Header schon ersetzt, koennte sich jeder
    # per Header als Heimnetz ausgeben und die MFA-Pflicht umgehen. Der
    # Reverse-Proxy wird in server.json eingetragen, nicht hier.
    exec python -m uvicorn app.main:app \
      --app-dir /app/backend \
      --host 0.0.0.0 \
      --port 8000 \
      --workers 1
    ;;
  backup-daemon)
    exec python /app/docker/backup_daemon.py
    ;;
  migrate)
    exec python /app/docker/start.py
    ;;
  shell)
    exec /bin/sh
    ;;
  *)
    exec "$@"
    ;;
esac
