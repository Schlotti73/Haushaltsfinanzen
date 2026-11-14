from pathlib import Path
from pydantic_settings import BaseSettings

from app.db_registry import aktive_id, aktiver_pfad
from app.pfade import daten_dir, programm_dir


class Settings(BaseSettings):
    db_path: Path = daten_dir() / "finanzen.db"
    secret_key: str = "change-me-in-production-use-long-random-string"
    session_max_age: int = 60 * 60 * 8  # 8 Stunden
    belege_dir: Path = daten_dir() / "belege"
    kontoauszuege_dir: Path = daten_dir() / "kontoauszuege"
    kontoauszug_muster_dir: Path = daten_dir() / "kontoauszug_muster"
    kassenzettel_muster_dir: Path = daten_dir() / "kassenzettel_muster"
    tesseract_cmd: Path = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    # Gehört zum Programm, nicht zu den Daten: tessdata kommt aus dem Paket.
    tessdata_dir: Path = programm_dir() / "backend" / "tessdata"

    class Config:
        env_file = ".env"
        env_prefix = "FINANZ_"


settings = Settings()

# Registrierte aktive Datenbank (config/datenbanken.json) gewinnt immer,
# auch über FINANZ_DB_PATH/.env – siehe app.db_registry.
_registrierter_pfad = aktiver_pfad()
if _registrierter_pfad is not None:
    settings.db_path = _registrierter_pfad

# Bei Mehrfach-Datenbank-Verwaltung braucht jede DB außer der ursprünglichen
# "Standard"-DB (id 1, immer die zuerst registrierte – siehe app.db_registry
# .stelle_erstregistrierung_sicher) eigene Datei-Ablagen. Sonst würden z.B.
# Kassenzettel-Muster mit demselben Geschäfts-Slug ("aldi", "lidl", …) aus
# verschiedenen DBs sich im selben globalen Ordner überschreiben. id 1 bleibt
# bewusst auf den bisherigen, unveränderten Pfaden (keine Migration nötig).
_aktive_id = aktive_id()
if _aktive_id is not None and _aktive_id != 1:
    _unterordner = f"db-{_aktive_id}"
    settings.belege_dir = settings.belege_dir / _unterordner
    settings.kontoauszuege_dir = settings.kontoauszuege_dir / _unterordner
    settings.kontoauszug_muster_dir = settings.kontoauszug_muster_dir / _unterordner
    settings.kassenzettel_muster_dir = settings.kassenzettel_muster_dir / _unterordner

settings.belege_dir.mkdir(parents=True, exist_ok=True)
settings.kontoauszuege_dir.mkdir(parents=True, exist_ok=True)
settings.kontoauszug_muster_dir.mkdir(parents=True, exist_ok=True)
settings.kassenzettel_muster_dir.mkdir(parents=True, exist_ok=True)
