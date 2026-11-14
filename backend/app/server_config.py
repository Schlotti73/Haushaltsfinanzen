"""Betriebseinstellungen aus config/server.json.

Eine Datei für Dienst (PowerShell) und Anwendung (Python): Ports, SSL, und
welche Netze als "Heimnetz" gelten. Fehlt die Datei, gelten die Vorgaben
unten – die Anwendung startet also auch ohne sie.
"""

from __future__ import annotations

import ipaddress
import json
from pathlib import Path

from app.pfade import betriebsart, einstellungen_dir

CONFIG_PFAD = einstellungen_dir() / "server.json"

_HEIMNETZE = ["127.0.0.1/32", "192.168.0.0/16", "10.0.0.0/8", "172.16.0.0/12"]

# Im Container faellt 172.16.0.0/12 weg, der Rest bleibt.
#
# Die echte Client-IP kommt auch im Container an: Docker leitet
# veroeffentlichte Ports per iptables-DNAT weiter und erhaelt dabei die
# Absenderadresse. Ein Zugriff aus dem LAN erscheint als 192.168.x.y, einer aus
# dem Internet mit seiner oeffentlichen Adresse - die MFA-Pflicht wirkt dort
# also genauso wie unter Windows. (Nur Verbindungen vom Host selbst laufen
# ueber den Userland-Proxy und erscheinen als 127.0.0.1.)
#
# 172.16.0.0/12 ist aber genau der Bereich, in dem Docker seine Container-Netze
# anlegt. Stuende er in der Vorgabe, gaelte ein Reverse-Proxy im Nachbar-
# container als Heimnetz, ohne dass der Betreiber das entschieden haette - und
# damit jeder, der durch diesen Proxy kommt. Wer einen Proxy einsetzt, traegt
# ihn deshalb bewusst unter vertrauenswuerdige_proxys ein; erst dann wertet
# quell_ip() X-Forwarded-For aus und sieht wieder die echte Client-IP.
#
# Die Liste nicht einfach zu leeren hat einen Grund, der Blut gelassen hat:
# ohne Heimnetz verlangt jede Anmeldung einen zweiten Faktor, einrichten laesst
# der sich aber nur nach einer Anmeldung. Das Ergebnis ist eine geschlossene
# Schleife, aus der nur noch das Bearbeiten von server.json herausfuehrt.
# Siehe docs/docker.md.
_HEIMNETZE_VORGABE = (
    [n for n in _HEIMNETZE if n != "172.16.0.0/12"]
    if betriebsart() == "docker"
    else _HEIMNETZE
)

VORGABE = {
    "port": 8000,
    "https": {"aktiviert": False, "port": 8443, "zertifikat": "", "schluessel": ""},
    "dev": {"backend_port": 8000, "frontend_port": 5173},
    "zugriff": {
        "vertrauenswuerdige_netze": _HEIMNETZE_VORGABE,
        "vertrauenswuerdige_proxys": [],
        "mfa_immer_erforderlich": False,
    },
}


def _tief_ergaenzen(vorgabe: dict, gelesen: dict) -> dict:
    ergebnis = dict(vorgabe)
    for schluessel, wert in (gelesen or {}).items():
        if isinstance(wert, dict) and isinstance(ergebnis.get(schluessel), dict):
            ergebnis[schluessel] = _tief_ergaenzen(ergebnis[schluessel], wert)
        else:
            ergebnis[schluessel] = wert
    return ergebnis


def lade() -> dict:
    try:
        with open(CONFIG_PFAD, encoding="utf-8") as f:
            return _tief_ergaenzen(VORGABE, json.load(f))
    except (OSError, json.JSONDecodeError):
        return dict(VORGABE)


einstellungen = lade()


def erlaubte_origins() -> list[str]:
    """CORS nur für die Dev-Ports; im Betrieb liefert dasselbe uvicorn das Frontend aus."""
    dev = einstellungen["dev"]
    ports = {dev.get("frontend_port", 5173), 3000}
    return [f"http://{host}:{p}" for p in sorted(ports) for host in ("localhost", "127.0.0.1")]


def _netze() -> list:
    netze = []
    for eintrag in einstellungen["zugriff"].get("vertrauenswuerdige_netze", []):
        try:
            netze.append(ipaddress.ip_network(eintrag, strict=False))
        except ValueError:
            continue
    return netze


def ist_vertrauenswuerdiger_proxy(ip: str | None) -> bool:
    if not ip:
        return False
    try:
        adresse = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for eintrag in einstellungen["zugriff"].get("vertrauenswuerdige_proxys", []):
        try:
            if adresse in ipaddress.ip_network(eintrag, strict=False):
                return True
        except ValueError:
            continue
    return False


def quell_ip(request) -> str | None:
    """Die IP, auf die wir uns verlassen.

    X-Forwarded-For wird nur ausgewertet, wenn die Verbindung selbst von einem
    ausdrücklich eingetragenen Proxy kommt. Sonst könnte sich jeder von außen
    per Header als Heimnetz ausgeben und die MFA-Pflicht umgehen.
    """
    peer = request.client.host if request.client else None
    if ist_vertrauenswuerdiger_proxy(peer):
        weitergeleitet = request.headers.get("x-forwarded-for")
        if weitergeleitet:
            return weitergeleitet.split(",")[0].strip()
    return peer


def ist_heimnetz(request) -> bool:
    ip = quell_ip(request)
    if not ip:
        return False
    try:
        adresse = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(adresse in netz for netz in _netze())
