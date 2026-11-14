# Wiederkehrende Zahlungen (Phase 1)

Basis für die Tabelle `wiederkehrende_buchungen` und die Liquiditätsvorschau
(Phase 5). Die Werte unten sind **Beispielwerte aus der Platzhalter-Welt**
(siehe [`docs/beispieldaten.md`](beispieldaten.md)) – sie zeigen den Aufbau der
Vorlagen, nicht die Zahlen einer echten Haushaltsplanung. Beim Einrichten
werden sie durch die eigenen Werte ersetzt.

Die Gliederung folgt zwei Blöcken, wie sie eine Haushaltsplanung üblicherweise
hat: Monatswerte („Planung Gehalt") und Jahreswerte („Nebenkosten").

## Monatlich (aus „Planung Gehalt")

| Empfänger/Zweck | Betrag/Monat | Kategorie | Rhythmus |
|---|---:|---|---|
| Gehalt | +2.800 | Einnahmen ▸ Gehalt | monatlich |
| Mieteinnahme | +500 | Einnahmen ▸ Mieteinnahme | monatlich |
| Darlehen Hausbau | −700 | Sparen & Tilgung ▸ Darlehen / Tilgung | monatlich |
| Haushalt | −600 | Haushaltseinkauf | monatlich |
| Nebenkosten (Abschlag) | −200 | Wohnen ▸ Nebenkosten | monatlich |
| Sonstiges | −150 | Sonstiges | monatlich |
| Fahrtkosten | −120 | Auto (Tag: Fahrtkosten) | monatlich |
| Auto | −100 | Auto | monatlich |
| Versicherungen | −100 | Versicherungen ▸ Versicherung allgemein | monatlich |
| Vorsorge | −80 | Versicherungen ▸ Riester / Vorsorge | monatlich |
| Streamflix | −10 | Sonstiges (Tag: Streaming) | monatlich |

> Kontrollsumme: Die Vorlagen sollen in der Summe den geplanten
> Jahresüberschuss ergeben – vor dem Anlegen einmal nachrechnen.

## Jährlich (aus „Nebenkosten")

| Empfänger/Zweck | Betrag/Jahr | Kategorie (Tag = Art) |
|---|---:|---|
| Stadt Beispielstadt – Grundsteuer | −300,00 | Wohnen ▸ Nebenkosten (Tag: Grundsteuer) |
| Abfallgebühren Beispielstadt | −150,00 | Wohnen ▸ Nebenkosten (Tag: Abfall) |
| Stadt Beispielstadt – Abwasser | −280,00 | Wohnen ▸ Nebenkosten (Tag: Abwasser) |
| Beispiel Versicherung AG – Gebäude | −540,00 | Versicherungen (Tag: Gebäude) |
| Beispiel Telekom | −360,00 | Sonstiges (Tag: Telekom) |
| Stadtwerke Beispielstadt – Wasser | −200,00 | Wohnen ▸ Nebenkosten (Tag: Wasser) |
| Stadtwerke Beispielstadt – Strom | −1.140,00 | Wohnen ▸ Nebenkosten (Tag: Strom) |

> Hinweis: Stehen einzelne Strom-/Wasserzähler über ein ganzes Jahr auf 0, wurden
> sie vermutlich auf einen Anbieter zusammengelegt. Vor dem Anlegen der Vorlagen
> prüfen, welche Zähler tatsächlich aktiv sind.

## Nächster Schritt

Diese Liste wird in Phase 5 als `wiederkehrende_buchungen`-Vorlagen angelegt.
Aus den Vorlagen werden geplante Zukunftsbuchungen (Status `geplant`) für die
Liquiditätsvorschau generiert und beim Import echter Buchungen abgeglichen.
