from typing import Optional

import bcrypt
from fastapi import Cookie, Depends, HTTPException, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Benutzer

_serializer = URLSafeTimedSerializer(settings.secret_key, salt="session")


def hash_passwort(passwort: str) -> str:
    return bcrypt.hashpw(passwort.encode(), bcrypt.gensalt()).decode()


def passwort_korrekt(passwort: str, passwort_hash: str) -> bool:
    return bcrypt.checkpw(passwort.encode(), passwort_hash.encode())


def session_erstellen(benutzer_id: int) -> str:
    return _serializer.dumps(benutzer_id)


def session_lesen(token: str) -> Optional[int]:
    try:
        return _serializer.loads(token, max_age=settings.session_max_age)
    except (BadSignature, SignatureExpired):
        return None


def get_current_user(
    session: Optional[str] = Cookie(default=None, alias="finanz_session"),
    db: Session = Depends(get_db),
) -> Benutzer:
    if not session:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet")
    user_id = session_lesen(session)
    if not user_id:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Sitzung abgelaufen")
    user = db.get(Benutzer, user_id)
    if not user or not user.aktiv:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Benutzer nicht gefunden")
    return user


def require_admin(user: Benutzer = Depends(get_current_user)) -> Benutzer:
    if user.rolle != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Nur für Administratoren")
    return user
