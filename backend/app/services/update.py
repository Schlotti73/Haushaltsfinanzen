"""Erkennen, ob ein neueres Release vorliegt, und das Paket herunterladen.

Gefragt wird ein eigenes, oeffentliches Repository, das nichts als die Pakete
enthaelt - der Quellcode liegt weiterhin woanders. Damit braucht die Abfrage
keine Zugangsdaten.

Der Umweg hat einen Grund. Im privaten Entwicklungs-Repository waere ein
Personal Access Token noetig, und dessen kleinste passende Berechtigung
(`Contents: Read`) umfasst zwangslaeufig den gesamten Quellcode: eine
Beschraenkung auf "nur die Release-Anhaenge" kennt GitHub nicht. Dazu laufen
Token ab, und zwar auf jeder Installation einzeln, ohne dass GitHub sie
erneuern wuerde. Ein oeffentliches Paket-Repository loest beides auf einmal -
und das ZIP enthaelt ohnehin den Quellcode, verbirgt also nichts, was die
Trennung zu schuetzen haette.

Ein Token laesst sich trotzdem hinterlegen, fuer den Fall, dass die Pakete
spaeter wieder privat liegen. Es steht dann in `<Einstellungen>/update.json`,
also beim Datenordner unter ProgramData und nicht beim Programm: so ueberlebt
es jedes Update und kann nicht versehentlich im Repository landen.

Bewusst ohne neue Abhaengigkeit: `urllib.request` aus der Standardbibliothek
genuegt fuer zwei GET-Aufrufe. Ein httpx oder requests muesste sonst als Wheel
mit ins Release-Paket wandern, und das Paket soll fuer diese Kleinigkeit nicht
wachsen.

Installiert wird hier nichts. Der Download legt das ZIP nur ab und nennt den
fertigen update.ps1-Befehl: das Update stoppt den Dienst, der genau diese
Oberflaeche ausliefert, und gehoert darum in eine Administrator-Konsole, nicht
hinter einen Knopf im Browser.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from app.pfade import (betriebsart, daten_dir, einstellungen_dir, programm_dir,
                       version as paket_version)

_CFG_DATEI = einstellungen_dir() / "update.json"
_ZIEL_ORDNER = daten_dir() / "updates"

# Voreingestellt, damit eine frische Installation ohne jedes Zutun prueft.
# Aenderbar bleibt es trotzdem - der Ort der Pakete ist keine Konstante des
# Programms, und ein eigener Webspace kaeme spaeter als zweiter Kanal in Frage.
_DEFAULTS: dict = {
    "aktiviert": True,
    "repo": "Schlotti73/Haushaltsfinanz-Releases",
    "token": "",
}

# Die Release-Abfrage wird kurz zwischengespeichert: die Seitenleiste fragt den
# Status bei jedem Seitenaufruf ab. Ohne Token laesst GitHub nur 60 Anfragen je
# Stunde und IP zu - mit dem Zwischenspeicher sind es hoechstens vier.
_CACHE_SEKUNDEN = 15 * 60
_cache: dict = {"zeit": 0.0, "wert": None}
_cache_lock = threading.Lock()

_download: dict = {
    "status": "leer",       # leer | laeuft | fertig | fehler
    "version": "",
    "geladen": 0,
    "gesamt": 0,
    "pfad": "",
    "befehl": "",
    "starter": "",
    "paket_cmd": "",
    "fehler": "",
}
_download_lock = threading.Lock()


# ── Konfiguration ───────────────────────────────────────────────────────────

def lese_cfg() -> dict:
    if _CFG_DATEI.exists():
        try:
            daten = json.loads(_CFG_DATEI.read_text(encoding="utf-8"))
            return {**_DEFAULTS, **daten}
        except Exception:
            pass
    return dict(_DEFAULTS)


def schreibe_cfg(*, repo: str, aktiviert: bool, token: Optional[str]) -> dict:
    """Speichert die Einstellungen. token=None laesst das bisherige stehen.

    Das Frontend bekommt das Token nie zurueck und schickt es nur, wenn es
    wirklich ein neues gibt - sonst wuerde ein Speichern der Repo-Angabe das
    hinterlegte Token mit einem Platzhalter ueberschreiben.
    """
    alt = lese_cfg()
    neu = {
        "aktiviert": bool(aktiviert),
        "repo": repo.strip(),
        "token": alt["token"] if token is None else token.strip(),
    }
    _CFG_DATEI.parent.mkdir(parents=True, exist_ok=True)
    _CFG_DATEI.write_text(json.dumps(neu, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        # Das Token ist ein Geheimnis: nur der Besitzer der Datei soll es lesen.
        # Unter Windows ohne Wirkung, unter Linux (Entwicklung) sehr wohl.
        _CFG_DATEI.chmod(0o600)
    except OSError:
        pass
    _cache_leeren()
    return neu


def _cache_leeren() -> None:
    with _cache_lock:
        _cache["zeit"] = 0.0
        _cache["wert"] = None


# ── Versionsvergleich ───────────────────────────────────────────────────────

# Die erste Folge punktgetrennter Zahlen im Tag. Traegt also "v1.2.3",
# "1.2.3" und "name-1.2.3" gleichermassen, und schneidet alles ab, was danach
# kommt ("v1.2.3-rc1" -> (1, 2, 3)).
_NUMMER = re.compile(r"\d+(?:\.\d+)*")


def version_tupel(text: str) -> Optional[tuple[int, ...]]:
    """v1.2.3 -> (1, 2, 3). None, wenn die Angabe keine Nummer ist ('dev').

    Vorab-Kennzeichen werden bewusst ignoriert: v1.2.3-rc1 und v1.2.3 gelten
    als dieselbe Version. Das Projekt taggt keine Vorabversionen, und die
    Alternative waere eine halbe semver-Implementierung fuer einen Fall, den
    es nicht gibt.
    """
    if not text:
        return None
    treffer = _NUMMER.search(text)
    if not treffer:
        return None
    return tuple(int(t) for t in treffer.group(0).split(".")[:4])


def ist_neuer(kandidat: str, basis: str) -> bool:
    a, b = version_tupel(kandidat), version_tupel(basis)
    if a is None or b is None:
        return False
    # Auf gleiche Laenge bringen: v1.2 gilt gegenueber v1.2.0 nicht als neuer.
    laenge = max(len(a), len(b))
    a = a + (0,) * (laenge - len(a))
    b = b + (0,) * (laenge - len(b))
    return a > b


# ── GitHub ──────────────────────────────────────────────────────────────────

def _anfrage(url: str, token: str, accept: str) -> urllib.request.Request:
    req = urllib.request.Request(url)
    req.add_header("Accept", accept)
    req.add_header("X-GitHub-Api-Version", "2022-11-28")
    req.add_header("User-Agent", "Haushaltsfinanz-Update")
    # add_unredirected_header, nicht add_header: GitHub leitet den Asset-Download
    # auf eine signierte Speicher-URL um, und die weist eine mitgeschickte
    # Authorization-Zeile mit 400 ab.
    if token:
        req.add_unredirected_header("Authorization", f"Bearer {token}")
    return req


def fehlertext(err: Exception) -> str:
    if isinstance(err, urllib.error.HTTPError):
        if err.code == 401:
            return "GitHub lehnt das Token ab (401). Ist es abgelaufen?"
        if err.code == 404:
            # 404 heisst bei GitHub beides: Repository nicht da und kein
            # Release darin. Die Meldung nennt darum alle drei Ursachen.
            return ("Kein Release gefunden (404). Stimmt die Repo-Angabe, ist dort "
                    "schon ein Release veroeffentlicht - und braucht es, falls das "
                    "Repository privat ist, ein Token?")
        if err.code == 403:
            return ("GitHub verweigert den Zugriff (403) - vermutlich das Stundenlimit "
                    "(ohne Token 60 Anfragen je Stunde). Spaeter noch einmal versuchen.")
        return f"GitHub antwortet mit HTTP {err.code}."
    if isinstance(err, urllib.error.URLError):
        return f"GitHub ist nicht erreichbar: {err.reason}"
    return f"Abfrage fehlgeschlagen: {err}"


def _hole_release(repo: str, token: str) -> dict:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    req = _anfrage(url, token, "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=20) as antwort:
        daten = json.loads(antwort.read().decode("utf-8"))

    zip_asset = None
    for asset in daten.get("assets") or []:
        if str(asset.get("name", "")).lower().endswith(".zip"):
            zip_asset = asset
            break

    return {
        "version": daten.get("tag_name") or "",
        "titel": daten.get("name") or "",
        "hinweise": daten.get("body") or "",
        "veroeffentlicht_am": daten.get("published_at") or "",
        "release_url": daten.get("html_url") or "",
        "asset_name": (zip_asset or {}).get("name") or "",
        "asset_url": (zip_asset or {}).get("url") or "",
        "asset_groesse": (zip_asset or {}).get("size") or 0,
        "asset_digest": (zip_asset or {}).get("digest") or "",
    }


def _release_gecacht(repo: str, token: str, erzwingen: bool) -> dict:
    with _cache_lock:
        frisch = _cache["wert"] is not None and (time.time() - _cache["zeit"]) < _CACHE_SEKUNDEN
        if frisch and not erzwingen:
            return _cache["wert"]
    wert = _hole_release(repo, token)
    with _cache_lock:
        _cache["zeit"] = time.time()
        _cache["wert"] = wert
    return wert


# ── Status ──────────────────────────────────────────────────────────────────

def status(erzwingen: bool = False) -> dict:
    """Alles, was die Oberflaeche ueber den Update-Stand wissen muss."""
    cfg = lese_cfg()
    aktuell = paket_version()
    basis = {
        "aktuelle_version": aktuell,
        "aktiviert": bool(cfg["aktiviert"]),
        # Die Oberflaeche entscheidet daran, ob sie den Download-Knopf zeigt
        # (Windows) oder den fertigen compose-Befehl (Docker).
        "betriebsart": betriebsart(),
        "update_befehl": DOCKER_UPDATE_BEFEHL if betriebsart() == "docker" else "",
        # Das Paket-Repository ist oeffentlich: die Repo-Angabe allein genuegt,
        # ein Token ist die Ausnahme und keine Voraussetzung.
        "konfiguriert": bool(cfg["repo"]),
        "token_hinterlegt": bool(cfg["token"]),
        "repo": cfg["repo"],
        "neuere_version": "",
        "neuer": False,
        "vergleichbar": version_tupel(aktuell) is not None,
        "fehler": "",
    }
    # "Jetzt pruefen" (erzwingen) fragt auch, wenn die Pruefung abgeschaltet
    # ist - wer den Knopf drueckt, will eine Antwort und keine Erinnerung an
    # ein Haekchen.
    if not cfg["repo"] or (not basis["aktiviert"] and not erzwingen):
        return basis
    try:
        release = _release_gecacht(cfg["repo"], cfg["token"], erzwingen)
    except Exception as err:  # noqa: BLE001 - jede Stoerung ist nur ein Hinweis
        basis["fehler"] = fehlertext(err)
        return basis

    basis.update({
        "neuere_version": release["version"],
        "titel": release["titel"],
        "hinweise": release["hinweise"][:4000],
        "veroeffentlicht_am": release["veroeffentlicht_am"],
        "release_url": release["release_url"],
        "asset_name": release["asset_name"],
        "asset_groesse": release["asset_groesse"],
        "neuer": ist_neuer(release["version"], aktuell),
    })
    if not basis["vergleichbar"]:
        basis["fehler"] = ("Die laufende Fassung hat keine Versionsnummer "
                           "(Entwicklungsbetrieb) - ein Vergleich ist nicht moeglich.")
    return basis


# ── Download ────────────────────────────────────────────────────────────────

def download_status() -> dict:
    """Der Stand des Downloads - samt dem Weg, ihn einzuspielen.

    `befehl` und `starter` werden hier bestimmt und nicht beim Download:
    sie beschreiben den *Rechner*, nicht die geladene Datei. Eingefroren
    zeigte die Oberflaeche sonst den Stand von damals - etwa den Konsolenweg,
    obwohl der Doppelklick-Starter seither angelegt wurde (update.ps1 legt ihn
    am Ende jedes Updates an). Genau so trat es auf einer Installation auf,
    die den Starter erst mit dem naechsten Update bekam.
    """
    with _download_lock:
        stand = dict(_download)
    if stand["pfad"]:
        stand["befehl"] = _befehl_fuer(Path(stand["pfad"]))
        stand["starter"] = starter_pfad()
        stand["paket_cmd"] = paket_cmd_pfad() if not stand["starter"] else ""
    return stand


def _setze(**felder) -> None:
    with _download_lock:
        _download.update(felder)


# Der Befehl, mit dem ein vorliegendes Update eingespielt wird. Im Container
# gibt es kein Paket und kein Skript: das Image traegt das Programm, der Tag
# ist die Version, und `pull` tauscht beides. Die Zeichenkette steht hier und
# nicht im Frontend, damit Oberflaeche und Dokumentation denselben Befehl
# nennen.
DOCKER_UPDATE_BEFEHL = "docker compose pull && docker compose up -d"


def _befehl_fuer(pfad: Path) -> str:
    if betriebsart() == "docker":
        return DOCKER_UPDATE_BEFEHL
    return f'.\\update.ps1 -Paket "{pfad}"'


def starter_pfad() -> str:
    """Der Doppelklick-Starter `<Programm>\\update.cmd`, falls es ihn gibt.

    `programm_dir()` zeigt auf den Versionsordner (`<Programm>\\versionen\\v1.5.0`),
    der Starter liegt zwei Ebenen darueber. Erkennbar ist die Prod-Struktur
    daran, dass der Elternordner `versionen` heisst - in der Entwicklung trifft
    das nie zu.

    Geprueft wird zusaetzlich, ob die Datei wirklich existiert: Installationen
    aus der Zeit vor dem Starter bekommen ihn erst mit dem naechsten Update
    (update.ps1 legt ihn dann an). Bis dahin bleibt der Konsolenweg der
    richtige Hinweis, und die Oberflaeche soll nicht auf eine Datei zeigen,
    die es nicht gibt.
    """
    programm = programm_dir()
    if programm.parent.name.lower() != "versionen":
        return ""
    starter = programm.parent.parent / "update.cmd"
    try:
        return str(starter) if starter.is_file() else ""
    except OSError:
        return ""


def paket_cmd_pfad() -> str:
    """Die `update.cmd` aus dem Paket: `<Programm>\\current\\scripts\\prod\\update.cmd`.

    Der Ausweg, wenn der erzeugte Starter im Programmordner fehlt - etwa nach
    einem Rollback auf eine Fassung von vor dem Starter. Diese Datei liegt in
    jedem Paket. Doppelklicken darf man sie allerdings nicht: ohne Argument
    nimmt sie ihren eigenen Paketstamm als Quelle, also die *laufende*
    Version. Ein mitgegebener Pfad gewinnt dagegen immer - die ZIP darauf zu
    ziehen ist darum der richtige Weg.

    Angegeben wird sie ueber `current\\`, nicht ueber den Versionsordner: so
    bleibt der Pfad auch nach dem Update gueltig.
    """
    programm = programm_dir()
    if programm.parent.name.lower() != "versionen":
        return ""
    cmd = programm.parent.parent / "current" / "scripts" / "prod" / "update.cmd"
    try:
        return str(cmd) if cmd.is_file() else ""
    except OSError:
        return ""


def starte_download(erzwingen: bool = False) -> dict:
    """Laedt das ZIP des neuesten Release im Hintergrund herunter."""
    with _download_lock:
        if _download["status"] == "laeuft":
            return dict(_download)

    # Im Container waere das Windows-ZIP nur Ballast im Datenordner: es laesst
    # sich dort weder auspacken noch einspielen. Der Knopf ist in der
    # Oberflaeche zwar ausgeblendet, die Pruefung gehoert trotzdem hierher -
    # die API ist auch ohne Oberflaeche erreichbar.
    if betriebsart() == "docker":
        raise ValueError(
            "Im Container wird kein Paket heruntergeladen. "
            f"Update: {DOCKER_UPDATE_BEFEHL}"
        )

    cfg = lese_cfg()
    if not cfg["repo"]:
        raise ValueError("Es ist kein Repository hinterlegt.")

    release = _release_gecacht(cfg["repo"], cfg["token"], erzwingen)
    if not release["asset_url"]:
        raise ValueError("Das neueste Release hat kein ZIP-Paket als Anhang.")
    if not ist_neuer(release["version"], paket_version()) and not erzwingen:
        raise ValueError("Es liegt keine neuere Version vor.")

    _setze(status="laeuft", version=release["version"], geladen=0,
           gesamt=release["asset_groesse"], pfad="", befehl="", fehler="")

    t = threading.Thread(target=_lade, args=(release, cfg["token"]), daemon=True)
    t.start()
    return download_status()


def _raeume_auf(behalten: Path) -> None:
    """Aeltere Pakete im Update-Ordner entfernen.

    Jedes Release ist rund 80 MB. Ohne das waechst der Datenordner mit jeder
    Version weiter, obwohl ein bereits installiertes Paket niemand mehr
    braucht - fuer das Zurueckrollen ist die vorige Installation da, nicht das
    ZIP (siehe scripts/prod/rollback.ps1).
    """
    for alt in _ZIEL_ORDNER.glob("*.zip"):
        if alt != behalten:
            try:
                alt.unlink()
            except OSError:
                pass


def _lade(release: dict, token: str) -> None:
    ziel = _ZIEL_ORDNER / (release["asset_name"] or f"Haushaltsfinanz_{release['version']}.zip")
    teil = ziel.with_suffix(ziel.suffix + ".teil")
    try:
        _ZIEL_ORDNER.mkdir(parents=True, exist_ok=True)
        req = _anfrage(release["asset_url"], token, "application/octet-stream")
        sha = hashlib.sha256()
        geladen = 0
        with urllib.request.urlopen(req, timeout=60) as antwort, teil.open("wb") as f:
            gesamt = int(antwort.headers.get("Content-Length") or release["asset_groesse"] or 0)
            _setze(gesamt=gesamt)
            while True:
                block = antwort.read(1024 * 256)
                if not block:
                    break
                f.write(block)
                sha.update(block)
                geladen += len(block)
                _setze(geladen=geladen)

        erwartet = (release["asset_digest"] or "").removeprefix("sha256:").strip().lower()
        if erwartet and sha.hexdigest() != erwartet:
            teil.unlink(missing_ok=True)
            _setze(status="fehler",
                   fehler="Die Pruefsumme der geladenen Datei stimmt nicht - Download verworfen.")
            return

        ziel.unlink(missing_ok=True)
        teil.replace(ziel)
        _raeume_auf(ziel)
        # befehl und starter setzt download_status() bei jeder Abfrage frisch.
        _setze(status="fertig", pfad=str(ziel), fehler="")
    except Exception as err:  # noqa: BLE001
        teil.unlink(missing_ok=True)
        _setze(status="fehler", fehler=fehlertext(err))
