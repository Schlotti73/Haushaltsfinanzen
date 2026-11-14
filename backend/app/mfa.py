"""Zweiter Faktor (TOTP) und die Frage, wann er verlangt wird.

Verlangt wird er, wenn die Anfrage nicht aus einem der in config/server.json
eingetragenen Heimnetze kommt – oder immer, wenn das dort so eingestellt ist.
Welche IP dabei zählt, entscheidet server_config.quell_ip: X-Forwarded-For wird
nur von einem ausdrücklich eingetragenen Proxy übernommen, sonst könnte sich
jeder von außen per Header als Heimnetz ausgeben.
"""

from __future__ import annotations

import json
import secrets

import bcrypt
import pyotp
import segno

from app.server_config import einstellungen, ist_heimnetz

AUSGEBER = "Haushaltsfinanzen"
ANZAHL_RECOVERY_CODES = 8


def mfa_noetig(request) -> bool:
    if einstellungen["zugriff"].get("mfa_immer_erforderlich"):
        return True
    return not ist_heimnetz(request)


def neues_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(name: str, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=name, issuer_name=AUSGEBER)


def qr_svg(uri: str) -> str:
    """QR-Code als SVG-Zeichenkette, ohne Bild-Abhängigkeiten."""
    import io

    puffer = io.BytesIO()
    segno.make(uri, error="m").save(puffer, kind="svg", scale=4, border=2)
    return puffer.getvalue().decode("utf-8")


def code_passt(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    # valid_window=1: eine Zeitscheibe Toleranz für ungenaue Uhren
    return pyotp.TOTP(secret).verify(code.replace(" ", ""), valid_window=1)


def neue_recovery_codes() -> tuple[list[str], str]:
    """Liefert die Klartext-Codes (einmalig anzuzeigen) und die gehashte Ablage."""
    codes = [f"{secrets.randbelow(10**5):05d}-{secrets.randbelow(10**5):05d}"
             for _ in range(ANZAHL_RECOVERY_CODES)]
    hashes = [bcrypt.hashpw(c.encode(), bcrypt.gensalt()).decode() for c in codes]
    return codes, json.dumps(hashes)


def recovery_code_einloesen(gespeichert: str | None, eingabe: str) -> str | None:
    """Prüft einen Wiederherstellungscode und gibt die verbleibenden zurück.

    None bedeutet: passte nicht. Ein passender Code wird verbraucht.
    """
    if not gespeichert or not eingabe:
        return None
    try:
        hashes = json.loads(gespeichert)
    except json.JSONDecodeError:
        return None
    eingabe = eingabe.strip()
    for h in hashes:
        if bcrypt.checkpw(eingabe.encode(), h.encode()):
            return json.dumps([x for x in hashes if x != h])
    return None


def offene_recovery_codes(gespeichert: str | None) -> int:
    try:
        return len(json.loads(gespeichert)) if gespeichert else 0
    except json.JSONDecodeError:
        return 0
