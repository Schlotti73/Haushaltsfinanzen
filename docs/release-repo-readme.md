# Haushaltsfinanz – Releases

Dieses Repository enthält keinen Code. Es dient allein dazu, die
Release-Pakete von **Haushaltsfinanz** abzulegen, einem privaten Werkzeug zur
Haushaltsbuchführung (FastAPI + React, Betrieb als Windows-Dienst).

Die Pakete liegen unter [Releases](../../releases) als
`Haushaltsfinanz_<version>.zip`.

## Wozu das getrennte Repository

Die Anwendung prüft selbst, ob eine neuere Fassung vorliegt, und lädt das
Paket herunter. Dafür muss das letzte Release abrufbar sein – mehr nicht.
Läge es im Entwicklungs-Repository, bräuchte jede Installation ein
Zugangstoken, das zwangsläufig auch den gesamten Quellcode lesen dürfte und
regelmäßig abläuft. Hier genügt eine anonyme Abfrage, und zugänglich ist
genau das ZIP.

## Systemanforderungen

Mitzubringen, sonst bricht die Installation ab:

| | |
|---|---|
| Windows | 10 oder 11, 64-Bit |
| Rechte | Administrator (das Setup fragt sie selbst ab) |
| Internet | während der Installation, danach nicht mehr nötig |
| App Installer | der Befehl `winget`; er gehört zu Windows 10/11, fehlt aber auf manchen Systemen |

Fehlt `winget`, meldet das Setup das vor der ersten Änderung und nennt die
beiden Bezugswege: den „App Installer" aus dem Microsoft Store oder das
`.msixbundle` von [winget-cli](https://github.com/microsoft/winget-cli/releases).
Gebraucht wird er nur, solange Python und die Texterkennung noch fehlen – sind
sie bereits installiert, läuft das Setup auch ohne ihn.

Das Setup holt selbst nach, was fehlt:

* **Python** – die Laufzeitumgebung der Anwendung,
* **Tesseract-OCR** – die Texterkennung für Kassenzettel und Belege,
* **WinSW** – den Wrapper, der die Anwendung als Windows-Dienst betreibt.

Alles Übrige liegt im Paket: die Python-Pakete als fertige Wheels, die
Sprachdaten der Texterkennung und das vorgebaute Frontend. Node.js wird auf
dem Zielrechner nicht gebraucht. Die genauen Versionen stehen in
`docs/betrieb.md` im Paket.

## Installation

ZIP freigeben (Rechtsklick → Eigenschaften → „Zulassen"), entpacken,
`setup.cmd` starten.

Update: entpacken und `update.cmd` starten – oder, bei einer laufenden
Installation, das Paket unter *Einstellungen → Programm-Update* herunterladen
und den dort genannten Starter doppelklicken.

Ausführlich in `docs/betrieb.md` im Paket.
