# -*- coding: utf-8 -*-
"""Prueft im laufenden Container, ob die Texterkennung einsatzbereit ist.

Aufruf aus docker/rauchtest.sh:
    docker exec -i <container> python - < docker/ocr_pruefung.py

Von Hand an einer laufenden Installation genauso:
    docker compose exec -T app python - < docker/ocr_pruefung.py

Gibt die gefundenen Sprachdateien aus und endet mit 0, wenn alles passt.
Sonst eine Meldung auf stderr und ein Rueckgabewert ungleich 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "/app/backend")

from app.config import settings  # noqa: E402

ERWARTET = ("deu.traineddata", "eng.traineddata")

vorhanden = sorted(p.name for p in settings.tessdata_dir.glob("*.traineddata"))
fehlend = [n for n in ERWARTET if n not in vorhanden]
if fehlend:
    raise SystemExit(
        f"fehlt in {settings.tessdata_dir}: {', '.join(fehlend)} "
        f"(gefunden: {', '.join(vorhanden) or 'nichts'})"
    )

# Nicht bei der Dateipruefung stehenbleiben, sondern den Weg der Anwendung
# gehen: passt ein Modell nicht zur Tesseract-Fassung oder fehlt das Programm,
# bricht erst dieser Aufruf ab - und zwar mit der Meldung von Tesseract selbst.
from PIL import Image, ImageDraw  # noqa: E402

bild = Image.new("L", (320, 64), 255)
ImageDraw.Draw(bild).text((10, 24), "Guten Morgen", fill=0)
probe = Path("/tmp/rauchtest-ocr.png")
bild.save(probe)

from app.services.ocr.engine import bild_zu_text  # noqa: E402

bild_zu_text(probe)

print(" ".join(vorhanden))
