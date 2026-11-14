"""Erinnerungen fuer das Dashboard.

Alles wird bei jedem Abruf aus den vorhandenen Daten berechnet und nichts
gespeichert: eine Erinnerung verschwindet genau dann, wenn ihre Ursache weg
ist. Damit kann kein einzelner Posten stillgelegt werden und trotzdem offen
bleiben - der Preis dafuer ist, dass sich eine Erinnerung nicht zurueckstellen
laesst.

Abschalten laesst sich dagegen eine ganze *Art*, je Datenbank in den
Einstellungen. Das ist etwas anderes als Zurueckstellen: es ist eine Aussage
darueber, dass diese Sorte Hinweis in dieser Installation nicht erwuenscht
ist, und sie gilt, bis sie zurueckgenommen wird. Eine abgeschaltete Art wird
gar nicht erst berechnet - das spart die Abfragen und haelt den Zaehler in der
Dashboard-Karte ehrlich.

Jede Art liefert hoechstens eine Zeile mit einer Anzahl. Die Einzelheiten
gehoeren auf die Zielseite, sonst waechst die Dashboard-Karte mit jedem
vergessenen Posten.
"""

from __future__ import annotations

from datetime import date
from typing import List

from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Buchung, Konto, WiederkehrendeBuchung
from app.routers.gebaeude import sammle_offene_ablesungen
from app.schemas import Erinnerung
from app.services import einstellungen as einst

router = APIRouter(prefix="/erinnerungen", tags=["erinnerungen"])


def _ablesungen(db: Session) -> Erinnerung | None:
    offen = sammle_offene_ablesungen(db)
    if not offen:
        return None
    jahre = sum(len(o.jahre) for o in offen)
    return Erinnerung(
        art="ablesungen",
        text=("Eine Jahresablesung fehlt" if jahre == 1
              else f"{jahre} Jahresablesungen fehlen"),
        zusatz=("bei einem Zähler" if len(offen) == 1
                else f"bei {len(offen)} Zählern"),
        anzahl=jahre,
        ziel="/gebaeude",
    )


def _import_faellig(db: Session, heute: date) -> Erinnerung | None:
    """Konten, deren letzter Kontoauszug-Import zu lange her ist.

    Nur Konten, die ueberhaupt schon einmal per PDF befuellt wurden - sonst
    mahnt die Liste ewig fuer Konten, die von Hand gefuehrt werden.
    """
    grenze = (heute - relativedelta(days=einst.erinnerung_import_tage(db))).isoformat()
    letzte = (
        db.query(Buchung.konto_id, func.max(Buchung.datum))
        .filter(Buchung.quelle == "import")
        .group_by(Buchung.konto_id)
        .all()
    )
    aktive = {k.id for k in db.query(Konto).filter(Konto.aktiv == True).all()}
    rueckstaendig = [k for k, letztes in letzte if k in aktive and letztes < grenze]
    if not rueckstaendig:
        return None
    return Erinnerung(
        art="import",
        text=("Ein Konto wartet auf den Kontoauszug" if len(rueckstaendig) == 1
              else f"{len(rueckstaendig)} Konten warten auf den Kontoauszug"),
        zusatz=f"seit mehr als {einst.erinnerung_import_tage(db)} Tagen kein Import",
        anzahl=len(rueckstaendig),
        ziel="/import",
    )


def _vorlauf(db: Session, heute: date) -> Erinnerung | None:
    """Vorlagen, deren geplante Buchungen nicht weit genug in die Zukunft reichen."""
    monate = einst.erinnerung_vorlauf_monate(db)
    horizont = (heute + relativedelta(months=monate)).isoformat()

    letzter_termin = dict(
        db.query(Buchung.wiederkehrend_id, func.max(Buchung.datum))
        .filter(Buchung.wiederkehrend_id.isnot(None))
        .group_by(Buchung.wiederkehrend_id)
        .all()
    )

    knapp = 0
    for wb in db.query(WiederkehrendeBuchung).filter(WiederkehrendeBuchung.aktiv == True).all():
        # Laeuft die Vorlage vor dem Horizont aus, ist nichts nachzuziehen.
        if wb.end_datum and wb.end_datum < horizont:
            continue
        if (letzter_termin.get(wb.id) or "") < horizont:
            knapp += 1
    if not knapp:
        return None
    return Erinnerung(
        art="vorlauf",
        text=("Eine wiederkehrende Buchung ist nicht weit genug geplant" if knapp == 1
              else f"{knapp} wiederkehrende Buchungen sind nicht weit genug geplant"),
        zusatz=f"weniger als {monate} Monate im Voraus",
        anzahl=knapp,
        ziel="/wiederkehrend",
    )


def _ueberfaellig(db: Session, heute: date) -> Erinnerung | None:
    """Geplante Buchungen, deren Termin vorbei ist.

    Entweder sind sie tatsaechlich gelaufen und nur nicht abgeglichen, oder die
    Vorlage dahinter ist tot. Beides faellt sonst nie auf, weil der Blick nach
    vorn geht.
    """
    anzahl = (
        db.query(Buchung)
        .filter(Buchung.status == "geplant", Buchung.datum < heute.isoformat())
        .count()
    )
    if not anzahl:
        return None
    return Erinnerung(
        art="ueberfaellig",
        text=("Eine geplante Buchung ist überfällig" if anzahl == 1
              else f"{anzahl} geplante Buchungen sind überfällig"),
        zusatz="Termin liegt in der Vergangenheit",
        anzahl=anzahl,
        ziel=f"/buchungen?status=geplant&datum_bis={(heute - relativedelta(days=1)).isoformat()}",
    )


@router.get("", response_model=List[Erinnerung])
def list_erinnerungen(db: Session = Depends(get_db), _=Depends(get_current_user)):
    heute = date.today()
    # Die Schalter stehen vor dem Aufruf, nicht dahinter: eine abgeschaltete
    # Art soll ihre Abfragen gar nicht erst absetzen.
    arten = []
    if einst.erinnerung_ablesungen_an(db):
        arten.append(_ablesungen(db))
    if einst.erinnerung_import_an(db):
        arten.append(_import_faellig(db, heute))
    if einst.erinnerung_vorlauf_an(db):
        arten.append(_vorlauf(db, heute))
    if einst.erinnerung_ueberfaellig_an(db):
        arten.append(_ueberfaellig(db, heute))
    return [e for e in arten if e is not None]
