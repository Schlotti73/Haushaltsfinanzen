"""Lesen/Schreiben der Anwendungseinstellungen aus der Tabelle `einstellung`.

Die Werte liegen als Text in der DB; konvertiert wird hier, damit die
Aufrufstellen mit fertigen Typen arbeiten. Ein fehlender Schlüssel liefert den
Standardwert aus `_DEFAULTS` – das ist die einzige Quelle für die Defaults,
denn eine neu angelegte DB entsteht über create_all + stamp head und sieht die
Alembic-Migration nie (siehe app/db_init.py).

Nicht zu verwechseln mit den Backup-Einstellungen in config/backup.json: die
gelten datenbankübergreifend, diese hier pro Datenbank.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Einstellung

# Toleranzen der PDF-Import-Vorschau beim Abgleich gegen vorhandene Buchungen.
BETRAG_TOLERANZ = "import_abgleich_betrag_toleranz"
TAGE_TOLERANZ = "import_abgleich_tage_toleranz"

# Dashboard: Karte „Finanzsaldo (ohne Sachwerte)" ein-/ausblenden. Bewusst als
# Opt-in – ohne erfasste Sachwerte (Immobilie) ist die Zahl bei laufendem
# Darlehen dauerhaft stark negativ und ohne Kontext irreführend.
DASHBOARD_FINANZSALDO = "dashboard_finanzsaldo"

# Erinnerungen auf dem Dashboard: ab wann eine Sache als ueberfaellig gilt.
ERINNERUNG_IMPORT_TAGE = "erinnerung_import_tage"
ERINNERUNG_VORLAUF_MONATE = "erinnerung_vorlauf_monate"

# Je Art ein Ein/Aus-Schalter. Bewusst getrennt von der Schwelle und nicht als
# Sonderwert 0 darin: zwei der vier Arten haben gar keine Schwelle, und so
# bleibt die eingestellte Zahl erhalten, wenn die Erinnerung spaeter wieder
# eingeschaltet wird.
ERINNERUNG_ABLESUNGEN_AN = "erinnerung_ablesungen_an"
ERINNERUNG_IMPORT_AN = "erinnerung_import_an"
ERINNERUNG_VORLAUF_AN = "erinnerung_vorlauf_an"
ERINNERUNG_UEBERFAELLIG_AN = "erinnerung_ueberfaellig_an"

_DEFAULTS: dict[str, str] = {
    BETRAG_TOLERANZ: "5.0",
    TAGE_TOLERANZ: "5",
    DASHBOARD_FINANZSALDO: "0",
    # 35 Tage: ein Monatsauszug plus Puffer, damit ein spaeter Versand nicht
    # sofort mahnt. 3 Monate Vorlauf: so viel Zeit bleibt, die geplanten
    # Buchungen nachzuziehen, bevor die Liquiditaetsvorschau duenn wird.
    ERINNERUNG_IMPORT_TAGE: "35",
    ERINNERUNG_VORLAUF_MONATE: "3",
    # Alle vier an: ein Update soll keine Erinnerung verstummen lassen, die
    # vorher sichtbar war.
    ERINNERUNG_ABLESUNGEN_AN: "1",
    ERINNERUNG_IMPORT_AN: "1",
    ERINNERUNG_VORLAUF_AN: "1",
    ERINNERUNG_UEBERFAELLIG_AN: "1",
}

# Obergrenzen: das Tagesfenster steuert auch die DB-Abfrage und die Länge der
# Kandidatenliste in der Vorschau, ein sehr großer Wert macht beides unbrauchbar.
MAX_BETRAG_TOLERANZ = 100.0
MAX_TAGE_TOLERANZ = 30


def lese(db: Session, schluessel: str) -> str:
    row = db.get(Einstellung, schluessel)
    return row.wert if row else _DEFAULTS.get(schluessel, "")


def schreibe(db: Session, schluessel: str, wert: str) -> None:
    row = db.get(Einstellung, schluessel)
    if row:
        row.wert = wert
    else:
        db.add(Einstellung(schluessel=schluessel, wert=wert))


def betrag_toleranz(db: Session) -> float:
    """Betragsspanne in Euro für einen „ähnlich"-Treffer (0 = exakt)."""
    try:
        wert = float(lese(db, BETRAG_TOLERANZ))
    except ValueError:
        return float(_DEFAULTS[BETRAG_TOLERANZ])
    return min(max(wert, 0.0), MAX_BETRAG_TOLERANZ)


def tage_toleranz(db: Session) -> int:
    """Tagesfenster für Kandidatenliste und „ähnlich"-Treffer."""
    try:
        wert = int(lese(db, TAGE_TOLERANZ))
    except ValueError:
        return int(_DEFAULTS[TAGE_TOLERANZ])
    return min(max(wert, 0), MAX_TAGE_TOLERANZ)


def dashboard_finanzsaldo(db: Session) -> bool:
    """Ob das Dashboard die Karte „Finanzsaldo (ohne Sachwerte)" zeigt."""
    return lese(db, DASHBOARD_FINANZSALDO) == "1"


def _zahl(db: Session, schluessel: str, minimum: int, maximum: int) -> int:
    try:
        wert = int(lese(db, schluessel))
    except ValueError:
        wert = int(_DEFAULTS[schluessel])
    return min(max(wert, minimum), maximum)


def erinnerung_import_tage(db: Session) -> int:
    """Tage ohne Kontoauszug-Import, ab denen das Dashboard erinnert."""
    return _zahl(db, ERINNERUNG_IMPORT_TAGE, 1, 365)


def erinnerung_vorlauf_monate(db: Session) -> int:
    """Monate, die geplante Buchungen mindestens in die Zukunft reichen sollen."""
    return _zahl(db, ERINNERUNG_VORLAUF_MONATE, 1, 24)


def _an(db: Session, schluessel: str) -> bool:
    """Ein Schalter ist nur bei ausdruecklichem "0" aus.

    Anders als bei dashboard_finanzsaldo (Opt-in) ist hier alles ein Opt-out:
    ein unbekannter oder kaputter Wert soll die Erinnerung zeigen, nicht
    stillschweigend verschlucken.
    """
    return lese(db, schluessel) != "0"


def erinnerung_ablesungen_an(db: Session) -> bool:
    """Ob das Dashboard an fehlende Jahresablesungen erinnert."""
    return _an(db, ERINNERUNG_ABLESUNGEN_AN)


def erinnerung_import_an(db: Session) -> bool:
    """Ob das Dashboard an Konten ohne Kontoauszug-Import erinnert."""
    return _an(db, ERINNERUNG_IMPORT_AN)


def erinnerung_vorlauf_an(db: Session) -> bool:
    """Ob das Dashboard an zu knapp geplante wiederkehrende Buchungen erinnert."""
    return _an(db, ERINNERUNG_VORLAUF_AN)


def erinnerung_ueberfaellig_an(db: Session) -> bool:
    """Ob das Dashboard an ueberfaellige geplante Buchungen erinnert."""
    return _an(db, ERINNERUNG_UEBERFAELLIG_AN)
