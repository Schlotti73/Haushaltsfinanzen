# Kategorien-Mapping (Phase 1)

Zuordnung der „Klasse"-Werte eines Altbestands auf das Kategorie-/Tag-/Projekt-Modell.
Maschinenlesbar in [`config-vorlagen/mapping.json`](../config-vorlagen/mapping.json) – die
Datei bleibt als Vorlage erhalten, `scripts/init_db.py` legt daraus die Konten an.
Das Werkzeug für die einmalige Übernahme liegt nicht im Repository.

Die Häufigkeiten stammen aus der Auswertung eines solchen Altbestands und
zeigen, welche Klassen überhaupt ins Gewicht fallen. Personen- und Ortsnamen
sind darin durch Platzhalter ersetzt.

| Alt-„Klasse" | Anzahl | → Kategorie | Tag | Projekt | Anmerkung |
|---|---:|---|---|---|---|
| Sonstiges | 1015 | Sonstiges | | | Sammelposten – kann später feiner aufgeteilt werden |
| Nebenkosten | 298 | Wohnen ▸ Nebenkosten | (aus Info) | | Tag je Art beim Import aus Info-Spalte ableiten |
| Haus | 134 | Wohnen ▸ Instandhaltung | | Haus | |
| Person 1 | 76 | Person | Person 1 | | Person → Tag |
| Auto | 70 | Auto | | | |
| Gehalt | 66 | Einnahmen ▸ Gehalt | | | |
| Miete | 57 | Einnahmen ▸ Mieteinnahme | | | Mieteingang; reine Mietzahlungen ggf. manuell auf „Miete (Zahlung)" |
| Rente | 52 | Versicherungen ▸ Riester / Vorsorge | | | Vorsorgebeiträge (ausgehend) |
| Rezeptgebühren | 33 | Pflege ▸ Rezeptgebühren | | | |
| Versicherung | 30 | Versicherungen ▸ Versicherung allgemein | | | |
| Spende | 20 | Spende | | | |
| Ort 1 | 17 | Sonstiges | | Ort 1 | Ort/Projekt → Projekt |
| Garten | 5 | Wohnen ▸ Garten | | | |
| Verhinderungspflege | 6 | Pflege ▸ Verhinderungspflege | | | |
| Darlehen | 3 | Sparen & Tilgung ▸ Darlehen / Tilgung | | | |
| Pflege | 3 | Pflege ▸ Pflege allgemein | | | |
| Einrichtung | 3 | Wohnen ▸ Einrichtung | | | |
| Person 2 | 2 | Person | Person 2 | | |
| Instandsetzung | 2 | Wohnen ▸ Instandhaltung | Instandsetzung | | |
| Haushalt | 1 | Haushaltseinkauf | | | |
| Wartung | 1 | Wohnen ▸ Instandhaltung | Wartung | | |
| Ort 2 | 1 | Sonstiges | | Ort 2 | |

### Zusätzlich aus Sheet „Neubau" und „Planung Gehalt"

| Alt-„Klasse" | → Kategorie | Tag | Projekt |
|---|---|---|---|
| Anschluss / Bau / Grundstück | Sonstiges | | Neubau |
| Pflegegeld | Einnahmen ▸ Pflegegeld | | |
| Fahrtkosten | Auto | Fahrtkosten | |
| Kleinkredit | Sparen & Tilgung ▸ Darlehen / Tilgung | Kleinkredit | |
| Riester | Versicherungen ▸ Riester / Vorsorge | | |
| Streaming | Sonstiges | Streaming | |
| Gemeinde | Sonstiges | Gemeinde | |

## Offene Entscheidungen (bitte prüfen/bestätigen)

1. **„Sonstiges" mit 1015 Buchungen** ist der größte Posten. Soll das so bleiben,
   oder beim Import versucht werden, anhand des Empfängers feiner zu klassifizieren
   (z. B. Lebensmittel-Händler → Haushaltseinkauf)?
2. **„Miete" (57×)** ist hier *Einnahme*. Falls auch ausgehende
   Mietzahlungen unter „Miete" liefen, müssten die getrennt werden.
3. **„Haus" vs. „Neubau":** „Haus" → Projekt *Haus* (Bestandsimmobilie/Tilgung),
   „Neubau" → Projekt *Neubau*. Passt diese Trennung?
4. **„Rente" = Vorsorgebeiträge** (ausgehend) → unter Versicherungen einsortiert.
   Korrekt, oder eigene Kategorie „Vorsorge"?
