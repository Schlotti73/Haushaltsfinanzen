"""
Backup-Skript: packt finanzen.db + alle Datei-Ablagen in eine ZIP-Datei.

Verwendung:
  python scripts/backup.py
  python scripts/backup.py --ziel C:/Backups/Haushalt
  python scripts/backup.py --ziel //nas/backups/haushalt

Netzwerkziele koennen Zugangsdaten brauchen; sie stehen in config/backup.json
(ziel_benutzer, ziel_passwort – verschluesselt, siehe scripts/netzlaufwerk.py).

Dateiname: <ziel>/YYYY-MM-DD_HH-MM.zip
"""

import argparse
import json
import zipfile
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "backend"))
from app.config import settings  # noqa: E402 – Pfad muss vor dem Import gesetzt sein
from app.db_registry import aktive_id, lese_eintraege  # noqa: E402
from app.pfade import daten_dir, einstellungen_dir  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
import netzlaufwerk  # noqa: E402

DB_PFAD = settings.db_path

# Alle Datei-Ablagen der aktiven DB. Die Datenbank allein genuegt nicht: nach
# einem Restore zeigte sonst jeder Beleg und jeder archivierte Kontoauszug auf
# eine fehlende Datei. Die Pfade kommen aus app.config und tragen bei
# Mehrfach-Datenbanken schon den db-<id>-Unterordner.
#
# Der Schluessel ist der stabile Name der Ablage im Backup (siehe
# _archiv_praefix und backend/app/routers/einstellungen.py) - er haengt nicht am
# Ablageort, damit ein Backup aus der Produktion in der Entwicklung
# wiederherstellbar bleibt und umgekehrt.
DATEI_ABLAGEN: list[tuple[str, str, Path]] = [
    ("belege", "Belege", settings.belege_dir),
    ("kontoauszuege", "Kontoauszuege", settings.kontoauszuege_dir),
    ("kontoauszug_muster", "Kontoauszug-Muster", settings.kontoauszug_muster_dir),
    ("kassenzettel_muster", "Kassenzettel-Muster", settings.kassenzettel_muster_dir),
]


def _archiv_praefix(schluessel: str, ablage: Path) -> str:
    """Ordnername der Ablage im ZIP.

    In der Entwicklung liegen die Ablagen unter dem Projektstamm, in der
    Produktion unter dem Datenordner (ProgramData) - der Programmordner, aus
    dem dieses Skript laeuft, ist dann ein voellig anderer Ort. Fruehere
    Fassungen haben die Pfade im ZIP mit relative_to(ROOT), also relativ zum
    PROGRAMMordner, gebildet. In der Produktion warf das beim ersten Beleg
    ValueError: das ZIP enthielt dann nur die Datenbank, obwohl das Skript
    Dateien mitsichern soll.

    Darum relativ zum Datenordner - und wenn die Ablage ueber eine eigene
    FINANZ_*-Variable ausserhalb davon liegt, unter "ablagen/<schluessel>",
    damit sie trotzdem im Backup landet.
    """
    try:
        return ablage.resolve().relative_to(daten_dir().resolve()).as_posix()
    except ValueError:
        return f"ablagen/{schluessel}"


# Name der Herkunfts-Datei im ZIP – wird beim Wiederherstellen gelesen, siehe
# backend/app/routers/einstellungen.py
META_NAME = "backup_meta.json"

_BACKUP_CFG = einstellungen_dir() / "backup.json"


def _lese_cfg() -> dict:
    if _BACKUP_CFG.exists():
        try:
            return json.loads(_BACKUP_CFG.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


_cfg = _lese_cfg()
BEHALTEN: int = int(_cfg.get("behalten", 30))
_ZIEL_DEFAULT: str = _cfg.get("ziel_ordner", "") or str(daten_dir() / "backups")


def _herkunft() -> dict:
    """Beschreibt, aus welcher registrierten Datenbank dieses Backup stammt.

    Alle Datenbanken sichern in denselben Zielordner und die ZIP-Namen sind
    reine Zeitstempel – ohne diese Angabe liesse sich ein Backup der DB "Firma"
    nicht von einem der DB "Privat" unterscheiden.
    """
    eigene_id = aktive_id()
    name = next(
        (e.get("name") for e in lese_eintraege() if e.get("id") == eigene_id),
        None,
    )
    return {
        "datenbank_id": eigene_id,
        "datenbank_name": name,
        "dateipfad": str(DB_PFAD),
        "erstellt_am": datetime.now().isoformat(timespec="seconds"),
        # Wo im ZIP welche Ablage liegt. Der Restore braucht diese Zuordnung,
        # weil der Datenordner beim Wiederherstellen ein anderer sein kann als
        # beim Sichern (Entwicklung <-> Produktion, verschobener Datenordner).
        "ablagen": {s: _archiv_praefix(s, p) for s, _b, p in DATEI_ABLAGEN},
    }


def backup(ziel: Path) -> None:
    ziel.mkdir(parents=True, exist_ok=True)
    stempel = datetime.now().strftime("%Y-%m-%d_%H-%M")
    zip_pfad = ziel / f"{stempel}.zip"

    if not DB_PFAD.exists():
        print(f"FEHLER: {DB_PFAD} nicht gefunden.")
        sys.exit(1)

    herkunft = _herkunft()

    with zipfile.ZipFile(zip_pfad, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(META_NAME, json.dumps(herkunft, ensure_ascii=False, indent=2))
        zf.write(DB_PFAD, "finanzen.db")
        quelle = herkunft["datenbank_name"] or DB_PFAD.name
        print(f"DB gesichert: finanzen.db aus „{quelle}“ ({DB_PFAD.stat().st_size // 1024} KB)")

        wal = DB_PFAD.with_suffix(".db-wal")
        if wal.exists():
            zf.write(wal, "finanzen.db-wal")

        for schluessel, bezeichnung, ablage in DATEI_ABLAGEN:
            if not ablage.exists():
                continue
            praefix = _archiv_praefix(schluessel, ablage)
            anzahl = 0
            bytes_gesamt = 0
            for datei in sorted(ablage.rglob("*")):
                if datei.is_file():
                    zf.write(datei, f"{praefix}/{datei.relative_to(ablage).as_posix()}")
                    anzahl += 1
                    bytes_gesamt += datei.stat().st_size
            if anzahl:
                # Groesse mit ausgeben: jedes der aufbewahrten Backups enthaelt
                # eine vollstaendige Kopie, das Wachstum soll sichtbar sein.
                print(f"{bezeichnung} gesichert: {anzahl} Dateien ({bytes_gesamt // 1024} KB)")

    print(f"Backup erstellt: {zip_pfad} ({zip_pfad.stat().st_size // 1024} KB)")

    # Alte Backups aufräumen
    alle = sorted(
        [f for f in ziel.iterdir() if f.is_file() and f.suffix == ".zip"],
        key=lambda f: f.name,
        reverse=True,
    )
    for alt in alle[BEHALTEN:]:
        alt.unlink()
        print(f"Altes Backup gelöscht: {alt.name}")


def main():
    parser = argparse.ArgumentParser(description="Backup finanzen.db + Datei-Ablagen als ZIP")
    parser.add_argument("--ziel", default=_ZIEL_DEFAULT)
    args = parser.parse_args()

    # Netzwerkziel: vor dem Kopieren verbinden, danach wieder trennen. Ohne
    # Zugangsdaten gilt der angemeldete Benutzer - der Dienst laeuft aber als
    # LocalSystem und kommt damit meist nicht an eine Freigabe.
    ziel = args.ziel
    benutzer = _cfg.get("ziel_benutzer") or None
    passwort = None
    if benutzer and _cfg.get("ziel_passwort"):
        try:
            passwort = netzlaufwerk.passwort_lesen(_cfg["ziel_passwort"])
        except Exception as fehler:
            print(f"FEHLER: Passwort fuer {benutzer} nicht lesbar ({fehler}).")
            print("Neu setzen mit: python scripts/netzlaufwerk.py --passwort-setzen")
            sys.exit(1)

    verbunden = False
    try:
        if netzlaufwerk.ist_netzpfad(ziel):
            try:
                netzlaufwerk.verbinden(ziel, benutzer, passwort)
                verbunden = True
            except RuntimeError as fehler:
                # Deutlich scheitern statt still kein Backup zu schreiben
                print(f"FEHLER: {fehler}")
                sys.exit(1)
        backup(Path(ziel))
    finally:
        passwort = None
        if verbunden:
            netzlaufwerk.trennen(ziel)


if __name__ == "__main__":
    main()
