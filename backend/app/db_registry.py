"""Registry der bekannten Datenbanken (datenbanken.json im Einstellungsordner).

Bewusst ohne Abhängigkeit von app.config, damit config.py dieses Modul
gefahrlos importieren kann (kein Zirkularimport). app.pfade ist dafür
unbedenklich: es importiert selbst nichts aus der Anwendung.
"""

import json
from pathlib import Path
from typing import Optional

from app.pfade import einstellungen_dir

# Eine Einstellung, nicht eine Vorlage: die Datei wird von der Anwendung
# geschrieben und enthält maschinenspezifische absolute Pfade. Sie liegt
# deshalb beim Datenordner und überlebt jedes Update – siehe app.pfade.
REGISTRY_PFAD = einstellungen_dir() / "datenbanken.json"


def lese_eintraege() -> list[dict]:
    if not REGISTRY_PFAD.exists():
        return []
    try:
        data = json.loads(REGISTRY_PFAD.read_text(encoding="utf-8"))
        return data.get("datenbanken", [])
    except Exception:
        return []


def schreibe_eintraege(eintraege: list[dict]) -> None:
    REGISTRY_PFAD.parent.mkdir(exist_ok=True)
    REGISTRY_PFAD.write_text(
        json.dumps({"datenbanken": eintraege}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def aktiver_pfad() -> Optional[Path]:
    """Rein lesend – sicher für den Import in config.py."""
    for eintrag in lese_eintraege():
        if eintrag.get("aktiv"):
            return Path(eintrag["dateipfad"])
    return None


def aktive_id() -> Optional[int]:
    """Rein lesend – sicher für den Import in config.py."""
    for eintrag in lese_eintraege():
        if eintrag.get("aktiv"):
            return eintrag.get("id")
    return None


def naechste_id(eintraege: list[dict]) -> int:
    return max((e.get("id", 0) for e in eintraege), default=0) + 1


def stelle_erstregistrierung_sicher(fallback_pfad: Path) -> list[dict]:
    """Legt bei allererstem Zugriff (Registry-Datei existiert noch nicht)
    die aktuell aktive DB als ersten Eintrag an."""
    if REGISTRY_PFAD.exists():
        return lese_eintraege()
    eintraege = [{"id": 1, "name": "Standard", "dateipfad": str(fallback_pfad), "aktiv": True}]
    schreibe_eintraege(eintraege)
    return eintraege
