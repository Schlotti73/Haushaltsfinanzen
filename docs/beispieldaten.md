# Beispieldaten – Platzhalter-Welt

Alle Beispiele in Hilfetexten, Doku, Code-Kommentaren, Formular-Platzhaltern und in der
Demo-Datenbank verwenden **dieselben erfundenen Namen**. Sie sind plausibel, aber keiner
existiert – damit verrät kein Beispiel, wo jemand tatsächlich einkauft.

## Regel

| Was | Behandlung |
|---|---|
| Geschäfte, Läden, Händler, Empfänger, Orte, Personen | **erfunden**, aus der Liste unten |
| Banken (Postbank, ING, Sparkasse) | **bleiben echt** – sie benennen die tatsächlich unterstützten Kontoauszugs-Parser |
| Zahlungsdienste (PayPal, Klarna) und der Amazon-CSV-Abgleich | **bleiben echt** – sie benennen Formate und Funktionen, die die App wirklich behandelt |
| Seed-Muster für Kassenzettel und Geschäfte (Alembic-Migrationen) | **bleiben echt** – fiktive Namen würden keine echten Belege erkennen |

Kurz: Was jemand *kauft*, ist erfunden. Was die App *technisch unterstützt*, wird beim Namen genannt.

## Namen

### Geschäfte (Kassenzettel)

| Rolle | Name | Schreibweise auf dem Kontoauszug |
|---|---|---|
| Supermarkt | Markt Müller | `MARKT MUELLER DANKT` |
| Getränkemarkt | Getränke Nord | `Getranke Nord Selbststand Iger` |
| Discounter | Sparmarkt | `SPARMARKT SAGT DANKE` |
| Baumarkt | Baumarkt Süd | `BAUMARKT SUED GMBH` |
| Lieferdienst / Restaurant | Pizza Primo | `PIZZA PRIMO 12345` |
| Streaming-Abo | Streamflix | `STREAMFLIX ABO` |

„Getränke Nord" ist mit Absicht dabei: Das Beispiel zeigt, wie die Umlaut-Normalisierung
aus `Getranke Nord` im PDF trotzdem einen Treffer auf `Getränke Nord` macht.

### Empfänger (Kontoauszug)

- Stadtwerke Beispielstadt (Strom, Wasser)
- Wohnbau Beispielstadt (Miete)
- Beispiel Versicherung AG
- Mustermann, Erika / Mustermann, Max (Privatpersonen)

### Konten

- Girokonto
- Sparkonto
- Darlehen Hausbau (Annuität)
- Zwischenfinanzierung (endfällig)

### Projekte und Gebäude

- Projekt „Sanierung Beispielhaus" mit Posten Dach, Fenster, Heizung
- Gebäude „Beispielhaus, Musterweg 1, 12345 Beispielstadt"

### Zugänge und Platzhalter

- Admin-Benutzer in Entwicklung und Erstinstallation: `admin`
- Zählernummern in Beispielen: kurze Phantasienummern wie `12345678`
- Einmal-Werkzeuge zur Übernahme von Altbeständen sind kein Teil des
  Repositories. Sie lesen echte Daten und gehören deshalb nicht in etwas,
  das veröffentlicht wird.

### Beträge

Runde, erkennbar erfundene Werte: Miete 500 €, Strom 95 €, Gehalt 2.800 €,
Darlehen 150.000 € zu 3,5 %.

## Beim Erweitern

Neue Beispiele nehmen Namen aus dieser Liste. Fehlt eine Rolle, wird sie hier
ergänzt – nicht im Hilfetext improvisiert, sonst laufen Hilfe, Doku und Demo
auseinander.
