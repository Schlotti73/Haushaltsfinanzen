from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import mfa as mfa_dienst
from app.auth import (
    get_current_user, hash_passwort, passwort_korrekt,
    require_admin, session_erstellen,
)
from app.database import get_db
from app.models import Benutzer
from app.schemas import BenutzerCreate, BenutzerOut, BenutzerUpdate, LoginRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    user = db.query(Benutzer).filter(func.lower(Benutzer.name) == body.name.lower(), Benutzer.aktiv == True).first()
    if not user or not passwort_korrekt(body.passwort, user.passwort_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Name oder Passwort falsch")

    # Zweiter Faktor nur, wenn die Anfrage nicht aus dem Heimnetz kommt (oder
    # er generell verlangt wird) - siehe app/mfa.py
    if mfa_dienst.mfa_noetig(request):
        if not user.mfa_aktiv:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Zugriff von ausserhalb des Heimnetzes erfordert einen zweiten Faktor. "
                       "Bitte im Heimnetz unter Einstellungen einrichten.")
        if not body.code:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA-Code erforderlich")
        if not mfa_dienst.code_passt(user.mfa_secret, body.code):
            rest = mfa_dienst.recovery_code_einloesen(user.mfa_recovery, body.code)
            if rest is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA-Code falsch")
            user.mfa_recovery = rest
            db.commit()

    token = session_erstellen(user.id)
    response.set_cookie("finanz_session", token, httponly=True, samesite="lax", max_age=60 * 60 * 8)
    return {"id": user.id, "name": user.name, "rolle": user.rolle}


@router.get("/mfa/status")
def mfa_status(request: Request, user: Benutzer = Depends(get_current_user)):
    return {
        "aktiv": bool(user.mfa_aktiv),
        "wird_verlangt": mfa_dienst.mfa_noetig(request),
        "aus_heimnetz": not mfa_dienst.mfa_noetig(request),
        "offene_recovery_codes": mfa_dienst.offene_recovery_codes(user.mfa_recovery),
    }


@router.post("/mfa/einrichten")
def mfa_einrichten(user: Benutzer = Depends(get_current_user), db: Session = Depends(get_db)):
    """Legt ein neues Secret an und liefert QR-Code und Klartext zum Abtippen.

    Aktiv wird es erst, wenn ein erster Code bestaetigt wurde - sonst koennte
    man sich aussperren, falls die App den Code nie richtig erzeugt.
    """
    if user.mfa_aktiv:
        raise HTTPException(400, "Zweiter Faktor ist bereits aktiv")
    user.mfa_secret = mfa_dienst.neues_secret()
    db.commit()
    uri = mfa_dienst.provisioning_uri(user.name, user.mfa_secret)
    return {"secret": user.mfa_secret, "uri": uri, "qr_svg": mfa_dienst.qr_svg(uri)}


@router.post("/mfa/bestaetigen")
def mfa_bestaetigen(code: str, user: Benutzer = Depends(get_current_user), db: Session = Depends(get_db)):
    if not user.mfa_secret:
        raise HTTPException(400, "Erst einrichten")
    if not mfa_dienst.code_passt(user.mfa_secret, code):
        raise HTTPException(400, "Code stimmt nicht")
    codes, gehasht = mfa_dienst.neue_recovery_codes()
    user.mfa_aktiv = True
    user.mfa_recovery = gehasht
    db.commit()
    # Die Klartext-Codes gibt es genau einmal - danach stehen nur noch Hashes in der DB
    return {"aktiv": True, "recovery_codes": codes}


@router.post("/mfa/deaktivieren")
def mfa_deaktivieren(passwort: str, user: Benutzer = Depends(get_current_user), db: Session = Depends(get_db)):
    """Abschalten nur gegen das eigene Passwort."""
    if not passwort_korrekt(passwort, user.passwort_hash):
        raise HTTPException(401, "Passwort falsch")
    user.mfa_aktiv = False
    user.mfa_secret = None
    user.mfa_recovery = None
    db.commit()
    return {"aktiv": False}


@router.post("/logout")
def logout(response: Response, _=Depends(get_current_user)):
    response.delete_cookie("finanz_session")
    return {"ok": True}


@router.get("/me", response_model=BenutzerOut)
def me(user: Benutzer = Depends(get_current_user)):
    return user


# ── Benutzerverwaltung (nur Admin) ──────────────────────────────────────────
@router.get("/benutzer", response_model=list[BenutzerOut])
def list_benutzer(db: Session = Depends(get_db), _=Depends(require_admin)):
    return db.query(Benutzer).all()


@router.post("/benutzer", response_model=BenutzerOut, status_code=201)
def create_benutzer(body: BenutzerCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if db.query(Benutzer).filter(Benutzer.name == body.name).first():
        raise HTTPException(400, "Name bereits vergeben")
    user = Benutzer(name=body.name, passwort_hash=hash_passwort(body.passwort), rolle=body.rolle)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@router.patch("/benutzer/{user_id}", response_model=BenutzerOut)
def update_benutzer(user_id: int, body: BenutzerUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    user = db.get(Benutzer, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    for field, val in body.model_dump(exclude_none=True).items():
        if field == "passwort":
            user.passwort_hash = hash_passwort(val)
        else:
            setattr(user, field, val)
    db.commit()
    db.refresh(user)
    return user


@router.delete("/benutzer/{user_id}", status_code=204)
def delete_benutzer(user_id: int, db: Session = Depends(get_db), admin=Depends(require_admin)):
    if admin.id == user_id:
        raise HTTPException(400, "Eigenen Account nicht löschbar")
    user = db.get(Benutzer, user_id)
    if not user:
        raise HTTPException(404, "Nicht gefunden")
    db.delete(user)
    db.commit()
