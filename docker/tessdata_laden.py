# -*- coding: utf-8 -*-
"""Laedt die Tesseract-Sprachdaten fuer das Container-Image.

Laeuft nur beim Bauen, in einer eigenen Stufe (docker/Dockerfile). Das Image
bekommt am Ende allein die beiden .traineddata-Dateien - kein curl, kein
Paketindex, keine Zwischenschichten.

Warum ueberhaupt laden und nicht mitkopieren: backend/tessdata ist
.gitignore't, weil Binaerdateien nicht ins Repository gehoeren. Ein Bau aus
einem frischen Clone - und genau so baut .github/workflows/docker.yml - haette
den Ordner deshalb nicht. Fehlt er, findet Tesseract wegen des erzwungenen
--tessdata-dir (backend/app/services/ocr/engine.py) auch das mitgelieferte
eng nicht, und die Texterkennung fiel komplett aus.

Warum tessdata_fast und nicht das Debian-Paket tesseract-ocr-deu: unter
Windows fuellt scripts/dev dieselbe Quelle nach backend/tessdata (siehe
docs/dev-workflow.md). Eine zweite Quelle hiesse andere Modelle und damit
andere Erkennungsergebnisse auf derselben Programmfassung.

Fassung und Pruefsummen sind festgenagelt: ein stiller Austausch der Modelle
wuerde die Erkennung veraendern, ohne dass sich eine Zeile Code aendert.
"""

from __future__ import annotations

import hashlib
import sys
import urllib.request
from pathlib import Path

FASSUNG = "4.1.0"
QUELLE = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/" + FASSUNG

# sha256 der Dateien aus tessdata_fast 4.1.0. Dieselben Dateien liegen unter
# Windows in backend/tessdata - gegengeprueft, bitgleich.
DATEIEN = {
    "deu.traineddata": "19d219bbb6672c869d20a9636c6816a81eb9a71796cb93ebe0cb1530e2cdb22d",
    "eng.traineddata": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
}


def main(ziel: Path) -> int:
    ziel.mkdir(parents=True, exist_ok=True)
    for name, erwartet in DATEIEN.items():
        url = f"{QUELLE}/{name}"
        print(f"  lade {name} aus tessdata_fast {FASSUNG} …", flush=True)
        with urllib.request.urlopen(url, timeout=120) as antwort:
            daten = antwort.read()

        tatsaechlich = hashlib.sha256(daten).hexdigest()
        if tatsaechlich != erwartet:
            # Harter Abbruch: ein Modell unbekannter Herkunft ist schlimmer als
            # ein fehlgeschlagener Bau. Der Bau ist sichtbar, das andere nicht.
            print(
                f"FEHLER: {name} hat eine andere Pruefsumme als erwartet.\n"
                f"  erwartet:     {erwartet}\n"
                f"  heruntergel.: {tatsaechlich}\n"
                f"  Quelle:       {url}\n"
                "  Wurde die Fassung in tessdata_fast neu geschrieben? Dann die\n"
                "  Pruefsumme hier bewusst nachziehen, nicht einfach ersetzen.",
                file=sys.stderr,
            )
            return 1

        (ziel / name).write_bytes(daten)
        print(f"  ok  {name}  {len(daten) / 1024:.0f} KiB", flush=True)

    return 0


if __name__ == "__main__":
    pfad = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tessdata")
    raise SystemExit(main(pfad))
