"""Update-Erkennung: Status, Download und die Herkunft der Pakete.

Lesen darf jeder Angemeldete - der Hinweis "Version X ist verfuegbar" steht in
der Seitenleiste und waere sonst nur fuer Administratoren da. Alles, was
schreibt oder Daten holt (Herkunft aendern, ZIP herunterladen), bleibt den
Administratoren vorbehalten.

Siehe app/services/update.py fuer die Begruendung des Kanals: ein eigenes,
oeffentliches Paket-Repository, das ohne Zugangsdaten auskommt.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user, require_admin
from app.services import update as upd

router = APIRouter(prefix="/update", tags=["update"])


class UpdateEinstellungen(BaseModel):
    repo: str = ""
    aktiviert: bool = True
    # None heisst: Token unveraendert lassen. Das Frontend kennt das
    # hinterlegte Token nicht und darf es darum nicht zurueckschreiben.
    token: str | None = None


def _cfg_antwort(cfg: dict) -> dict:
    """Niemals das Token selbst ausliefern, nur ob eines hinterlegt ist."""
    return {
        "repo": cfg.get("repo", ""),
        "aktiviert": bool(cfg.get("aktiviert", True)),
        "token_hinterlegt": bool(cfg.get("token")),
    }


@router.get("/status")
def status(erzwingen: bool = False, _=Depends(get_current_user)):
    return upd.status(erzwingen=erzwingen)


@router.get("/einstellungen")
def einstellungen_lesen(_=Depends(require_admin)):
    return _cfg_antwort(upd.lese_cfg())


@router.put("/einstellungen")
def einstellungen_schreiben(daten: UpdateEinstellungen, _=Depends(require_admin)):
    neu = upd.schreibe_cfg(repo=daten.repo, aktiviert=daten.aktiviert, token=daten.token)
    return _cfg_antwort(neu)


@router.post("/download")
def download_starten(erzwingen: bool = False, _=Depends(require_admin)):
    try:
        return upd.starte_download(erzwingen=erzwingen)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err))
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=upd.fehlertext(err))


@router.get("/download")
def download_stand(_=Depends(get_current_user)):
    return upd.download_status()
