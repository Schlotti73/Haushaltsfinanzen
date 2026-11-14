# Haushaltsfinanz-App als Container.
#
# Drei Stufen, damit weder Node noch ein Paketindex im Endbild landen: die
# erste baut das Frontend nach backend/static (so legt es
# frontend/vite.config.js fest, und genau dort sucht backend/app/main.py), die
# zweite holt die Tesseract-Sprachdaten, die dritte nimmt nur die beiden
# Ergebnisse mit.
#
# Das Image traegt das Programm, der Tag traegt die Version - zusammen sind sie
# das, was auf Windows der Versionsordner mit der current-Junction ist. Daten
# liegen ausschliesslich unter /daten (FINANZ_DATEN_DIR) und werden nie
# mitgebaut. Siehe docs/docker.md.

# ── Stufe 1: Frontend ───────────────────────────────────────────────────────
FROM node:22-slim AS frontend

WORKDIR /bau

# Erst die Abhaengigkeiten, dann der Quelltext: so bleibt die npm-Schicht im
# Cache, solange sich package-lock.json nicht aendert.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# vite schreibt nach ../backend/static - der Ordner liegt ausserhalb von /bau,
# deshalb muss er existieren.
RUN mkdir -p /backend/static && npm run build


# ── Stufe 2: Sprachdaten der Texterkennung ────────────────────────────
FROM python:3.12-slim AS sprachdaten

# Eigene Stufe, damit die Laufzeit kein Werkzeug zum Herunterladen braucht.
# Das Skript nennt Fassung und Pruefsummen und bricht bei Abweichung ab; das
# Basisimage bringt alles mit, was es braucht (urllib, ca-certificates).
COPY docker/tessdata_laden.py /tessdata_laden.py
RUN python /tessdata_laden.py /tessdata


# ── Stufe 3: Laufzeit ───────────────────────────────────────────────────────
FROM python:3.12-slim AS laufzeit

# tesseract-ocr: nur das Programm. Die Sprachdaten deu/eng kommen aus Stufe 2
#   und liegen unter backend/tessdata, wo settings.tessdata_dir sie erwartet -
#   die apt-Sprachpakete waeren eine zweite, abweichende Quelle.
# libglib2.0-0: von opencv-python-headless gebraucht.
# tini: ein Init, das Signale weiterreicht und Zombies einsammelt. Ohne das
#   laeuft uvicorn als PID 1 und `docker stop` wartet jedes Mal zehn Sekunden.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr \
      libglib2.0-0 \
      tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Programmteile. Bewusst einzeln statt "COPY . ." - ins Image gehoeren weder
# die Entwicklungs-Datenbanken noch die Release-ZIPs aus dem Projektstamm.
COPY backend/ ./backend/
COPY scripts/ ./scripts/
COPY db/ ./db/
COPY config-vorlagen/ ./config-vorlagen/
COPY docker/ ./docker/

# Das gebaute Frontend aus Stufe 1. Es ueberschreibt ein eventuell
# mitkopiertes backend/static aus dem Arbeitsverzeichnis.
COPY --from=frontend /backend/static ./backend/static

# Die Sprachdaten aus Stufe 2. backend/tessdata ist in .dockerignore
# ausgeschlossen, damit hier immer die geladenen Dateien liegen und nicht,
# was auf dem bauenden Rechner zufaellig im Ordner lag.
COPY --from=sprachdaten /tessdata ./backend/tessdata

# Die Versionsnummer kommt vom Bau (git describe --tags) und landet in der
# VERSION-Datei, die app.pfade.version() liest. Ohne sie meldet die Anwendung
# "dev" - richtig in der Entwicklung, falsch in einem veroeffentlichten Image.
ARG VERSION=dev
RUN printf '%s' "$VERSION" > /app/VERSION

RUN chmod +x /app/docker/entrypoint.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/backend \
    FINANZ_BETRIEBSART=docker \
    FINANZ_DATEN_DIR=/daten \
    FINANZ_TESSERACT_CMD=/usr/bin/tesseract \
    FINANZ_AUTO_MIGRATE=0

# FINANZ_AUTO_MIGRATE=0 ist Absicht: migrieren darf allein der Entrypoint, und
# zwar erst, nachdem er eine Sicherung angelegt hat. Liefe die Migration im
# lifespan der Anwendung, wuerde jeder Neustart zu einem moeglichen
# Schema-Aenderer ohne Sicherungskopie - auch der Neustart nach dem
# Zurueckspielen einer alten Datenbank. Dieselbe Begruendung wie bei Windows,
# siehe docs/release-paket.md.

VOLUME ["/daten"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status == 200 else 1)"

ENTRYPOINT ["/usr/bin/tini", "--", "/app/docker/entrypoint.sh"]
CMD ["app"]
