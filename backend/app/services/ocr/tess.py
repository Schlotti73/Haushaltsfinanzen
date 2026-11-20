"""Gemeinsame Tesseract-Einrichtung fuer Engine und Vorverarbeitung.

Warum der Sprachdaten-Ordner ueber die Umgebung und nicht ueber
``--tessdata-dir`` gesetzt wird: pytesseract zerlegt den config-String mit
``shlex.split`` und trennt dabei an Leerzeichen. Liegt das Programm unter
``C:\Program Files\…``, kam bei Tesseract nur ``C:/Program`` an:

    Error opening data file C:/Program/deu.traineddata

Anfuehrungszeichen helfen nicht: unter Windows ruft pytesseract shlex mit
``posix=False`` auf, die Zeichen blieben also im Argument stehen.

TESSDATA_PREFIX zeigt ab Tesseract 5 auf den tessdata-Ordner selbst (nicht auf
dessen Elternordner wie bei 4.x). Genauso setzt ihn auch der Windows-Dienst in
scripts/prod/install_service.ps1 - hier wird er gesetzt, damit die Anwendung
auch ohne Dienst-Umgebung (Entwicklung, Docker, Skripte) ihre eigenen
Sprachdaten aus backend/tessdata benutzt und nicht irgendeine zweite
Installation im System.
"""

from __future__ import annotations

import os

import pytesseract

from app.config import settings

pytesseract.pytesseract.tesseract_cmd = str(settings.tesseract_cmd)
os.environ["TESSDATA_PREFIX"] = str(settings.tessdata_dir)

# --psm 6 (einheitlicher Textblock) liefert auf schmalen Kassenzettel-Fotos
# deutlich bessere Ergebnisse als die automatische Seitensegmentierung
# (Standard-PSM 3), die bei langen schmalen Streifen oft fehlschlaegt.
KONFIGURATION = "--psm 6"
