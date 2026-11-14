"""Verbindung zu einem Netzwerkpfad (UNC) mit optionalen Zugangsdaten.

Wird vom Backup genutzt. Das Passwort steht nicht im Klartext in der
Konfiguration, sondern DPAPI-verschlüsselt – entschlüsseln kann es nur derselbe
Windows-Benutzer auf demselben Rechner, unter dem der Dienst läuft.

Passwort ablegen:
    python scripts/netzlaufwerk.py --passwort-setzen
"""

from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(ROOT / "backend"))
from app.pfade import einstellungen_dir  # noqa: E402 – Pfad muss vorher stehen

CFG = einstellungen_dir() / "backup.json"


def _dpapi(richtung: str, daten: bytes) -> bytes:
    """Ver-/Entschlüsselt mit der Windows-Datenschutz-API über PowerShell.

    Bewusst ohne pywin32: das Projekt soll keine zusätzliche Abhängigkeit nur
    fürs Backup bekommen.
    """
    if sys.platform != "win32":
        # Auf Linux (Docker) gibt es keine DPAPI – dort gehört das Passwort in
        # eine Umgebungsvariable oder in die Mount-Optionen des Hosts.
        return daten
    b64 = base64.b64encode(daten).decode()
    if richtung == "schuetzen":
        ps = (f"$b=[Convert]::FromBase64String('{b64}');"
              "Add-Type -AssemblyName System.Security;"
              "$p=[Security.Cryptography.ProtectedData]::Protect($b,$null,'CurrentUser');"
              "[Convert]::ToBase64String($p)")
    else:
        ps = (f"$b=[Convert]::FromBase64String('{b64}');"
              "Add-Type -AssemblyName System.Security;"
              "$p=[Security.Cryptography.ProtectedData]::Unprotect($b,$null,'CurrentUser');"
              "[Convert]::ToBase64String($p)")
    ergebnis = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                              capture_output=True, text=True)
    if ergebnis.returncode != 0:
        raise RuntimeError(f"DPAPI fehlgeschlagen: {ergebnis.stderr.strip()}")
    return base64.b64decode(ergebnis.stdout.strip())


def passwort_schuetzen(klartext: str) -> str:
    return base64.b64encode(_dpapi("schuetzen", klartext.encode())).decode()


def passwort_lesen(geschuetzt: str) -> str:
    return _dpapi("entsperren", base64.b64decode(geschuetzt)).decode()


def ist_netzpfad(pfad: str) -> bool:
    return pfad.startswith("\\\\") or pfad.startswith("//")


def verbinden(pfad: str, benutzer: str | None, passwort: str | None) -> None:
    """Stellt die Verbindung zum UNC-Pfad her.

    Ohne Zugangsdaten wird nichts getan – dann gilt der angemeldete Benutzer.
    Eine bereits bestehende Verbindung meldet Fehler 1219; das ist in Ordnung.
    """
    if not ist_netzpfad(pfad) or not benutzer:
        return
    wurzel = "\\\\" + "\\".join(pfad.lstrip("\\/").replace("/", "\\").split("\\")[:2])
    befehl = ["net", "use", wurzel]
    if passwort:
        befehl.append(passwort)
    befehl += [f"/user:{benutzer}", "/persistent:no"]
    ergebnis = subprocess.run(befehl, capture_output=True, text=True)
    if ergebnis.returncode != 0 and "1219" not in ergebnis.stdout + ergebnis.stderr:
        raise RuntimeError(
            f"Netzwerkpfad {wurzel} nicht erreichbar: "
            f"{(ergebnis.stderr or ergebnis.stdout).strip()}")


def trennen(pfad: str) -> None:
    if not ist_netzpfad(pfad):
        return
    wurzel = "\\\\" + "\\".join(pfad.lstrip("\\/").replace("/", "\\").split("\\")[:2])
    subprocess.run(["net", "use", wurzel, "/delete", "/y"], capture_output=True, text=True)


def _passwort_setzen() -> None:
    import getpass

    cfg = json.loads(CFG.read_text(encoding="utf-8")) if CFG.exists() else {}
    benutzer = input(f"Benutzer [{cfg.get('ziel_benutzer', '')}]: ").strip() or cfg.get("ziel_benutzer", "")
    passwort = getpass.getpass("Passwort: ")
    cfg["ziel_benutzer"] = benutzer
    cfg["ziel_passwort"] = passwort_schuetzen(passwort) if passwort else ""
    CFG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Zugangsdaten in {CFG} abgelegt (Passwort verschlüsselt).")


if __name__ == "__main__":
    if "--passwort-setzen" in sys.argv:
        _passwort_setzen()
    else:
        print(__doc__)
